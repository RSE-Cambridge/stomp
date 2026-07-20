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

'''This module provides a class to determine whether or not distinct
iterations of a given loop can generate conflicting array accesses (if
not, the loop can potentially be parallelised). It formulates the
problem as a set of SMT constraints over array indices which are then
are passed to the Z3 solver.'''

import z3
from typing import Optional, Tuple, Set
from psyclone.psyir.nodes import Loop, IntrinsicCall, Routine, Node
from psyclone.core import Signature
from stomp.array_index_analysis import \
    ArrayIndexAnalysisOptions, ArrayIndexAnalysis, ArrayAccess
from stomp.fortran_to_z3 import FortranToZ3
from stomp.openmp_directives import OpenMPDirective

# Analysis Options
# ================


class LoopConflictAnalysisOptions(ArrayIndexAnalysisOptions):
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

    :param check_scalars: whether to check scalar accesses as well as
       array accesses.
    '''
    def __init__(self,
                 int_width: int = 32,
                 use_bv: bool = None,
                 smt_timeout_ms: Optional[int] = 5000,
                 prohibit_overflow: bool = False,
                 handle_array_intrins: bool = True,
                 num_sweep_threads: int = 4,
                 sweep_seed: int = 1,
                 succeed_on_timeout: bool = False,
                 check_scalars: bool = False):
        super().__init__(int_width=int_width,
                         use_bv=use_bv,
                         prohibit_overflow=prohibit_overflow,
                         handle_array_intrins=handle_array_intrins,
                         check_scalars=check_scalars
                       )
        self.smt_timeout_ms = smt_timeout_ms
        self.num_sweep_threads = num_sweep_threads
        self.sweep_seed = sweep_seed
        self.succeed_on_timeout = succeed_on_timeout


# Analysis
# ========

class LoopConflictAnalysis(ArrayIndexAnalysis):
    '''The analysis class provides a method 'get_loop_conflicts()' to
    determine whether or not the array accesses in a given loop are
    conflicting between iterations. Two array accesses are conflicting
    if they access the same element of the same array in different loop
    iterations, and at least one is a write.

    The analysis assumes that any scalar integer or scalar logical
    variables written by the loop can safely be considered as private
    to each iteration. This should be validated by the callee and is
    typically done by DependencyTools.

    The basis of the analysis is inherited from ArrayIndexAnalysis, and
    additional behavior is introduced as described below.

    Given a loop, we find its enclosing routine, and start analysing the
    routine statement-by-statement in a recursive-descent fashion.

    When we encounter the loop of interest, we perform a couple of steps
    before recursing into the loop body. First, we kill all variables
    written by the loop body, because we don't know whether we are
    entering the loop (at run time) for the first time or not. Second,
    we create two SMT variables to represent the loop variables of two
    arbitary but distinct iterations of the loop. Each of these two
    variables is constrained to the start, stop, and step of the loop,
    and the two variables are constrained to be not equal. After that,
    we analyse the loop body twice, each time mapping the loop variable
    in the substitution to each of the SMT loop variables. After
    analysing the loop body for the first time, we save the array access
    list and start afresh with a new one. Therefore, once the analysis
    is complete, we have two array access lists, one for each iteration.

    When we encounter a loop that is not the loop of interest, we follow
    a similar approach but only consider a single arbitrary iteration of
    the loop.

    When the analysis is complete, we are left with two array
    access lists representing two different iterations of the same loop.
    A conflict occurs if there is an access to an array in the first
    list that can have the same array indices as an access to the same
    array in the second list, and one of which is a write.  This is
    determined by asserting an equality constraint between each access's
    indices which, when combined with the current condition of each
    access and the global constraint set, will be satisfiable if and
    only if there is a conflict.  In this way, we check every access
    pair and determine whether or not the loop contains conflicts.
    '''

    def __init__(self, options=LoopConflictAnalysisOptions()):
        '''This class provides a method 'get_loop_conflicts()' to
        determine whether or not distinct iterations of a given loop
        can generate conflicting array accesses.

        :param options: these options allow user control over features
           provided by, and choices made by, the analysis.
        '''
        self.opts = options

    def _init_analysis(self):
        '''Initialise the analysis by setting all the internal state
        variables accordingly.'''
        super()._init_analysis()
        # We record two access dicts, representing two arbitrary but distinct
        # iterations of the loop to parallelise
        self.saved_access_dicts = []
        # The SMT variables representing each loop iteration variable
        self.smt_loop_var_i = None
        self.smt_loop_var_j = None
        # For handling stomp 'unique' clauses (works similary to access dicts)
        self.saved_unique_lists = []
        self.unique_list = []

    def _save_access_dict(self):
        '''Move the current access dict to the stack, and proceed with
        an empty one.'''
        self.saved_access_dicts.append(self.access_dict)
        self.access_dict = {}
        # For handling stomp 'unique' clauses
        self.saved_unique_lists.append(self.unique_list)
        self.unique_list = []

    def get_loop_conflicts(self,
                           loop: Loop,
                           private: Set[str] = set(),
                           all_conflicts: bool = False) -> \
            list[Tuple[Signature, Optional[str]]]:
        '''Determine whether or not distinct iterations of the given loop
           can generate conflicting array accesses.

           :param loop: loop to be analysed.
           :param private: any access to an array variable in this set
              will not be considered as a potential conflict.
           :param all_conflicts: if True, enumerate all conflicts, otherwise
              stop after the first conflict. Defaults to False.
           :return: a list pairs array-name/message pairs. If the list
              is empty, the loop is conflict free. If the solver times out,
              the message is None.
        '''

        # Type checking
        if not isinstance(loop, Loop):
            raise TypeError("LoopConflictAnalysis: Loop argument expected")
        self.loop = loop

        # Find the enclosing routine
        routine = loop.ancestor(Routine)
        if not routine:
            raise ValueError(
                    "LoopConflictAnalysis: loop has no enclosing routine")
        self.routine = routine

        # Start with an empty constraint set and substitution
        self._init_analysis()
        self.loop_to_parallelise = loop
        self.private_vars = private

        # Resolve choice of integers v. bit vectors
        if self.opts.use_bv is None:
            for call in routine.walk(IntrinsicCall):
                i = call.intrinsic
                if i in [IntrinsicCall.Intrinsic.SHIFTL,
                         IntrinsicCall.Intrinsic.SHIFTR,
                         IntrinsicCall.Intrinsic.SHIFTA,
                         IntrinsicCall.Intrinsic.IAND,
                         IntrinsicCall.Intrinsic.IOR,
                         IntrinsicCall.Intrinsic.IEOR]:
                    self.opts.use_bv = True
                    break

        # Create Fortran-to-Z3 translator
        self.trans = FortranToZ3(
                         use_bv=self.opts.use_bv,
                         int_width=self.opts.int_width,
                         prohibit_overflow=self.opts.prohibit_overflow,
                         handle_array_intrins=self.opts.handle_array_intrins)

        # Initialise array intrinsic variables
        self._init_array_intrins_vars(routine)

        # Step through body of the enclosing routine, statement by statement
        for stmt in routine.children:
            self._step(stmt, z3.BoolVal(True))

        # Check that we have found and analysed the loop to parallelise
        if not (self.finished and len(self.saved_access_dicts) == 2):
            return None  # pragma: no cover

        # A list of conflicts to return
        conflicts = []

        # Add constraints for stomp 'unique' directives
        for (unique_i, unique_j) in zip(*self.saved_unique_lists):
            self._add_constraint(
                z3.Implies(z3.And(unique_i[0], unique_j[0]),
                           unique_i[1] != unique_j[1]))

        # Get the accesses pairs involving the same variable name
        candidates = self._get_candidate_conflicts()

        # We want to analyse scalar conflicts first, if there are any
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

    def _get_conflict(self, write: ArrayAccess, accs: list[ArrayAccess]) -> \
            Optional[Tuple[Signature, Optional[str]]]:
        '''Get the conflict between the write access 'write' and
           any access in 'accs', if there is one.

           :param write: a write access from one iteration.
           :param accs: a list of accesses from another iteration.
           :return: a pair containing an array name and a message string,
              if a conflict exists, and None otherwise. If the solver
              times out, the message is None.
        '''
        sum_of_prods = []
        for acc in accs:
            indices_equal = []
            for (i_idxs, j_idxs) in zip(write.indices, acc.indices):
                for (i_idx, j_idx) in zip(i_idxs, j_idxs):
                    indices_equal.append(i_idx == j_idx)
            sum_of_prods.append(indices_equal + [write.cond, acc.cond])

        # Invoke solver
        (result, result_values) = self.trans.solve(
            self.constraints,
            sum_of_prods,
            [self.smt_loop_var_i, self.smt_loop_var_j] +
            [ind for inds in write.indices for ind in inds],
            smt_timeout_ms = self.opts.smt_timeout_ms,
            num_sweep_threads = self.opts.num_sweep_threads,
            sweep_seed = self.opts.sweep_seed
            )

        # Determine return value
        (sig, sig_inds) = write.psyir_node.get_signature_and_indices()
        if result == z3.sat:
            # Produce message
            i_val = str(result_values.pop(0))
            j_val = str(result_values.pop(0))
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
            msg = (f"Iterations {i_val} and {j_val} have conflicting "
                   f"accesses to {access_str}")
            return (sig, msg)
        elif result == z3.unknown:  # pragma: no cover
            if self.opts.succeed_on_timeout:
                return None
            else:
                return (sig, None)
        else:
            return None

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

    def _step(self, stmt: Node, cond: z3.BoolRef):
        '''Analyse the given statement in recursive-descent fashion.'''

        # Has analysis finished?
        if self.finished:
            return

        # Loop
        if isinstance(stmt, Loop):
            # Kill variables written by loop body
            self._kill_all_written_vars(stmt.loop_body)
            # Kill loop variable
            self._kill_integer_var(stmt.variable.name)
            # Have we reached the loop we'd like to parallelise?
            if stmt is self.loop_to_parallelise:
                self.in_region_of_interest = True
                # Consider two arbitary but distinct iterations
                i_var = self._fresh_integer_var()
                j_var = self._fresh_integer_var()
                self._add_constraint(i_var != j_var)
                iteration_vars = [i_var, j_var]
                self.smt_loop_var_i = i_var
                self.smt_loop_var_j = j_var
            else:
                # Consider a single, arbitrary iteration
                i_var = self._fresh_integer_var()
                iteration_vars = [i_var]
            # Analyse loop body for each iteration variable separately
            for var in iteration_vars:
                self._save_subst()
                smt_loop_var = self._integer_var(stmt.variable.name)
                self.subst[smt_loop_var] = var
                # Introduce constraints on loop variable
                self._constrain_loop_var(
                    var, stmt.start_expr, stmt.stop_expr, stmt.step_expr)
                # Analyse loop body
                self._step(stmt.loop_body, cond)
                if stmt is self.loop_to_parallelise:
                    self._save_access_dict()
                self._restore_subst()
            # Record whether the analysis has finished
            if stmt is self.loop_to_parallelise:
                self.finished = True
            return

        # Stomp directive
        if isinstance(stmt, OpenMPDirective) and stmt.is_stomp_directive:
            # Add assumption
            if "unique" in stmt.clauses:
                expr = self._translate_integer_expr_with_subst(
                           stmt.clauses["unique"])
                self.unique_list.append((cond, expr))
                # Fall through

        super()._step(stmt, cond)
