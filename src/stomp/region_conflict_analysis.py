# -----------------------------------------------------------------------------
# BSD 3-Clause License
#
# Copyright (c) 2026, University of Cambridge, UK.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# -----------------------------------------------------------------------------
# Author: M. Naylor, University of Cambridge, UK
# -----------------------------------------------------------------------------

'''This module provides a class to check OpenMP parallel regions (teams,
distribute, parallel, do) for conflicting array accesses.  It formulates the
problem as a set of SMT constraints over array indices which are then are
passed to the Z3 solver.'''

import z3
from typing import Optional, Tuple, List
from psyclone.psyir.nodes import \
    Loop, IntrinsicCall, Routine, Node, Schedule, Statement
from psyclone.core import Signature, AccessInfo
from psyclone.psyir.symbols import TypedSymbol
from stomp.openmp_directives import \
    OpenMPDirective, drop_omp_dir_bodies, get_enclosing_directives, \
    get_sections
from stomp.array_index_analysis import \
    ArrayIndexAnalysisOptions, ArrayIndexAnalysis, ArrayAccess, \
    _is_scalar_integer, _is_scalar_logical
from stomp.fortran_to_z3 import FortranToZ3
from stomp.control_flow import \
    after_statement, next_statement, affects_control_flow

# Analysis Options
# ================


class RegionConflictAnalysisOptions(ArrayIndexAnalysisOptions):
    '''The analysis supports a range of different options, which are all
    captured together in this class.

    :param use_bv: whether to treat Fortran integers as bit vectors or
       arbitrary-precision integers. If None is specified then the
       analysis will use a simple heuristic to decide.

    :param int_width: the bit width of Fortran integers. This is 32 by
       default but it can be useful to reduce it to (say) 8 in particular
       cases to improve the ability of solver to find a timely solution,
       provided the user considers it safe to do so. (Note that the analysis
       currently only gathers information about Fortran integer values of
       unspecified width.)

    :param smt_timeout_ms: the time limit (in milliseconds) given to
       the SMT solver to find a solution. If the solver does not
       return within this time, the analysis will conservatively return
       that a conflict exists even though it has not yet found one.
       This can be set to 'None' to disable the timeout.

    :param prohibit_overflow: if True, the analysis will tell the solver
       to ignore the possibility of integer overflow. Integer overflow is
       undefined behaviour in Fortran so this is safe.

    :param handle_array_intrins: handle array intrinsics 'size()',
       'lbound()', and 'ubound()' specially. For example, multiple
       occurrences of 'size(arr)' will be assumed to return the same value,
       provided that those occurrences are not separated by a statement
       that may modify the size/bounds of 'arr'.

    :param num_sweep_threads: when larger than one, this option enables the
       sweeper, which runs multiple solvers across multiple threads with each
       one using a different constraint ordering (and potentially different
       solver parameters in future). This reduces the solver's sensitivity
       to the order of constraints.

    :param sweep_seed: the seed for the random number generator used
       by the sweeper.

    :param succeed_on_timeout: interpret a timeout as a non-conflict.
       This means that analysis may report no conflicts when there is one,
       but it will have tried to find one.

    '''
    def __init__(self,
                 int_width: int = 32,
                 use_bv: bool = None,
                 smt_timeout_ms: Optional[int] = 5000,
                 prohibit_overflow: bool = False,
                 handle_array_intrins: bool = True,
                 num_sweep_threads: int = 4,
                 sweep_seed: int = 1,
                 succeed_on_timeout: bool = False):
        super().__init__(int_width=int_width,
                         use_bv=use_bv,
                         prohibit_overflow=prohibit_overflow,
                         handle_array_intrins=handle_array_intrins)
        self.smt_timeout_ms = smt_timeout_ms
        self.num_sweep_threads = num_sweep_threads
        self.sweep_seed = sweep_seed
        self.succeed_on_timeout = succeed_on_timeout


# Analysis
# ========

