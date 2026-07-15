# SPDX-License-Identifier: BSD-3-Clause

'''This module implements static checks.'''

from psyclone.core import Signature
from psyclone.psyir.nodes import \
  Node, Routine, Loop, Call, IntrinsicCall, ArrayReference, Reference
from psyclone.psyir.tools import ReductionInferenceTool
from stomp.openmp_directives import \
    OpenMPDirective, \
    is_within_directive, is_child_directive, \
    get_enclosing_directives, MAP_REDUCTION_OP_TO_STR
from stomp.message import StompMessageCode, StompLogger
from stomp.array_index_analysis import _is_scalar_integer
from stomp.loop_conflict_analysis import LoopConflictAnalysis
from stomp.region_conflict_analysis import RegionConflictAnalysis
from stomp.misc import is_array_access, get_nested_loops
from stomp.module_spec_directives import is_threadsafe


# Basic checks that apply to every directive
# ==========================================


def check_loose_end(d: OpenMPDirective):
    '''Check that an "end" directive has a matching starting directive.'''
    if "end" in d.clauses and d.started_by is None:
        StompLogger.add_message(
            StompMessageCode.UnmatchedEnd,
            description = "Could not find associated starting "
                "directive for this OpenMP 'end' directive.",
            directive_node = d.original_directive)


def check_loop_directive_is_followed_by_loop(d: OpenMPDirective):
    '''Check that a loop directive is followed by a loop.'''
    if "end" not in d.clauses:
        if d.is_loop():
            is_loop = d.position+1 < len(d.siblings) and \
                      isinstance(d.siblings[d.position+1], Loop)
            if not is_loop:
                StompLogger.add_message(
                    StompMessageCode.LoopDirectiveHasNoLoop,
                    description = "OpenMP loop directive is not "
                                  "followed by a loop.",
                    directive_node = d.original_directive)


def check_singleton_directive_num_stmts(d: OpenMPDirective):
    '''Check that singleton directives with an associated "end" directive
    contain exactly one statement.'''
    if "end" not in d.clauses:
        if d.is_singleton():
            if d.ended_by is not None:
                num_stmts = d.ended_by.position - d.position - 1
                if num_stmts != 1:
                    StompLogger.add_message(
                        StompMessageCode.SingleStatementExpected,
                        description = f"OpenMP directive should hold a "
                            f"single statement but {num_stmts} statements "
                            f"have been provided.",
                        directive_node = d.original_directive)


def check_singleton_directive_not_empty(d: OpenMPDirective):
    '''Check that singleton directives are followed by a statement.'''
    if "end" not in d.clauses:
        if d.is_singleton():
            if len(d.siblings[d.position+1:]) == 0:
                StompLogger.add_message(
                    StompMessageCode.SingletonDirEmpty,
                    description = "OpenMP singleton directive has "
                        "no associated statement.",
                    directive_node = d.original_directive)


def check_standalone_directive_not_end(d: OpenMPDirective):
    '''Check that standalone directives are not end directives.'''
    if "end" in d.clauses and d.is_standalone():
        StompLogger.add_message(
            StompMessageCode.EndStandaloneDir,
            description = "Standalone OpenMP directive should not "
                "have an associated 'end' directive.",
            directive_node = d.original_directive)


def check_directive_is_recognised(d: OpenMPDirective):
    '''Check that directives are recognised OpenMP directives.'''
    kws = d.get_directive_keywords()
    if kws and kws[0] == "end":
        del kws[0]
    if tuple(kws) not in d.get_allowed_keywords_set():
        StompLogger.add_message(
            StompMessageCode.UnrecognisedDirective,
            description = "This is not a recognised OpenMP directive.",
            directive_node = d.original_directive)


def check_ordered_directives(d: OpenMPDirective):
    '''For an "ordered" directive inside a "do" directive, the "do"
    directive must contain the "ordered" clause.'''
    if "end" in d.clauses: return
    if "ordered" in d.clauses and "do" not in d.clauses:
        for e in get_enclosing_directives(d):
            if "do" in e.clauses:
                if "ordered" not in e.clauses:
                    StompLogger.add_message(
                        StompMessageCode.StrayOrderedDirective,
                        description = "Found 'ordered' directive enclosed "
                            "by a 'do' directive without the 'ordered' "
                            "clause.",
                        directive_node = d.original_directive)
                break


