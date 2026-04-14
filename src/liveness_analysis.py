# SPDX-License-Identifier: BSD-3-Clause

'''This module provides functions for liveness analysis.'''

from typing import List, Set, Optional
from psyclone.psyir.nodes import \
    Node, Statement, Loop, WhileLoop, IfBlock, Schedule


def use(node: Node) -> Set[str]:
    '''Return the set of variables read by the given node.'''
    result = set()
    accesses = node.reference_accesses()
    for (sig, seq) in accesses.items():
        if seq.is_read():
            result.add(sig.var_name)
    return result


def next_statement(stmt: Statement) -> List[Statement]:
    '''Return the list of statements that may execute after the given one.'''
    next_list = []
    if isinstance(stmt, Statement):
        while stmt:
            if stmt.position + 1 < len(stmt.siblings):
                next_list.append(stmt.siblings[stmt.position + 1])
                return next_list
            else:
                if isinstance(stmt.parent, Loop):
                    next_list.append(stmt)
                elif isinstance(stmt.parent, WhileLoop):
                    next_list.append(stmt)
                stmt = stmt.parent
    return next_list


def is_live_in(var_name: str, stmt: Statement) -> bool:
    '''Inefficient function to determine if given variable is live-in
    to the given statement.'''
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
            result = step(s.loop_body)
            if result is not None: return result
        elif isinstance(s, WhileLoop):
            if var_name in use(s.condition): return True
            result = step(s.loop_body)
            if result is not None: return result
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
            if result_then is False and result_else is False:
                return False
        elif isinstance(s, Statement):
            accesses = s.reference_accesses()
            for (sig, seq) in accesses.items():
                if sig.var_name == var_name:
                    if seq.is_read(): return True
            for (sig, seq) in accesses.items():
                if sig.var_name == var_name:
                    if seq.is_write(): return False
        return None

    # Explore all execution paths from given statement
    stack = [stmt]
    while stack:
        s = stack.pop()
        result = step(s)
        if result is True:
            return True
        if result is None:
            stack.extend(next_statement(s))
    return False


def is_live_out(var_name: str, stmt: Statement) -> bool:
    '''Inefficient function to determine if given variable is live-out
    from the given statement.'''
    for s in next_statement(stmt):
        if is_live_in(var_name, s):
            return True
    return False
