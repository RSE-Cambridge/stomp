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

'''This module provides a base class to support analysis of array accesses in a
given block of code. For each array access, it provides a list of array
indices represented as SMT formulae and a condition represented as an SMT
constraint. This allows the use of an SMT solver to answer questions about
array accesses, such as whether or they can safely execute in parallel.'''

import z3
from psyclone.psyir.nodes import Loop, DataNode, Literal, Assignment, \
    Reference, IntrinsicCall, \
    Routine, Node, IfBlock, Schedule, Range, WhileLoop, \
    CodeBlock
from psyclone.core import Signature
from psyclone.psyir.symbols import DataType, ScalarType, ArrayType
from fparser.two import Fortran2003, Fortran2008
from stomp.misc import if_else_chain
from stomp.openmp_directives import OpenMPDirective


# Analysis Options
# ================


class ArrayIndexAnalysisOptions:
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

    :param prohibit_overflow: if True, the analysis will tell the solver
       to ignore the possibility of integer overflow. Integer overflow is
       undefined behaviour in Fortran so this is safe.

    :param handle_array_intrins: handle array intrinsics 'size()',
       'lbound()', and 'ubound()' specially. For example, multiple
       occurrences of 'size(arr)' will be assumed to return the same value,
       provided that those occurrences are not separated by a statement
       that may modify the size/bounds of 'arr'.

    :param check_scalars: whether to check for scalar access conflicts
       as well as array access conflicts.

    '''
    def __init__(self,
                 int_width: int = 32,
                 use_bv: bool = None,
                 prohibit_overflow: bool = False,
                 handle_array_intrins: bool = True,
                 check_scalars: bool = False):
        self.int_width = int_width
        self.use_bv = use_bv
        self.prohibit_overflow = prohibit_overflow
        self.handle_array_intrins = handle_array_intrins
        self.check_scalars = check_scalars


# Array access type
# =================


class ArrayAccess:
    '''This class is used to record details of each array access
    encountered during the analysis.

    :param name: name of the variable being accesses.
    :param cond: a boolean SMT expression representing the current
       condition at the point the array access is made.
    :param is_write: whether the access is a read or a write.
    :param indices: SMT integer expressions representing the
      indices of the array access.
    :param psyir_node: PSyIR node for the access (useful for reporting
       conflict messages / errors).
    :param is_team_private: is it an access to a team-private array?
    :param is_scalar: is it an access to a scalar rather than an array?
    '''
    def __init__(self,
                 name:             Signature,
                 cond:             z3.BoolRef,
                 is_write:         bool,
                 indices:          list[list[z3.ExprRef]],
                 psyir_node:       Node,
                 is_team_private:  bool = False,
                 is_scalar:        bool = False,
                 no_self_conflict: bool = False):
        self.name = name
        self.cond = cond
        self.is_write = is_write
        self.indices = indices
        self.psyir_node = psyir_node
        self.is_team_private = is_team_private
        self.is_scalar = is_scalar
        self.no_self_conflict = no_self_conflict


# Analysis
# ========

class ArrayIndexAnalysis:
    '''This base class supports analysing array accesses in the given code.
    For each array access, it provides a list of array indices represented
    as SMT formulae and a condition represented as an SMT constraint. This
    allows the use of an SMT solver to answer questions about array accesses,
    such as whether or they can safely execute in parallel.

    Given a block of code, we step through the code statement-by-statement
    in a recursive-descent fashion.

    As we proceed, we maintain a set of SMT constraints and a
    substitution that maps Fortran variable names to SMT variable names.
    For each Fortran variable, the substitution points to an SMT
    variable that is constrained (in the set of constraints) such that
    it captures the value of the Fortran variable at the current point
    in the code. When a Fortran variable is updated, the substitution is
    modified to point to a fresh SMT variable, with new constraints,
    without destroying the old constraints.

    More concretely, when we encounter an assignment of a scalar
    integer/logical variable, of the form 'x = rhs', we translate 'rhs'
    to the SMT formula 'smt_rhs' with the current substitution applied.
    We then add a constraint 'var = smt_rhs' where 'var' is a fresh SMT
    variable, and update the substitution so that 'x' maps to 'var'.

    The Fortran-expression-to-SMT translator knows about several Fortran
    operators and intrinsics, but not all of them; when it sees
    something it doesn't know about, it simply translates it to a fresh
    unconstrained SMT variable.

    Sometimes we reach a statement that modifies a Fortran variable in
    an unknown way (e.g. calling a subroutine). This can be handled by
    updating the substitution to point to a fresh unconstrained SMT
    variable; we refer to this process as "killing" the variable.

    In addition to the current substitution, we maintain a stack of
    previous substitutions. This allows substitutions to be saved and
    restored before and after analysing a block of code that may or may
    not be executed at run time.

    We also maintain a "current condition". This can be viewed as a
    constraint that has not been committed to the constraint set because
    we want to be able to grow, contract, and retract it as we enter and
    exit conditional blocks of code. This current condition is passed in
    recursive calls, so there is an implicit stack of them.

    More concretely, when we encounter an 'if' statement, we copy the
    current substitution onto the stack, then recurse into the 'then'
    body, passing in the 'if' condition as an argument, and then restore
    the old substitution. We do the same for the 'else' body if there is
    one (in this case the negated condition is passed to the recursive
    call). Finally, we kill all variables written by the 'then' and
    'else' bodies, because we don't know which will be executed at run
    time. (In future, we could do better here by introducing OR
    constraints, e.g. each variable written is either equal to the value
    written in the 'then' OR the 'else' depending on the condition.)

    As the analysis proceeds, we also maintain a list of array accesses.
    For each access, we record various information including the name of
    the array, whether it is a read or a write, the current condition at
    the point the access is made, and its list of indices (translated to
    SMT).

    When we encounter a loop, we perform a couple of steps
    before recursing into the loop body. First, we kill all variables
    written by the loop body, because we don't know whether we are
    entering the loop (at run time) for the first time or not. Second,
    we constrain the loop variable to the start, stop, and step of the loop.

    When the recursive descent is complete, we are left with a list of
    array access in a form that can be reasoned about using an SMT solver.
    '''

    def __init__(self, options=ArrayIndexAnalysisOptions()):
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

        # The substitution maps integer and logical Fortran variables
        # to SMT symbols
        self.subst = {}
        # We have a stack of these to support save/restore
        self.subst_stack = []
        # The constraint set is represented as a list of boolean SMT formulae
        self.constraints = []
        # The access dict maps each array name to a list of array accesses
        self.access_dict = {}
        # Has the analaysis finished?
        self.finished = False
        # We map array intrinsic calls (e.g. size, lbound, ubound) to SMT
        # integer variables. The following dict maps array names to a
        # set of integer variable names holding the results of intrinsic
        # calls on that array.
        self.array_intrins_vars = {}
        # Accesses to arrays in this set will be ignored.
        self.explicit_private_vars = set()
        # Are we inside the parallel region to analyse for conflicts?
        self.in_region_of_interest = False

    def _init_array_intrins_vars(self, routine: Routine):
        '''Initialise the 'array_intrins_vars' dict so that, for each
        array accessed, it holds a set of integer variables
        representing the results of intrinsics (such as size,
        lbound, ubound) applied to that array.

        :param routine: the Routine holding the code that we are
           analysing.
        '''
        if self.opts.handle_array_intrins:
            for stmt in routine.children:
                for call in stmt.walk(IntrinsicCall):
                    intrins_pair = \
                        self.trans.translate_array_intrinsic_call(call)
                    if intrins_pair:
                        (arr_name, var_name) = intrins_pair
                        if arr_name not in self.array_intrins_vars:
                            self.array_intrins_vars[arr_name] = set()
                        self.array_intrins_vars[arr_name].add(var_name)

    def _save_subst(self):
        '''Push copy of current substitution to the stack.'''
        self.subst_stack.append(self.subst.copy())

    def _restore_subst(self):
        '''Pop substitution from stack into current substitution.'''
        self.subst = self.subst_stack.pop()

    def _fresh_integer_var(self) -> z3.ExprRef:
        '''Create an fresh SMT integer variable.'''
        if self.opts.use_bv:
            return z3.FreshConst(z3.BitVecSort(self.opts.int_width))
        else:
            return z3.FreshInt()

    def _fresh_logical_var(self) -> z3.BoolRef:
        return z3.FreshBool()

    def _integer_var(self, var: str) -> z3.ExprRef:
        '''Create an integer SMT variable with the given name.'''
        if self.opts.use_bv:
            return z3.BitVec(var, self.opts.int_width)
        else:
            return z3.Int(var)

    def _integer_val(self, val: int) -> z3.ExprRef:
        '''Create an SMT integer value.'''
        if self.opts.use_bv:
            return z3.BitVecVal(val, self.opts.int_width)
        else:
            return z3.IntVal(val)

    def _kill_integer_var(self, var: str):
        '''Clear knowledge of integer 'var' by mapping it to a fresh,
        unconstrained symbol.'''
        fresh_sym = self._fresh_integer_var()
        smt_var = self._integer_var(var)
        self.subst[smt_var] = fresh_sym

    def _kill_logical_var(self, var: str):
        '''Clear knowledge of logical 'var' by mapping it to a fresh,
        unconstrained symbol'''
        fresh_sym = z3.FreshBool()
        smt_var = z3.Bool(var)
        self.subst[smt_var] = fresh_sym

    def _kill_all_written_vars(self, node: Node):
        '''Kill all scalar integer/logical variables written inside 'node'.'''
        var_accesses = node.reference_accesses()
        for sig, access_seq in var_accesses.items():
            for access_info in access_seq.all_write_accesses:
                if isinstance(access_info.node, Loop):
                    self._kill_integer_var(sig.var_name)
                    break
                elif isinstance(access_info.node, Reference):
                    if _is_scalar_integer(access_info.node.datatype):
                        self._kill_integer_var(sig.var_name)
                        break
                    elif _is_scalar_logical(access_info.node.datatype):
                        self._kill_logical_var(sig.var_name)
                        break
                    elif isinstance(access_info.node.datatype, ArrayType):
                        # If an array variable is modified we kill intrinsic
                        # vars associated with it. This is overly safe:
                        # we probably only need to kill these vars if the
                        # array is passed to a mutating routine/intrinsic.
                        if sig.var_name in self.array_intrins_vars:
                            for v in self.array_intrins_vars[sig.var_name]:
                                self._kill_integer_var(v)
                        break

    def _add_constraint(self, smt_expr: z3.BoolRef):
        '''Add the SMT constraint to the constraint set.'''
        self.constraints.append(smt_expr)

    def _add_integer_assignment(self, var: str, smt_expr: z3.ExprRef):
        '''Add an integer assignment constraint to the constraint set.'''
        # Create a fresh symbol
        fresh_sym = self._fresh_integer_var()
        # Assert equality between this symbol and the given SMT expression
        self._add_constraint(fresh_sym == smt_expr)
        # Update the substitution
        smt_var = self._integer_var(var)
        self.subst[smt_var] = fresh_sym

    def _add_logical_assignment(self, var: str, smt_expr: z3.BoolRef):
        '''Add a logical assignment constraint to the constraint set.'''
        # Create a fresh symbol
        fresh_sym = z3.FreshBool()
        # Assert equality between this symbol and the given SMT expression
        self._add_constraint(fresh_sym == smt_expr)
        # Update the substitution
        smt_var = z3.Bool(var)
        self.subst[smt_var] = fresh_sym

    def _apply_subst(self, expr: z3.ExprRef) -> z3.ExprRef:
        '''Apply the current substitution to the given expression.'''
        # The Z3 substitute() function takes a list of pairs rather
        # than a dict and, as the substitution can get quite large,
        # this can be inefficient. Therefore, we first narrow down
        # the substitution to cover only the free variables present
        # in the expression, and then apply it.
        subst_pairs = []
        for fv in _free_vars(expr):
            if fv in self.subst:
                subst_pairs.append((fv, self.subst[fv]))
        return z3.substitute(expr, *subst_pairs)

    def _translate_integer_expr_with_subst(self, expr: Node):
        '''Translate the given integer expression to SMT, and apply the
        current substitution.'''
        (smt_expr, cs) = self.trans.translate_integer_expr(expr)
        for c in cs:
            self._add_constraint(self._apply_subst(c))
        return self._apply_subst(smt_expr)

    def _translate_logical_expr_with_subst(self, expr: Node):
        '''Translate the given logical expression to SMT, and apply the
        current substitution.'''
        (smt_expr, cs) = self.trans.translate_logical_expr(expr)
        for c in cs:
            self._add_constraint(self._apply_subst(c))
        return self._apply_subst(smt_expr)

    def _translate_cond_expr_with_subst(self, expr: Node):
        '''Translate the given conditional expression to SMT, and apply
        the current substitution. Instead of adding constraints to
        the constraint set, this function ANDs constraints with the
        translated expression.'''
        (smt_expr, cs) = self.trans.translate_logical_expr(expr)
        smt_expr = z3.And([smt_expr] + cs)
        return self._apply_subst(smt_expr)

    def _constrain_loop_var(self,
                            var:   z3.ExprRef,
                            start: DataNode,
                            stop:  DataNode,
                            step:  DataNode):
        '''Constrain a loop variable to given start/stop/step.'''
        zero = self._integer_val(0)
        var_begin = self._translate_integer_expr_with_subst(start)
        var_end = self._translate_integer_expr_with_subst(stop)
        if step is None:
            step = Literal("1", ScalarType.integer_type())  # pragma: no cover
        var_step = self._translate_integer_expr_with_subst(step)
        i = self._fresh_integer_var()
        self._add_constraint(var_step != zero)
        self._add_constraint(
          z3.Implies(var_step > zero,
                     z3.And(var >= var_begin, var <= var_end)))
        self._add_constraint(
          z3.Implies(var_step < zero,
                     z3.And(var <= var_begin, var >= var_end)))
        self._add_constraint(var == var_begin + i * var_step)
        self._add_constraint(i >= zero)
        # Prohibit overflow/underflow of "i * var_step"
        if self.opts.use_bv and self.opts.prohibit_overflow:
            self._add_constraint(z3.BVMulNoOverflow(i, var_step, True))
            self._add_constraint(z3.BVMulNoUnderflow(i, var_step))
        return (var_begin, var_end, var_step)

    def _get_private_vars(self) -> set[str]:
        '''Get the list of private variables'''
        return self.explicit_private_vars

    def _add_array_access(self, access: ArrayAccess):
        '''Add an array access to the current access dict.'''
        array_name = str(access.name)
        if array_name in self._get_private_vars():
            return
        if array_name in self.access_dict:
            self.access_dict[array_name].append(access)
        else:
            self.access_dict[array_name] = [access]

    def _add_all_array_accesses(self, node: Node, cond: z3.BoolRef):
        '''Add all array accesses in the given node to the current
        access dict.'''
        if not self.in_region_of_interest: return
        var_accesses = node.reference_accesses()
        for sig, access_seq in var_accesses.items():
            for access_info in access_seq:
                if isinstance(access_info.node, Reference):
                    if not access_info.is_data_access: continue
                    (s, indices) = access_info.node.get_signature_and_indices()
                    indices_flat = [i for inds in indices for i in inds]
                    is_array_access = (indices_flat != [] or
                       isinstance(access_info.node.datatype, ArrayType))
                    if is_array_access or self.opts.check_scalars:
                        smt_indices = []
                        for inds in indices:
                            smt_inds = []
                            for ind in inds:
                                if isinstance(ind, Range):
                                    var = self._fresh_integer_var()
                                    self._constrain_loop_var(
                                      var, ind.start, ind.stop, ind.step)
                                    smt_inds.append(var)
                                else:
                                    smt_inds.append(
                                      self._translate_integer_expr_with_subst(
                                        ind))
                            smt_indices.append(smt_inds)
                        self._add_array_access(
                            ArrayAccess(
                              s, cond, access_info.is_any_write(),
                              smt_indices, access_info.node,
                              not is_array_access))

    def _step(self, stmt: Node, cond: z3.BoolRef):
        '''Analyse the given statement in recursive-descent fashion.'''

        # Has analysis finished?
        if self.finished:
            return

        # Assignment
        if isinstance(stmt, Assignment):
            if isinstance(stmt.lhs, Reference):
                (sig, indices) = stmt.lhs.get_signature_and_indices()
                indices_flat = [i for inds in indices for i in inds]
                if indices_flat == [] and len(sig) == 1:
                    if (self.in_region_of_interest and
                            self.opts.check_scalars and
                            sig.var_name not in self._get_private_vars()):
                        # Only accumulate info about private variables
                        # if we're inside the region of potential conflicts
                        pass
                    elif _is_scalar_integer(stmt.lhs.datatype):
                        rhs_smt = self._translate_integer_expr_with_subst(
                                    stmt.rhs)
                        self._add_integer_assignment(sig.var_name, rhs_smt)
                        self._add_all_array_accesses(stmt.rhs, cond)
                        return
                    elif _is_scalar_logical(stmt.lhs.datatype):
                        rhs_smt = self._translate_logical_expr_with_subst(
                                    stmt.rhs)
                        self._add_logical_assignment(sig.var_name, rhs_smt)
                        self._add_all_array_accesses(stmt.rhs, cond)
                        return

        # Schedule
        if isinstance(stmt, Schedule):
            for child in stmt.children:
                self._step(child, cond)
            return

        # IfBlock
        if isinstance(stmt, IfBlock):
            # Loop over each condition/body pair in the list of branches
            for (if_cond, if_body) in if_else_chain(stmt):
                # Translate condition to SMT
                if if_cond is None:
                    smt_cond = z3.BoolVal(True)
                else:
                    smt_cond = self._translate_cond_expr_with_subst(if_cond)
                    self._add_all_array_accesses(if_cond, cond)
                # Recursively step into body
                self._save_subst()
                self._step(if_body, z3.And(cond, smt_cond))
                self._restore_subst()
                # Accumulate the condition for the next branch
                cond = z3.And(cond, z3.Not(smt_cond))
            # Kill vars written by each branch
            for (_, if_body) in if_else_chain(stmt):
                self._kill_all_written_vars(if_body)
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
            self._constrain_loop_var(
                var, stmt.start_expr, stmt.stop_expr, stmt.step_expr)
            # Analyse loop body
            self._step(stmt.loop_body, cond)
            self._restore_subst()
            return

        # WhileLoop
        if isinstance(stmt, WhileLoop):
            # Kill variables written by loop body
            self._kill_all_written_vars(stmt.loop_body)
            # Add array accesses in condition
            self._add_all_array_accesses(stmt.condition, cond)
            # Translate condition to SMT
            smt_condition = self._translate_cond_expr_with_subst(
              stmt.condition)
            # Recursively step into loop body
            self._save_subst()
            self._step(stmt.loop_body, z3.And(cond, smt_condition))
            self._restore_subst()
            return

        # Stop statement
        if _is_stop(stmt):
            # We can assume that the current condition doesn't hold anywhere
            # beyond this point
            self._add_constraint(z3.Not(cond))
            return

        # Stomp directive
        if isinstance(stmt, OpenMPDirective) and stmt.is_stomp_directive:
            # Add assumption
            if "assume" in stmt.clauses:
                assumption = self._translate_logical_expr_with_subst(
                                 stmt.clauses["assume"])
                self._add_constraint(z3.Implies(cond, assumption))
                return

        # Fall through
        self._add_all_array_accesses(stmt, cond)
        self._kill_all_written_vars(stmt)


# Helper functions
# ================


def _is_scalar_integer(dt: DataType) -> bool:
    '''Check that type is a scalar integer of unspecified precision.'''
    return (isinstance(dt, ScalarType) and
            dt.intrinsic == ScalarType.Intrinsic.INTEGER and
            dt.precision == ScalarType.Precision.UNDEFINED)


def _is_scalar_logical(dt: DataType) -> bool:
    '''Check that type is a scalar logical.'''
    return (isinstance(dt, ScalarType) and
            dt.intrinsic == ScalarType.Intrinsic.BOOLEAN)


def _free_vars(expr: z3.ExprRef) -> list[z3.ExprRef]:
    '''Return all the free variables (uninterpreted constants) in the
    given expression.'''
    if z3.is_const(expr):
        if expr.decl().kind() == z3.Z3_OP_UNINTERPRETED:
            return {expr}
        else:
            return {}
    else:
        return {fv for child in expr.children() for fv in _free_vars(child)}


def _is_stop(node: Node) -> bool:
    '''Determines whether or not the given PSyIR node represents a
    Fortran "stop" or "error stop" statement.'''
    if isinstance(node, CodeBlock) and len(node.parse_tree_nodes) == 1:
        stmt = node.parse_tree_nodes[0]
        if (isinstance(stmt, Fortran2003.Stop_Stmt) or
                isinstance(stmt, Fortran2008.Error_Stop_Stmt)):
            return True
    return False