def check_nested_directives(d: OpenMPDirective):
    '''Check for nested directives that are not supported
    by the checker.'''
    if "end" in d.clauses: return
    enclosing = get_enclosing_directives(d)
    disallowed_nested_dirs = ["parallel", "teams", "distribute",
        "do", "sections"]
    for disallow in disallowed_nested_dirs:
        if disallow in d.clauses:
            bad = any([disallow in e.clauses for e in enclosing])
            if bad:
                StompLogger.add_message(
                   StompMessageCode.DisallowedNestedDirective,
                   description = f"Found nested '{disallow}' directive, "
                       "which is either not allowed by OpenMP or not "
                       "supported by the checker.",
                   directive_node = d.original_directive)
                break


def check_stomp_unique_directives(d: OpenMPDirective):
    '''Check that stomp 'unique' directives contain a scalar integer
    Reference.'''
    if d.is_stomp_directive and "unique" in d.clauses:
        expr = d.clauses["unique"]
        ok = isinstance(expr, Reference) and \
             not isinstance(expr, ArrayReference) and \
             _is_scalar_integer(expr.datatype)
        if not ok:
            StompLogger.add_message(
                StompMessageCode.BadUniqueDirective,
                description = "The 'unique' directive must contain "
                    "a scalar integer reference as its argument.",
                directive_node = d.original_directive)


# Collapsed loop checks
# =====================


def check_collapse_clause(d: OpenMPDirective):
    '''Check that all OpenMP loops with a collapse(n) clause preceed an
    n-element loop nest, and the loop ranges are not data dependent.'''
    if d.is_loop() and d.is_singleton() and "collapse" in d.clauses:
        # Check that collapse clause is non-zero
        if d.clauses["collapse"] == 0:
            StompLogger.add_message(
                StompMessageCode.InvalidCollapseClause,
                description = "A 'collapse' clause with a value of 0 "
                    "is not allowed.",
                directive_node = d.original_directive)
        # Check that num loops are consistent with collapse clause
        loop = d.get_singleton_body()
        loops = get_nested_loops(loop)
        expected = d.clauses["collapse"]
        got = len(loops)
        if got < expected:
            StompLogger.add_message(
                 StompMessageCode.InvalidCollapseClause,
                 description = f"Collapse clause suggests "
                     f"{expected} nested loops but only {got} found.",
                 directive_node = d.original_directive)
        # Check for data dependencies between the variable of an outer loop
        # and the ranges of its inner loops
        found = False
        loop = loops.pop(0)
        while loops:
            loop_exprs = []
            loop_exprs.extend([loop.start_expr for loop in loops])
            loop_exprs.extend([loop.stop_expr for loop in loops])
            loop_exprs.extend([loop.step_expr for loop in loops])
            for expr in loop_exprs:
                if expr is None: continue
                for sig in expr.reference_accesses().all_data_accesses:
                    if loop.variable.name == str(sig):
                        found = True
                        break
                if found: break
            if found: break
            loop = loops.pop(0)
        if found:
            StompLogger.add_message(
                StompMessageCode.NonRectangularLoop,
                description = f"Found a non-rectangular collapsed loop nest: "
                    f"the range of an inner loop depends on an outer loop "
                    f"variable, namely '{loop.variable.name}'. This may not "
                    f"be supported by your OpenMP implementation.",
                directive_node = d.original_directive,
                node = loop)


# Data sharing checks
# ===================


def check_data_sharing_clauses(d: OpenMPDirective):
    '''Basic checks for variables mentioned in data sharing clauses.'''
    # Check that loop variables are not declared as shared
    must_be_private = d.get_always_private()
    (private, shared, red) = d.get_private_shared_red()
    contradiction = must_be_private & shared
    if contradiction:
        StompLogger.add_message(
            StompMessageCode.DataSharingConflict,
            description = f"Variable '{contradiction.pop()}' "
                f"must be private but is declared as 'shared'.",
            directive_node = d.original_directive)


# Reduction clause checks
# =======================


