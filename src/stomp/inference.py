# SPDX-License-Identifier: BSD-3-Clause

'''This module infers parallel loops.'''

from typing import Optional
from psyclone.psyir.nodes import Node, Routine, Loop
from psyclone.psyir.tools import ReductionInferenceTool
from psyclone.psyir.nodes.omp_directives import MAP_REDUCTION_OP_TO_OMP
from stomp.openmp_directives import \
    MAP_REDUCTION_OP_TO_STR, get_enclosing_directives
from stomp.message import StompMessageCode, StompLogger
from stomp.loop_conflict_analysis import \
    LoopConflictAnalysis, LoopConflictAnalysisOptions
from stomp.liveness_analysis import is_live_out
from stomp.misc import is_array_access
from stomp.solver_options import SMTSolverOptions


# Infer parallel loops
# ====================


def infer_parallel_loops(psyir: Node,
                         solver_options: Optional[SMTSolverOptions] = None):
    '''Look for loops not enclosed by OpenMP directives which don't
    contain any conflicts between iterations.'''
    for routine in psyir.walk(Routine):
        for loop in routine.walk(Loop):
            # Skip loops nested within OpenMP directives
            if get_enclosing_directives(loop): continue

            loop_vars = [loop.variable.name for loop in loop.walk(Loop)]
            accesses = loop.reference_accesses()

            # Initialisation
            red_infer = ReductionInferenceTool(MAP_REDUCTION_OP_TO_OMP.keys())
            red_clauses = []
            private_vars = []

            # Check for scalar conflicts
            scalar_conflict = False
            for (sig, seq) in accesses.items():
                # Is it scalar access?
                is_scalar = not any([is_array_access(info) for info in seq])

                if is_scalar:
                    # Ignore loop variables
                    if sig.var_name in loop_vars: continue

                    # Ignore read-only variables
                    if seq.is_read_only(): continue

                    # Allow reduction variables
                    red_clause = red_infer.attempt_reduction(sig, seq)
                    if red_clause:
                        red_clauses.append(red_clause)
                        continue

                    # Allow non-read-before-write that are not live-out
                    read_before_write = seq and \
                                        seq[0].is_any_read() and \
                                        seq.is_written()
                    ok = not read_before_write and \
                         not is_live_out(sig.var_name, loop)
                    if seq.is_written():
                        private_vars.append(sig.var_name)
                    if ok: continue

                    scalar_conflict = True
                    break

            if scalar_conflict:
                continue

            # Check for array conflicts
            opts = LoopConflictAnalysisOptions()
            if solver_options:
                opts.sweep_seed = solver_options.sweep_seed
                opts.num_sweep_threads = solver_options.sweep_threads
                opts.smt_timeout_ms = solver_options.solver_timeout_ms
                opts.use_bv = solver_options.use_bit_vec
                opts.int_width = solver_options.bit_vec_width
                opts.prohibit_overflow = opts.use_bv
            analysis = LoopConflictAnalysis(opts)
            conflicts = analysis.get_loop_conflicts(loop)
            if not conflicts:
                clauses = []
                if private_vars:
                    clauses.append("private(" + ", ".join(private_vars) + ")")
                for (red_op, ref) in red_clauses:
                    op = MAP_REDUCTION_OP_TO_STR[red_op]
                    clauses.append("reduction(" + op + ": " + ref.name + ")")
                desc = f"Loop over variable '{loop.variable.name}' " \
                       f"is parallelisable"
                if clauses:
                    clause_text = " ".join(clauses)
                    desc += f" using the following clauses: '{clause_text}'."
                else:
                    desc += "."
                StompLogger.add_message(
                    StompMessageCode.FoundParallelisableLoop,
                    description = desc,
                    node = loop,
                    routine_name = routine.name)
