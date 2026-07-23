# SPDX-License-Identifier: BSD-3-Clause

'''A poor man's liveness analysis.'''

from typing import Set, Optional
from psyclone.psyir.nodes import \
    Node, Statement, Loop, WhileLoop, IfBlock, Schedule
from stomp.control_flow import after_statement


def use(node: Node) -> Set[str]:
    '''Return the set of variables read by the given node.'''
    result = set()
    accesses = node.reference_accesses()
    for (sig, seq) in accesses.items():
        if seq.is_read():
            result.add(sig.var_name)
    return result


def is_live_in(var_name: str, stmt: Statement) -> bool:
    '''Function to determine if given variable is live-in to the
    given statement. Not very efficient.'''
    visited = set()

    # Is the variable live-in the to given statement?
    def step(s: Statement) -> Optional[bool]:
        if id(s) in visited: return None
        visited.add(id(s))
        if isinstance(s, Loop):
            if var_name == s.variable: return False
            if var_name in use(s.start_expr): return True
            if var_name in use(s.stop_expr): return True
            if var_name in use(s.step_expr): return True
            return step(s.loop_body)
        elif isinstance(s, WhileLoop):
            if var_name in use(s.condition): return True
            return step(s.loop_body)
        elif isinstance(s, Schedule):
            for child in s.children:
                result = step(child)
                if result is not None: return result
        elif isinstance(s, IfBlock):
            if var_name in use(s.condition): return True
            result_then = step(s.if_body)
            if s.else_body:
                result_else = step(s.else_body)
            else:
                result_else = None
            if result_then is True or result_else is True:
                return True
            elif result_then is False and result_else is False:
                return False
            else:
                return None
        elif isinstance(s, Statement):
            accesses = s.reference_accesses()
            for (sig, seq) in accesses.items():
                if sig.var_name == var_name:
                    if seq.is_read(): return True
            for (sig, seq) in accesses.items():
                if sig.var_name == var_name:
                    if seq.is_written(): return False
        return None

    # Explore all execution paths from given statement
    stack = [stmt]
    while stack:
        s = stack.pop()
        result = step(s)
        if result is True:
            return True
        if result is None:
            for succ in after_statement(s):
                if id(succ) not in visited:
                    stack.append(succ)
    return False


def is_live_out(var_name: str, stmt: Statement) -> bool:
    '''Function to determine if given variable is live-out from the
    given statement. Not very efficient.'''
    for s in after_statement(stmt):
        if is_live_in(var_name, s):
            return True
    return False