def check_reduction_clauses(d: OpenMPDirective):
    '''Check that reduction clauses describe valid reductions.'''
    if "end" in d.clauses: return

    if "reduction" in d.clauses:
        # Create mapping from string to reduction operator
        str_to_red_op = {}
        for (op, s) in MAP_REDUCTION_OP_TO_STR.items():
           str_to_red_op[s] = op

        # Get accesses in directive body
        accesses = d.body_reference_accesses()

        # Check reduction clauses
        for (op, x) in d.clauses["reduction"]:
          if op in str_to_red_op:
              x_sig = Signature(x)
              if x_sig not in accesses:
                  StompLogger.add_message(
                      StompMessageCode.BadReductionClause,
                      description =
                          f"Found a reduction clause involving a variable "
                          f"'{x}' that is not referenced in the body of "
                          f"the directive.",
                      directive_node = d.original_directive)
              else:
                  seq = accesses[x_sig]

                  # Array reductions not yet supported
                  if any([is_array_access(info) for info in seq]):
                      StompLogger.add_message(
                          StompMessageCode.UnsupportedArrayReduction,
                          description =
                              f"Variable '{x}' is an array. Array reductions "
                              f"are not yet supported by the checker.",
                          directive_node = d.original_directive)
                      continue

                  # Check for valid reduction forms in loops
                  if not d.is_loop(): continue
                  red_infer = ReductionInferenceTool([str_to_red_op[op]])
                  red_clause = red_infer.attempt_reduction(x_sig, seq)
                  if not red_clause:
                      StompLogger.add_message(
                          StompMessageCode.BadReductionClause,
                          description =
                              f"Not all references to variable '{x}' "
                              f"are valid reduction forms involving the "
                              f"operator '{op}'.",
                          directive_node = d.original_directive)
          else:
              StompLogger.add_message(
                  StompMessageCode.BadReductionClause,
                  description =
                      f"Unrecognised reduction operator '{op}'.",
                  directive_node = d.original_directive)


# Parallel scalar access checks
# =============================


def check_parallel_scalar_accesses(psyir: Node):
    '''Various checks for scalar accesses within parallel directives.'''
    # Iterate over all accesses that are enclosed by parallel directive
    par_region = [["parallel"], ["teams"]]
    par_loop = [["do"], ["distribute"], ["simd"]]
    par = par_region + par_loop
    safe = [["critical"], ["atomic"], ["single"], ["master"]]
    for routine in psyir.walk(Routine):
        accesses = routine.reference_accesses()
        for (sig, seq) in accesses.items():
            for (i, info) in enumerate(seq):
                d = is_within_directive(info.node, par)

                # Write access to a shared variable must be protected
                bad = d and \
                      info.is_any_write() and \
                      not is_array_access(info) and \
                      d.is_shared_var(sig.var_name) and \
                      not is_within_directive(info.node, safe)
                if bad:
                    StompLogger.add_message(
                        StompMessageCode.ParallelScalarConflict,
                        description = f"Unprotected parallel write to shared "
                            f"variable '{sig.var_name}'.",
                        node = info.node,
                        directive_node = d.original_directive,
                        routine_name = routine.name)
                    break

                # Read of private (not firstprivate) scalar must
                # be initialised
                code = StompMessageCode.ReadUninitialisedPrivate
                if code not in StompLogger.ignore:
                    region = is_within_directive(info.node, par_region)
                    bad = d and \
                          info.is_any_read() and \
                          not is_array_access(info) and \
                          d.is_private_var(sig.var_name) and \
                          not d.is_firstprivate_var(sig.var_name) and \
                          not d.is_always_private(sig.var_name)
                    if bad:
                        # Look for preceeding initialiser
                        ok = False
                        for pre in reversed(seq[0:i]):
                            ok = pre.is_any_write() and \
                                     (region is None or
                                      is_child_directive(pre.node, region))
                            if ok: break
                        if not ok:
                            StompLogger.add_message(
                                StompMessageCode.ReadUninitialisedPrivate,
                                description = f"Parallel loop reads "
                                    f"uninitialised private variable "
                                    f"'{sig.var_name}'.",
                                node = info.node,
                                directive_node = d.original_directive,
                                routine_name = routine.name)
                            break


