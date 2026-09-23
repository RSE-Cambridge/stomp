# SPDX-License-Identifier: BSD-3-Clause

'''This module provides a class to translate Fortran to Z3. Currently, it
supports translation of scalar integer and scalar logical expressions.'''

import z3
import random
import threading
from typing import Optional, Tuple, List
from psyclone.psyir.nodes import \
    Literal, Reference, UnaryOperation, BinaryOperation, \
    IntrinsicCall, Node, ArrayReference, Call


class FortranToZ3:
    '''The class provides methods to translate Fortran expressions to Z3
       expressions, as well as some useful wrappers around the Z3 solver.

       :param handle_array_intrins: if True, array intrinsic calls
          'size(<arr>,<dim>)', 'lbound(<arr>,<dim>)', and
          'ubound(<arr>,<dim>)' will be translated to Z3 integer variables
          of the form '#size_<arr>_<dim>', '#lbound_<arr>_<dim>', and
          '#ubound_<arr>_<dim>'.

       :param allow_unsupported: if False, raise a TranslationNotSupported
          exception when trying to translate an expression that we don't
          currently support translation of. If True, introduce unconstrained
          fresh variables for unsupported expressions.
    '''
    def __init__(self,
                 handle_array_intrins: bool = False,
                 allow_unsupported: bool = True):
        self.handle_array_intrins = handle_array_intrins
        self.allow_unsupported = allow_unsupported
        self.custom_call_mapping = {}

    def add_custom_call_mapping(self, fun_name: str, expr: z3.ExprRef):
        '''Add a custome translation from a call of the given function
           name to the given Z3 expression.'''
        self.custom_call_mapping[fun_name] = expr

    def translate_integer_expr(self, expr_root: Node) -> z3.ExprRef:
        '''Translate a Fortran scalar integer expression to SMT.

           :param expr_root: the expression to translate. This is assumed
             to have scalar integer type.
           :return: the translated expression.
        '''
        def trans(e: Node) -> z3.ExprRef:
            # Literal
            if isinstance(e, Literal):
                try:
                    return z3.IntVal(int(e.value))
                except ValueError:
                    pass

            # Reference
            if (isinstance(e, Reference)
                    and not isinstance(e, ArrayReference)):
                (sig, indices) = e.get_signature_and_indices()
                indices_flat = [i for inds in indices for i in inds]
                if indices_flat == []:
                    return z3.Int(str(sig))

            # UnaryOperation
            if isinstance(e, UnaryOperation):
                arg_smt = trans(e.operand)
                if e.operator == UnaryOperation.Operator.MINUS:
                    return -arg_smt
                if e.operator == UnaryOperation.Operator.PLUS:
                    return arg_smt

            # BinaryOperation
            if isinstance(e, BinaryOperation):
                (left, right) = e.operands
                left_smt = trans(left)
                right_smt = trans(right)

                if e.operator == BinaryOperation.Operator.ADD:
                    return left_smt + right_smt
                if e.operator == BinaryOperation.Operator.SUB:
                    return left_smt - right_smt
                if e.operator == BinaryOperation.Operator.MUL:
                    return left_smt * right_smt
                if e.operator == BinaryOperation.Operator.DIV:
                    return left_smt / right_smt

            # IntrinsicCall
            if isinstance(e, IntrinsicCall):
                # Unary operators
                if e.intrinsic == IntrinsicCall.Intrinsic.ABS:
                    smt_arg = trans(e.children[1])
                    return z3.Abs(smt_arg)

                # Binary operators
                if e.intrinsic in [IntrinsicCall.Intrinsic.MODULO,
                                   IntrinsicCall.Intrinsic.MOD]:
                    left_smt = trans(e.children[1])
                    right_smt = trans(e.children[2])

                    if (e.intrinsic == IntrinsicCall.Intrinsic.MODULO):
                        return left_smt % right_smt

                    if (e.intrinsic == IntrinsicCall.Intrinsic.MOD):
                        m = left_smt % right_smt
                        return (z3.If(z3.And(
                                          m != 0,
                                          (left_smt < 0) != (right_smt < 0)),
                                      m-right_smt, m))

                # N-ary operators
                if e.intrinsic in [IntrinsicCall.Intrinsic.MIN,
                                   IntrinsicCall.Intrinsic.MAX]:
                    smt_args = [trans(arg) for arg in e.children[1:]]
                    reduced = smt_args[0]
                    for arg in smt_args[1:]:
                        if e.intrinsic == IntrinsicCall.Intrinsic.MIN:
                            reduced = z3.If(reduced < arg, reduced, arg)
                        elif e.intrinsic == IntrinsicCall.Intrinsic.MAX:
                            reduced = z3.If(reduced < arg, arg, reduced)
                    return reduced

                # Array intrinsics
                if self.handle_array_intrins:
                    var_name = self.translate_array_intrinsic_call(e)
                    if var_name:
                        return z3.Int(var_name)

            # Call
            if isinstance(e, Call):
                if e.routine.name in self.custom_call_mapping:
                    return self.custom_call_mapping[e.routine.name]

            # Fall through: return a fresh, unconstrained symbol
            if self.allow_unsupported:
                return z3.FreshInt()
            else:
                raise TranslationNotSupported(e)

        return trans(expr_root)

    def translate_logical_expr(self, expr_root: Node) -> z3.BoolRef:
        '''Translate a scalar logical Fortran expression to SMT.

           :param expr_root: the expression to translate. This is assumed
             to have scalar logical type.
           :return: the translated expression.
        '''
        def trans(expr: Node):
            # Literal
            if isinstance(expr, Literal):
                if expr.value == "true":
                    return z3.BoolVal(True)
                if expr.value == "false":
                    return z3.BoolVal(False)

            # Reference
            if (isinstance(expr, Reference)
                    and not isinstance(expr, ArrayReference)):
                (sig, indices) = expr.get_signature_and_indices()
                indices_flat = [i for inds in indices for i in inds]
                if indices_flat == []:
                    return z3.Bool(str(sig))

            # UnaryOperation
            if isinstance(expr, UnaryOperation):
                arg_smt = trans(expr.operand)
                if expr.operator == UnaryOperation.Operator.NOT:
                    return z3.Not(arg_smt)

            # BinaryOperation
            if isinstance(expr, BinaryOperation):
                # Operands are logicals
                if expr.operator in [BinaryOperation.Operator.AND,
                                     BinaryOperation.Operator.OR,
                                     BinaryOperation.Operator.EQV,
                                     BinaryOperation.Operator.NEQV]:
                    (left, right) = expr.operands
                    left_smt = trans(left)
                    right_smt = trans(right)

                    if expr.operator == BinaryOperation.Operator.AND:
                        return z3.And(left_smt, right_smt)
                    if expr.operator == BinaryOperation.Operator.OR:
                        return z3.Or(left_smt, right_smt)
                    if expr.operator == BinaryOperation.Operator.EQV:
                        return left_smt == right_smt
                    if expr.operator == BinaryOperation.Operator.NEQV:
                        return left_smt != right_smt

                # Operands are numbers
                if expr.operator in [BinaryOperation.Operator.EQ,
                                     BinaryOperation.Operator.NE,
                                     BinaryOperation.Operator.GT,
                                     BinaryOperation.Operator.LT,
                                     BinaryOperation.Operator.GE,
                                     BinaryOperation.Operator.LE]:
                    (left, right) = expr.operands
                    left_smt = self.translate_integer_expr(left)
                    right_smt = self.translate_integer_expr(right)

                    if expr.operator == BinaryOperation.Operator.EQ:
                        return left_smt == right_smt
                    if expr.operator == BinaryOperation.Operator.NE:
                        return left_smt != right_smt
                    if expr.operator == BinaryOperation.Operator.GT:
                        return left_smt > right_smt
                    if expr.operator == BinaryOperation.Operator.LT:
                        return left_smt < right_smt
                    if expr.operator == BinaryOperation.Operator.GE:
                        return left_smt >= right_smt
                    if expr.operator == BinaryOperation.Operator.LE:
                        return left_smt <= right_smt

            # Fall through: return a fresh, unconstrained symbol
            if self.allow_unsupported:
                return z3.FreshBool()
            else:
                raise TranslationNotSupported(expr)

        return trans(expr_root)

    def lbound_name(self, array_name: str, array_dim: str) -> str:
        '''Return name for integer variable representing the lower bound
           in the given dimension of the array with the given name.'''
        return f"{array_name}_#lbound_{array_dim}"

    def ubound_name(self, array_name: str, array_dim: str) -> str:
        '''Return name for integer variable representing the upper bound
           in the given dimension of the array with the given name.'''
        return f"{array_name}_#ubound_{array_dim}"

    def size_name(self,
                  array_name: str,
                  array_dim: Optional[str] = None) -> str:
        '''Return name for integer variable representing the size
           of the given dimension of the array with the given name.'''
        if array_dim is None:
            return f"{array_name}_#size"
        else:
            return f"{array_name}_#size_{array_dim}"

    def get_bounds_names(
            self,
            array_name: str,
            array_rank) -> Tuple[List[Tuple[str, str, str]], str]:
        '''Return names for integer variables representing the lower bound,
           upper bound, and size, in each dimension for an array with the
           given name and rank. Also return a name for the integer
           variable representing the full size over all dimensions.
        '''
        dims = [
           (self.lbound_name(array_name, i),
            self.ubound_name(array_name, i),
            self.size_name(array_name, i))
           for i in range(1, array_rank+1)]
        return (dims, self.size_name(array_name))

    def translate_array_intrinsic_call(self, call: IntrinsicCall) \
            -> Optional[str]:
        '''Translate array intrinsic call (one of 'size', 'lbound', 
           and 'ubound') to an integer SMT variable.
        '''
        if call.intrinsic not in [IntrinsicCall.Intrinsic.LBOUND,
                                  IntrinsicCall.Intrinsic.UBOUND,
                                  IntrinsicCall.Intrinsic.SIZE]:
            return None
        # We require 2 or more children
        if len(call.children) < 2:
            return None  # pragma: no cover
        # We require the first argument to be a Reference
        array = call.children[1]
        if not isinstance(array, Reference):
            return None
        # We require no indices in the reference
        (sig, indices) = array.get_signature_and_indices()
        any_indices = any([inds != [] for inds in indices])
        if any_indices: return None
        name = str(sig)
        # Translate full-size call
        if len(call.children) == 2:
            if call.intrinsic == IntrinsicCall.Intrinsic.SIZE:
                return self.size_name(name)
            else:
                return None
        # Translate other calls
        if len(call.children) != 3:
            return None
        rank = call.children[2]
        if isinstance(rank, Literal):
            if call.intrinsic == IntrinsicCall.Intrinsic.LBOUND:
                return self.lbound_name(name, rank.value)
            elif call.intrinsic == IntrinsicCall.Intrinsic.UBOUND:
                return self.ubound_name(name, rank.value)
            elif call.intrinsic == IntrinsicCall.Intrinsic.SIZE:
                return self.size_name(name, rank.value)
        return None

    def solve(self,
              constraints: list[z3.BoolRef],
              sum_of_prods: list[list[z3.BoolRef]] = [[z3.BoolVal(True)]],
              exprs_to_eval: list[z3.ExprRef] = [],
              smt_timeout_ms: Optional[int] = 5000,
              num_sweep_threads: int = 4,
              sweep_seed: int = 1) \
            -> (z3.CheckSatResult, list[z3.ExprRef]):
        '''Invoke the solver on the given constraints. If the constraints
        are satisfiable then the given expressions are evaluated and
        returned.

        The solver is quite sensitive to the order of constraints.
        If the sweeper is enabled, multiple solvers are run in parallel,
        with each one using a different constraint order. As soon as one
        solver completes, the others are cancelled.

        :param constraints: a set of constraints to solve. These are
           implicitly ANDed together. If the sweeper is enabled,
           this list is randomly shuffled by each solver thread.
        :param sum_of_prods: a sum of products of constraints to solve.
           Elements of the inner lists are ANDed together.
           Elements of the outer lists are ORed together.
           These constraints are implicitly ANDed with the 'constraints'.
           If the sweeper is enabled, elements of the inner lists are
           randomly shuffled by each solver thread.
        :param exprs_to_eval: a list of expressions to evaluate, assuming
           the constraints are satisfiable.
        :param smt_timeout_ms: the time limit (in milliseconds) given to
           the SMT solver to find a solution.
        :param num_sweep_threads: when larger than one, this option enables the
           sweeper, which runs multiple solvers across multiple threads with
           each one using a different constraint ordering. This reduces the
           solver's sensitivity to the order of constraints.
        :param sweep_seed: the seed for the random number generator used
           by the sweeper.
        :return: the result of the solver and a list of evaluated expressions
           (the list is empty if the constraints were not satisifiable)
        '''
        if num_sweep_threads <= 1:
            s = z3.Solver()
            s.set("random_seed", sweep_seed)
            s.set("smt.random_seed", sweep_seed)
            if smt_timeout_ms is not None:
                s.set("timeout", smt_timeout_ms)
            s.add(z3.And(constraints))
            s.add(z3.Or([z3.And(prod) for prod in sum_of_prods]))
            result = s.check()
            result_values = []
            if result == z3.sat:
                m = s.model()
                for expr in exprs_to_eval:
                    result_values.append(m.eval(expr,
                                                model_completion=True))
            return (result, result_values)
        else:
            return self.sweep_solve(
                      constraints,
                      sum_of_prods,
                      exprs_to_eval,
                      smt_timeout_ms,
                      num_sweep_threads,
                      sweep_seed)

    def sweep_solve(self,
                    constraints: list[z3.BoolRef],
                    sum_of_prods: list[list[z3.BoolRef]] =
                                      [[z3.BoolVal(True)]],
                    exprs_to_eval: list[z3.ExprRef] = [],
                    smt_timeout_ms: Optional[int] = 5000,
                    num_sweep_threads: int = 4,
                    sweep_seed: int = 1) \
            -> (z3.CheckSatResult, list[z3.ExprRef]):
        '''The interface to this method is identical to that of the
        'solve()' method. This method implements the sweeper.'''
        result = []
        result_values = []
        result_lock = threading.Lock()
        done_event = threading.Event()

        # Function that runs in each thread
        def wrapper(solver, exprs_to_eval):
            out = solver.check()
            with result_lock:
                if not done_event.is_set():
                    if out == z3.sat:
                        m = solver.model()
                        for expr in exprs_to_eval:
                            result_values.append(str(
                               m.eval(expr, model_completion=True)))
                    result.append(out)
                    done_event.set()

        # Random number generator for shuffling constraints
        rnd = random.Random(sweep_seed)

        # Create a solver per thread
        solvers = []
        threads = []
        for i in range(0, num_sweep_threads):
            # Create a solver for the problem
            ctx = z3.Context()
            s = z3.Solver(ctx=ctx)
            s.set("random_seed", sweep_seed+i)
            s.set("smt.random_seed", sweep_seed+i)
            if smt_timeout_ms is not None:
                s.set("timeout", smt_timeout_ms)
            s.add(z3.And(constraints).translate(ctx))
            sum_constraint = z3.Or([z3.And(prod) for prod in sum_of_prods])
            s.add(sum_constraint.translate(ctx))
            solvers.append(s)
            exprs_to_eval_ctx = [e.translate(ctx) for e in exprs_to_eval]

            # Create a thread for this solver and start it
            t = threading.Thread(target=wrapper, args=(s, exprs_to_eval_ctx))
            threads.append(t)
            t.start()

            # Shuffle the constraints for the next thread
            rnd.shuffle(constraints)
            for prod in sum_of_prods:
                rnd.shuffle(prod)
            if done_event.is_set():
                break

        # Wait for first thread to complete
        done_event.wait()

        # Interrupt all solvers and wait for all threads to complete.
        # This loop appears more complex than necessary, but we want to
        # handle the possibility that we may interrupt a solver before
        # it has started, in which case the interrupt would have no effect
        # and we'd have to wait for that solver's timeout to expire.
        for (s, t) in zip(solvers, threads):
            while True:
                s.interrupt()
                t.join(timeout=0.1)
                if not t.is_alive():
                    break

        return (result[0], result_values)


class TranslationNotSupported(Exception):
    def __init__(self, expr):
        super().__init__("FortranToZ3: encountered an expression "
                         "that can't be translated to Z3.")
        self.expr = expr