class RegionConflictAnalysis(ArrayIndexAnalysis):
    '''This class provides a method 'get_region_conflicts()' to
    determine whether or not the array accesses in a given parallel region
    are conflicting between teams/threads. Two array accesses are conflicting
    if they access the same element of the same array in different
    teams/threads, and at least one is a write.

    The analysis assumes that any scalar integer or scalar logical
    variables written by the loop can safely be considered as private
    to each iteration. This should be validated by the callee.

    The basis of the analysis is inherited from ArrayIndexAnalysis. This base
    analysis is extended consider two arbitrary but distinct threads executing
    inside each teams/parallel reigon, and to look for array-access conflicts
    between the two. Two threads are considered distinct if that have different
    thread ids or different team ids.  '''

    def __init__(self, options=RegionConflictAnalysisOptions()):
        '''This class provides a method 'get_region_conflicts()' to
        determine whether or not distinct teams/threads in a given
        region generate conflicting array accesses.

        :param options: these options allow user control over features
           provided by, and choices made by, the analysis.
        '''
        self.opts = options
        self.opts.check_scalars = True

    def _init_analysis(self):
        '''Initialise the analysis by setting all the internal state
        variables accordingly.'''
        super()._init_analysis()
        # Are we analysing a "teams" region?
        self.is_teams_region = False
        # Are we inside a "parallel" region?
        self.inside_parallel = False
        # Variables known to be private to each team
        self.team_private_vars = []
        # Variables known to be private to each thread
        self.thread_private_vars = []
        # The SMT variable holding the team id
        self.smt_team_var = None
        self.smt_team_var_i = None
        self.smt_team_var_j = None
        # The SMT variable holding the thread id within the team
        self.smt_thread_var = None
        self.smt_thread_var_i = None
        self.smt_thread_var_j = None
        # The SMT variable holding the number of threads
        self.smt_num_threads_var = None
        # List of loop variable tuples for "do"/"distibute" loops
        self.parallel_do_vars = None
        self.distribute_vars = None
        # The number of loops immediately expected for a "do"/"distibute" loop
        self.collapse_do = 0
        self.collapse_distribute = 0
        # We record two access dicts, representing two arbitrary but distinct
        # threads executing in the region
        self.saved_access_dicts = []
        # The condition around the statment of interest
        self.region_cond = None

    def _save_access_dict(self):
        '''Move the current access dict to the stack, and proceed with
        an empty one.'''
        self.saved_access_dicts.append(self.access_dict)
        self.access_dict = {}

    def _add_array_access(self, array_name: str, access: ArrayAccess):
        '''Override parent method: add an array access to the current
        access dict.'''
        # Ignore accesses outside region of interest
        if not self.in_region_of_interest:
            return
        # Ignore accesses to thread-private variables
        if array_name in self.thread_private_vars:
            return
        # If we are not inside a "parallel" region then constrain the
        # thread id to zero as only the master thread is active
        if not self.inside_parallel:
            access._cond = z3.And(access._cond, self.smt_thread_var == 0)
        # For team-private variables, the two threads must be in the same
        # team for there to be a conflict
        if array_name in self.team_private_vars:
            access._cond = z3.And(access._cond,
                                  self.smt_team_var_i == self.smt_team_var_j)
            access._is_team_private = True
        # If not analysing a teams region, every array is team-private
        if not self.is_teams_region:
            access._is_team_private = True
        # Call parent method with possibly-modified access
        super()._add_array_access(array_name, access)

    def _kill_scalar_vars(self, vs: List[str]):
        '''Kill the scalar variables in the given list of variables.'''
        for v in vs:
            sym = self.routine.symbol_table.lookup(v, otherwise=None)
            if sym is None: continue
            if isinstance(sym, TypedSymbol):
                if _is_scalar_integer(sym.datatype):
                    self._kill_integer_var(v)
                elif _is_scalar_logical(sym.datatype):
                    self._kill_logical_var(v)

    def get_region_conflicts(self,
                             region: OpenMPDirective,
                             all_conflicts: bool = False) -> \
            list[Tuple[Signature, Optional[str]]]:
        '''Determine whether or not distinct threads of the given region
           can generate conflicting array accesses.

           :param region: region to be analysed.
           :param all_conflicts: if True, enumerate all conflicts, otherwise
              stop after the first conflict. Defaults to False.
           :return: a list pairs array-name/message pairs. If the list
              is empty, the loop is conflict free. If the solver times out,
              the message is None.
        '''

        # Type checking
        if not isinstance(region, OpenMPDirective):
            raise TypeError("RegionConflictAnalysis: "
                            "Expected OpenMP directive.")
        is_teams_region = "teams" in region.clauses
        is_par_region = "parallel" in region.clauses
        if not (is_teams_region or is_par_region):
            raise TypeError("RegionConflictAnalysis: "
                            "Expected 'teams' or 'parallel' region.")
        region_body = region.get_body()

        # Find the enclosing routine
        routine = region.ancestor(Routine)
        if not routine:
            raise ValueError(
                    "RegionConflictAnalysis: region has no enclosing routine")
        self.routine = routine

        # Start with an empty constraint set and substitution
        self._init_analysis()
        self.region_of_interest = region
        self.is_teams_region = is_teams_region

        # Resolve choice of integers v. bit vectors
        if self.opts.use_bv is None:
            for stmt in region_body:
                for call in stmt.walk(IntrinsicCall):
                    i = call.intrinsic
                    if i in [IntrinsicCall.Intrinsic.SHIFTL,
                             IntrinsicCall.Intrinsic.SHIFTR,
                             IntrinsicCall.Intrinsic.SHIFTA,
                             IntrinsicCall.Intrinsic.IAND,
                             IntrinsicCall.Intrinsic.IOR,
                             IntrinsicCall.Intrinsic.IEOR]:
                        self.opts.use_bv = True
                        break
                if self.opts.use_bv:
                    break

        # Create Fortran-to-Z3 translator
        self.trans = FortranToZ3(
                         use_bv=self.opts.use_bv,
                         int_width=self.opts.int_width,
                         prohibit_overflow=self.opts.prohibit_overflow,
                         handle_array_intrins=self.opts.handle_array_intrins)

        # Initialise array intrinsic variables
        self._init_array_intrins_vars(routine)

        # Find region of interest
        for stmt in routine.children:
            self._step(stmt, z3.BoolVal(True))
        if not self.in_region_of_interest:
            raise RuntimeError("RegionConflictAnalysis: could not find "
                "region of interest in routine.")
        self.finished = False

        # Consider two arbitary but distinct threads entering the region.
        # For each one, the team id or thread id must differ, but the two
        # threads can be in the same team or have the same thread id in
        # different teams
        smt_team_var_i = self._fresh_integer_var()
        smt_team_var_j = self._fresh_integer_var()
        self.smt_team_var_i = smt_team_var_i
        self.smt_team_var_j = smt_team_var_j
        smt_thread_var_i = self._fresh_integer_var()
        smt_thread_var_j = self._fresh_integer_var()
        self.smt_thread_var_i = smt_thread_var_i
        self.smt_thread_var_j = smt_thread_var_j
        self._add_constraint(z3.Or(smt_team_var_i != smt_team_var_j,
                                   smt_thread_var_i != smt_thread_var_j))

        # Variables holding the number of teams/threads
        smt_num_teams_var = self._fresh_integer_var()
        smt_num_threads_var = self._fresh_integer_var()
        self.smt_num_threads_var = smt_num_threads_var

        # Bounds on variables
        self._add_constraint(smt_team_var_i >= 0)
        self._add_constraint(smt_team_var_j >= 0)
        self._add_constraint(smt_thread_var_i >= 0)
        self._add_constraint(smt_thread_var_j >= 0)
        self._add_constraint(smt_num_teams_var > 0)
        self._add_constraint(smt_num_threads_var > 0)
        if "num_teams" in region.clauses:
            n = self._translate_integer_expr_with_subst(
                    region.clauses["num_teams"])
            self._add_constraint(smt_num_teams_var == n)
            self._add_constraint(smt_team_var_i < n)
            self._add_constraint(smt_team_var_j < n)
        if "thread_limit" in region.clauses:
            n = self._translate_integer_expr_with_subst(
                    region.clauses["thread_limit"])
            self._add_constraint(smt_num_threads_var <= n)
            self._add_constraint(smt_thread_var_i < n)
            self._add_constraint(smt_thread_var_j < n)

        # Constrain team to 0 if no teams directive present
        if "teams" not in region.clauses:
            self._add_constraint(smt_team_var_i == 0)
            self._add_constraint(smt_team_var_j == 0)
            self._add_constraint(smt_num_teams_var == 1)

        # Handle omp_get_num_teams() and omp_get_num_threads()
        self.trans.add_custom_call_mapping(
            "omp_get_num_teams", smt_num_teams_var)
        self.trans.add_custom_call_mapping(
            "omp_get_num_threads", smt_num_threads_var)

        # Hold the 'parallel_do_vars' and 'distribute_vars' for two
        # arbitary but distinct threads in the region
        parallel_do_vars_per_thread = []
        distribute_vars_per_thread = []

        # Analyse the region twice, once for each of the two threads
        for thread in ["i", "j"]:
            # Handle omp_get_thread_num() and omp_get_team_num()
            if thread == "i":
                self.trans.add_custom_call_mapping(
                    "omp_get_thread_num", smt_thread_var_i)
                self.trans.add_custom_call_mapping(
                    "omp_get_team_num", smt_team_var_i)
                self.smt_thread_var = smt_thread_var_i
                self.smt_team_var = smt_team_var_i
            else:
                self.trans.add_custom_call_mapping(
                    "omp_get_thread_num", smt_thread_var_j)
                self.trans.add_custom_call_mapping(
                    "omp_get_team_num", smt_team_var_j)
                self.smt_thread_var = smt_thread_var_j
                self.smt_team_var = smt_team_var_j
            # Variables known to be private to each team
            self.team_private_vars = []
            # Variables known to be private to each thread
            self.thread_private_vars = []
            # Other initialisation
            self.parallel_do_vars = []
            self.distribute_vars = []
            # Analyse region
            self._step(region, self.region_cond)
            # Save results of analysis
            parallel_do_vars_per_thread.append(self.parallel_do_vars)
            distribute_vars_per_thread.append(self.distribute_vars)
            self._save_access_dict()

        # Constrain each thread's 'parallel_do_vars' tuples to be
        # not equal, if each thread's thread_id is not equal
        diff_threads = smt_thread_var_i != smt_thread_var_j
        for (info_i, info_j) in zip(*parallel_do_vars_per_thread):
            if not (info_i.distinct and info_j.distinct): continue
            diff_tuples = z3.Or(
                [i.var != j.var for (i, j) in
                    zip(info_i.loop_infos, info_j.loop_infos)])
            self._add_constraint(
                z3.Implies(z3.And(info_i.cond, info_j.cond, diff_threads),
                           diff_tuples))

        # Constrain each thread's 'distribute_vars' tuples to be
        # not equal, if each thread's team_id is not equal
        diff_teams = smt_team_var_i != smt_team_var_j
        for (info_i, info_j) in zip(*distribute_vars_per_thread):
            diff_tuples = z3.Or(
                [i.var != j.var for (i, j) in
                    zip(info_i.loop_infos, info_j.loop_infos)])
            self._add_constraint(
                z3.Implies(z3.And(info_i.cond, info_j.cond, diff_teams),
                           diff_tuples))

        # Add constraints to ensure consistent scheduling of statically
        # schedule loops
        self._consistent_loop_scheduling(
            parallel_do_vars_per_thread[0],
            parallel_do_vars_per_thread[1],
            diff_threads)
        self._consistent_loop_scheduling(
            distribute_vars_per_thread[0],
            distribute_vars_per_thread[1],
            diff_teams)

        # Get the accesses pairs involving the same variable name
        candidates = self._get_candidate_conflicts()

        # We want to analyse scalar conflict first, if there are any
        scalar_candidates = []
        array_candidates = []
        for (i_accesses, j_accesses) in candidates:
            if any([i_acc.is_scalar for i_acc in i_accesses]):
                scalar_candidates.append((i_accesses, j_accesses))
            else:
                array_candidates.append((i_accesses, j_accesses))

        conflicts = self._get_conflicts(scalar_candidates, all_conflicts)
        if not conflicts or all_conflicts:
            conflicts += self._get_conflicts(array_candidates, all_conflicts)
        return conflicts

    def _get_candidate_conflicts(self) -> \
            list[Tuple[list[ArrayAccess], list[ArrayAccess]]]:
        '''Get the candidate conflicts (acceses to the same variable).'''
        candidates = []
        thread_i = self.saved_access_dicts[0]
        thread_j = self.saved_access_dicts[1]
        for (i_arr_name, i_accesses) in thread_i.items():
            for (j_arr_name, j_accesses) in thread_j.items():
                if (i_arr_name == j_arr_name or
                        i_arr_name.startswith(j_arr_name + "%") or
                        j_arr_name.startswith(i_arr_name + "%")):
                    candidates.append((i_accesses, j_accesses))
        return candidates

    def _get_conflicts(self,
                       candidates: list[Tuple[list[ArrayAccess],
                                              list[ArrayAccess]]],
                       all_conflicts: bool) -> \
            Optional[Tuple[Signature, Optional[str]]]:
        '''Get the conflicts in the given conflict candidates.'''
        conflicts = []
        # Formulate constraints for solving, considering the two threads
        for (i_accesses, j_accesses) in candidates:
            # For each write access in the i iteration
            for i_access in i_accesses:
                if i_access.is_write:
                    conflict = self._get_conflict(i_access, j_accesses)
                    if conflict:
                        conflicts.append(conflict)
                        if not all_conflicts:
                            return conflicts
        return conflicts

    def _get_conflict(self, write: ArrayAccess, accs: list[ArrayAccess]) -> \
            Optional[Tuple[Signature, Optional[str]]]:
        '''Get the conflict between the write access 'write' and
           any access in 'accs', if there is one.

           :param write: a write access from one thread.
           :param accs: a list of accesses from another thread.
           :return: a pair containing an array name and a message string,
              if a conflict exists, and None otherwise. If the solver
              times out, the message is None.
        '''
        sum_of_prods = []
        for acc in accs:
            if self._needs_conflict_check(write, acc):
                indices_equal = []
                for (i_idxs, j_idxs) in zip(write.indices, acc.indices):
                    for (i_idx, j_idx) in zip(i_idxs, j_idxs):
                        indices_equal.append(i_idx == j_idx)
                sum_of_prods.append(indices_equal + [write.cond, acc.cond])

        # Invoke solver
        (result, result_values) = self.trans.solve(
            self.constraints,
            sum_of_prods,
            [self.smt_team_var_i, self.smt_team_var_j,
                 self.smt_thread_var_i, self.smt_thread_var_j] +
            [ind for inds in write.indices for ind in inds],
            smt_timeout_ms = self.opts.smt_timeout_ms,
            num_sweep_threads = self.opts.num_sweep_threads,
            sweep_seed = self.opts.sweep_seed
            )

        # Determine return value
        (sig, sig_inds) = write.psyir_node.get_signature_and_indices()
        if result == z3.sat:
            # Produce message
            team_i = str(result_values.pop(0))
            team_j = str(result_values.pop(0))
            thread_i = str(result_values.pop(0))
            thread_j = str(result_values.pop(0))
            components = []
            sig_fields = [sig[i] for i in range(len(sig))]
            for (field, inds) in zip(sig_fields, sig_inds):
                vals = []
                for ind in inds:
                    if result_values:
                        vals.append(str(result_values.pop(0)))
                if vals:
                    components.append(field + '(' + ','.join(vals) + ')')
                else:
                    components.append(field)
            access_str = '%'.join(components)
            msg = (f"Thread (team={team_i},thread={thread_i}) and thread "
                   f"(team={team_j},thread={thread_j}) have conflicting "
                   f"accesses to {access_str}")
            return (sig, msg)
        elif result == z3.unknown:  # pragma: no cover
            if self.opts.succeed_on_timeout:
                return None
            else:
                return (sig, None)
        else:
            return None

    def _step(self, stmt: Node, cond: z3.BoolRef):
        '''Analyse the given statement in recursive-descent fashion.'''

        # Has analysis finished?
        if self.finished:
            return

        # Look for region of interest
        if (not self.in_region_of_interest and
                isinstance(stmt, OpenMPDirective) and
                stmt is self.region_of_interest):
            self.in_region_of_interest = True
            self.region_cond = cond
            self.finished = True
            return

        # Schedule
        if isinstance(stmt, Schedule):
            for child in drop_omp_dir_bodies(stmt.children):
                self._step(child, cond)
            return

        # Loop
        if isinstance(stmt, Loop):
            # Kill variables written by loop body
            self._kill_all_written_vars(stmt.loop_body)
            # Kill loop variable
            self._kill_integer_var(stmt.variable.name)
            # Introduce constraints on loop variable
            var = self._fresh_integer_var()
            self._save_subst()
            smt_loop_var = self._integer_var(stmt.variable.name)
            self.subst[smt_loop_var] = var
            (loop_start, loop_stop, loop_step) = \
                self._constrain_loop_var(
                    var, stmt.start_expr, stmt.stop_expr, stmt.step_expr)
            loop_info = LoopInfo(var, loop_start, loop_stop, loop_step)
            # Record OpenMP "do" and "distribute" loop variables
            if self.collapse_do > 0:
                self.parallel_do_vars[-1].loop_infos.append(loop_info)
                self.collapse_do -= 1
            if self.collapse_distribute > 0:
                self.distribute_vars[-1].loop_infos.append(loop_info)
                self.collapse_distribute -= 1
            # Analyse loop body
            self._step(stmt.loop_body, cond)
            self._restore_subst()
            return

        if (self.in_region_of_interest and
                isinstance(stmt, OpenMPDirective)):
            # Save some state that needs to be restored after analysing
            # the directive's body
            save_inside_parallel = self.inside_parallel
            save_thread_private_vars = self.thread_private_vars.copy()
            save_team_private_vars = self.team_private_vars.copy()
            self._save_subst()

            # Track private variables for the region
            if ("teams" in stmt.clauses or
                    "parallel" in stmt.clauses):
                region_vars = stmt.get_private_shared_red()
                region_private_vars = list(
                    region_vars[0] | {red[1] for red in region_vars[2]}
                                   | stmt.get_always_private())
                if "parallel" in stmt.clauses:
                    self.thread_private_vars = region_private_vars.copy()
                    self.private_vars = self.thread_private_vars
                elif "teams" in stmt.clauses:
                    self.team_private_vars = region_private_vars.copy()
                    self.private_vars = self.team_private_vars
                # We might considering killing private (but not
                # firstprivate) variables here, however, other checks
                # should catch use of uninitialised privates
                # self._kill_scalar_vars(region_private_vars)
            else:
                new_private_vars = []
                if "private" in stmt.clauses:
                    new_private_vars.extend(stmt.clauses["private"])
                if "reduction" in stmt.clauses:
                    new_private_vars.extend(
                        [red[1] for red in stmt.clauses["reduction"]])
                if "do" in stmt.clauses:
                    self.thread_private_vars.extend(new_private_vars)
                elif "sections" in stmt.clauses:
                    self.thread_private_vars.extend(new_private_vars)
                elif "distribute" in stmt.clauses:
                    self.team_private_vars.extend(new_private_vars)
                # We might considering killing private (but not
                # firstprivate) variables here, however, other checks
                # should catch use of uninitialised privates
                # self._kill_scalar_vars(new_private_vars)

            # Track whether or nor we are inside a "parallel" region
            if "parallel" in stmt.clauses:
                self.inside_parallel = True
                # Constrain the number of threads, if specified
                if "num_threads" in stmt.clauses:
                    n = self._translate_integer_expr_with_subst(
                            stmt.clauses["num_threads"])
                    cond = z3.And(cond, self.smt_num_threads_var == n)
                    cond = z3.And(cond, self.smt_thread_var < n)
            # Handle "master" directive
            if "master" in stmt.clauses:
                cond = z3.And(cond, self.smt_thread_var == 0)
            # Handle "single" directive
            if "single" in stmt.clauses:
                # Create a fresh logical variable and add it to the condition
                active = self._fresh_logical_var()
                cond = z3.And(cond, active)
                # Require each thread's variable to be different
                # For convenience, this is done via 'parallel_do_vars'
                var_info = CollapsedLoopInfo(stmt, [LoopInfo(active)])
                self.parallel_do_vars.append(var_info)
            # Handle loop directives
            if "do" in stmt.clauses:
                self.collapse_do = stmt.clauses.get("collapse", 1)
                self.parallel_do_vars.append(CollapsedLoopInfo(stmt, []))
            if "distribute" in stmt.clauses:
                self.collapse_distribute = stmt.clauses.get("collapse", 1)
                self.distribute_vars.append(CollapsedLoopInfo(stmt, []))
            # Handle 'sections' directive
            if "sections" in stmt.clauses:
                sections = get_sections(stmt)
                if sections:
                    # We model "sections" like a parallel loop whose
                    # body contains an "if" for each section
                    zero = self._integer_val(0)
                    num_sections = self._integer_val(len(sections))
                    section_id = self._fresh_integer_var()
                    self._add_constraint(section_id >= zero)
                    self._add_constraint(section_id < num_sections)
                    # Iterate over sections
                    for (i, section) in enumerate(sections):
                       i_val = self._integer_val(i)
                       self._save_subst()
                       section_cond = z3.And(cond, section_id == i_val)
                       for s in drop_omp_dir_bodies(section):
                           self._step(s, section_cond)
                       self._restore_subst()
                    # Require each thread's section_id to be different.
                    # For convenience, this is done via 'parallel_do_vars'
                    self.parallel_do_vars.append(
                        CollapsedLoopInfo(stmt, [LoopInfo(section_id)]))
            # Handle stomp 'unique' directive
            if stmt.is_stomp_directive and "unique" in stmt.clauses:
                # Compile expression
                expr = self._translate_integer_expr_with_subst(
                           stmt.clauses["unique"])
                # Require each thread's expression to be different.
                # For convenience, this is done via 'parallel_do_vars'
                self.parallel_do_vars.append(
                    CollapsedLoopInfo(stmt, [LoopInfo(expr)], cond=cond))
                return

            # Analyse region body
            if "sections" not in stmt.clauses:
                region_body = stmt.get_body()
                if region_body:
                    for s in drop_omp_dir_bodies(region_body):
                        self._step(s, cond)

            # Restore state before continuing
            self.inside_parallel = save_inside_parallel
            self.thread_private_vars = save_thread_private_vars
            self.team_private_vars = save_team_private_vars
            self._restore_subst()
            return

        super()._step(stmt, cond)

    @staticmethod
    def _needs_conflict_check(access_from: AccessInfo,
                              access_to: AccessInfo) -> bool:
        '''Determine wheter or not we need to check for a conflict
        between the two given accesses'''
        node_from = access_from.psyir_node
        node_to = access_to.psyir_node
        enclosing_from = get_enclosing_directives(node_from)
        enclosing_to = get_enclosing_directives(node_to)

        # Return false if both nodes are enclosed by an "atomic" directive
        from_atomic = any(["atomic" in d.clauses for d in enclosing_from])
        to_atomic = any(["atomic" in d.clauses for d in enclosing_to])
        if from_atomic and to_atomic: return False

        # Return false if both nodes are enclosed by an "ordered" directive
        from_ord = any(["ordered" in d.clauses and "do" not in d.clauses
                        for d in enclosing_from])
        to_ord = any(["ordered" in d.clauses and "do" not in d.clauses
                      for d in enclosing_to])
        if from_ord and to_ord: return False

        # If we are in a teams region but accessing a non-team-private
        # array then return True because "crtical" and "barrier" only
        # prevent conflicts within a team not between teams
        if (not (access_from._is_team_private and
                 access_to._is_team_private)):
            return True

        # Return false if both nodes are enlosed by a "critical" directive
        # with the same name
        from_critical = [d.clauses["critical"]
                         for d in enclosing_from if "critical" in d.clauses]
        to_critical = [d.clauses["critical"]
                       for d in enclosing_to if "critical" in d.clauses]
        if set(from_critical) & set(to_critical): return False

        # If both nodes are inside a "parallel" region then we only
        # need to check for a conflict if there is a path from the
        # first to the second that does not pass through an
        # explicit or implicit OpenMP barrier.
        def is_parallel(d: OpenMPDirective) -> bool:
            return "parallel" in d.clauses
        from_par = any([is_parallel(d) for d in enclosing_from])
        to_par = any([is_parallel(d) for d in enclosing_to])
        if from_par and to_par:
            stmt_from = node_from.ancestor(Statement)
            stmt_to = node_to.ancestor(Statement)
            if stmt_from and stmt_to:
                return barrier_free_path(stmt_from, stmt_to) or \
                       barrier_free_path(stmt_to, stmt_from)

        return True

    # For parallel loops with a static schedule and the same
    # iteration space, programmers can rely on a consistent mapping
    # from loop variable to thread id. This methods adds constraints
    # to ensure this.
    def _consistent_loop_scheduling(
            self, parallel_loop_vars_i, parallel_loop_vars_j, diff_threads):
        for (i, info_i) in enumerate(parallel_loop_vars_i):
            if info_i.is_static:
                for (j, info_j) in enumerate(parallel_loop_vars_j):
                    if i != j and info_j.is_static:
                        diff_tuples = z3.Or(
                            [i.var != j.var for (i, j) in
                                zip(info_i.loop_infos, info_j.loop_infos)])
                        same_space = z3.And(
                            [z3.And(i.begin == j.begin,
                                    i.end == j.end,
                                    i.step == j.step) for (i, j) in
                                zip(info_i.loop_infos, info_j.loop_infos)])
                        self._add_constraint(z3.Implies(z3.And(
                            diff_threads, same_space), diff_tuples))