# Parallel array access checks
# ============================


def check_parallel_array_accesses(psyir: Node):
    '''Check all OpenMP teams/parallel regions for array access
    conflicts, where at least two accesses (one of which is a write)
    access the same indices of the same array in different threads.'''

    for routine in psyir.walk(Routine):
        for d in routine.walk(OpenMPDirective):
            if "end" in d.clauses: continue
            # Look for "teams" directives, or parallel directives not
            # enclosed by a "teams" directive
            ok = False
            if "teams" in d.clauses:
                ok = True
            elif "parallel" in d.clauses:
                enclosing = get_enclosing_directives(d)
                ok = all(["teams" not in e.clauses for e in enclosing])
            if not ok: continue

            # Apply the region conflict analysis
            analysis = RegionConflictAnalysis()
            conflicts = analysis.get_region_conflicts(d)
            for (sig, msg) in conflicts:
                if msg is None:
                    continue
                StompLogger.add_message(
                    StompMessageCode.ParallelArrayConflict,
                    description = "Array access conflict in "
                        "parallel region. " + msg + ".",
                    directive_node = d.original_directive,
                    routine_name = routine.name)


# SIMD loop checks
# ================


def check_simd_loops(psyir: Node):
    '''Check that 'simd' directives have non-conflicting loop iterations.
    The 'safelen' clause is not yet supported.'''
    for routine in psyir.walk(Routine):
        for d in routine.walk(OpenMPDirective):
            if "end" in d.clauses: continue
            if "simd" in d.clauses and "do" not in d.clauses:
                collapse = 1
                if "collapse" in d.clauses:
                    collapse = d.clauses["collapse"]
                outer_loop = d.get_singleton_body()
                all_loops = outer_loop.walk(Loop)
                loop_vars = [loop.variable.name for loop in all_loops]
                par_loops = all_loops[0:collapse]

                # Compute private variables
                private_vars = set(loop_vars)
                clauses = ["private", "firstprivate", "lastprivate"]
                for c in clauses:
                    if c in d.clauses:
                        private_vars.update(d.clauses[c])
                for (op, x) in d.clauses.get("reduction", []):
                    private_vars.add(x)

                # Analyse loop
                analysis = LoopConflictAnalysis()
                for loop in par_loops:
                    conflicts = analysis.get_loop_conflicts(loop,
                                    private=private_vars)
                    if conflicts:
                        StompLogger.add_message(
                            StompMessageCode.ParallelArrayConflict,
                            description = conflicts[0][1] + ".",
                            node = outer_loop,
                            directive_node = d.original_directive,
                            routine_name = routine.name)


# Impure call checks
# ==================


def check_impure_calls(d: OpenMPDirective, assume_pure: set[str] = set()):
    '''Report calls to impure functions/routines in parallel regions'''
    # Skip the check if we're just going to ignore it
    code = StompMessageCode.ImpureParallelCall
    if code in StompLogger.ignore: return

    # Scan calls in parallel regions
    is_parallel_region = "parallel" in d.clauses or "teams" in d.clauses
    if is_parallel_region:
        # Add names of functions/subroutines to ignore
        assume_pure.add("omp_get_team_num")
        assume_pure.add("omp_get_thread_num")
        assume_pure.add("omp_get_num_teams")
        assume_pure.add("omp_get_num_threads")
        region_body = d.get_body()
        if region_body:
            for stmt in region_body:
                for call in stmt.walk(Call):
                    name = call.routine.name

                    # Ignore specified calls
                    if name in assume_pure: continue

                    # Ignore intrinsic calls
                    if isinstance(call, IntrinsicCall): continue

                    # Ignore routines marked as "threadsafe"
                    if is_threadsafe(call.routine.symbol): continue

                    # Catch all remaining impure calls
                    if not call.is_pure:
                        StompLogger.add_message(
                            StompMessageCode.ImpureParallelCall,
                            description = f"Call to impure "
                                f"function/subroutine '{name}' in parallel "
                                f"region. Use the command-line option "
                                f"'--pure {name}' to assume that this call is "
                                f"pure or '-e ImpureParallelCall' to assume "
                                f"that all calls are pure.",
                            directive_node = d.original_directive,
                            node = call)
