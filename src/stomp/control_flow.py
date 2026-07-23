# SPDX-License-Identifier: BSD-3-Clause

'''A poor man's control-flow analysis.'''

from typing import List
from psyclone.psyir.nodes import \
    Statement, Loop, WhileLoop, Schedule, IfBlock, Routine, Return


def after_statement(stmt: Statement) -> List[Statement]:
    '''Return the statements that may execute after the given one.'''
    next_list = []
    while stmt.parent:
        if isinstance(stmt, Return):
            break
        if (isinstance(stmt.parent, Schedule) or
                isinstance(stmt.parent, Routine)):
            if stmt.position + 1 < len(stmt.siblings):
                next_list.append(stmt.siblings[stmt.position + 1])
                return next_list
        elif isinstance(stmt.parent, Loop):
            next_list.append(stmt)
        elif isinstance(stmt.parent, WhileLoop):
            next_list.append(stmt)
        stmt = stmt.parent
    return next_list


def next_statement(stmt: Statement) -> List[Statement]:
    '''Return the statements that may execute next.'''
    next_stmts = []
    if isinstance(stmt, Schedule) and len(stmt.children) >= 1:
        return [stmt.children[0]]
    elif isinstance(stmt, Loop):
        next_stmts.append(stmt.loop_body)
    elif isinstance(stmt, WhileLoop):
        next_stmts.append(stmt.loop_body)
    elif isinstance(stmt, IfBlock):
        next_stmts.append(stmt.if_body)
        if stmt.else_body:
            next_stmts.append(stmt.else_body)
    return next_stmts + after_statement(stmt)


def affects_control_flow(stmt: Statement) -> bool:
    '''Returns true if the given statement affects control flow.
    Such statements are recognised by the 'after_statement' and
    'next_statement' functions. Statements for which this function
    returns false may require special attention in relation to control
    flow.
    '''
    return isinstance(stmt, Schedule) or \
           isinstance(stmt, Loop) or \
           isinstance(stmt, WhileLoop) or \
           isinstance(stmt, IfBlock)