# Helpers
# =======


# Type holding info about loops
class LoopInfo:
    def __init__(self, var: z3.ExprRef,
                       begin: z3.ExprRef = None,
                       end: z3.ExprRef = None,
                       step: z3.ExprRef = None):
        self.var = var
        self.begin = begin
        self.end = end
        self.step = step


# Type holding info about collapsed loops
class CollapsedLoopInfo:
    def __init__(self,
                 d: OpenMPDirective,
                 loop_infos: List[LoopInfo],
                 cond: z3.BoolRef = z3.BoolVal(True)):
        self.loop_infos = loop_infos
        # Add condition guard for the loop
        self.cond = cond
        # Is it a statically scheduled construct?
        self.is_static = "schedule" in d.clauses and \
                         d.clauses["schedule"] is not None and \
                         d.clauses["schedule"][1] == "static"
        self.is_static = self.is_static or "distribute" in d.clauses
        # Do different thread ids imply distinct loop variable values?
        self.distinct = True
        is_nowait = False
        if d.ended_by is not None and "nowait" in d.ended_by.clauses:
            is_nowait = True
        is_lone_do = "do" in d.clauses and "parallel" not in d.clauses
        if is_lone_do and is_nowait and not self.is_static:
            body = d.get_singleton_body()
            for stmt in after_statement(body):
                if barrier_free_path(stmt, body):
                    self.distinct = False
                    break

def barrier_free_path(stmt_from: Statement, stmt_to: Statement) -> bool:
    '''Is there a path from the first statement to the second that does
    not pass through an explicit or implicit OpenMP barrier? It is assumed
    that both statements reside inside the same OpenMP parallel region.'''
    visited = set()
    stack = [stmt_from]
    while stack:
        s = stack.pop()
        if id(s) in visited: return False
        visited.add(id(s))
        if s is stmt_to: return True
        if isinstance(s, OpenMPDirective):
            if "barrier" in s.clauses: continue
            if "end" in s.clauses:
                if "parallel" in s.clauses: continue
                if "nowait" not in s.clauses and \
                       ("do" in s.clauses or
                        "single" in s.clauses or
                        "workshare" in s.clauses or
                        "sections" in s.clauses):
                    continue
        elif not affects_control_flow(s):
            for child in s.walk(Statement):
                if child is stmt_to: return True
        for succ in next_statement(s):
            if id(succ) not in visited:
                stack.append(succ)
    return False
