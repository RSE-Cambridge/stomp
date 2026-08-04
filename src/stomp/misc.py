# SPDX-License-Identifier: BSD-3-Clause

'''This module provides miscelaneous functions.'''

import re
from typing import Union, Optional, List
from psyclone.psyir.nodes import \
    Reference, IfBlock, Schedule, Node, Loop, Statement, CodeBlock
from psyclone.core import AccessInfo
from psyclone.psyir.symbols import ArrayType, SymbolTable
from psyclone.psyir.frontend.fortran import FortranReader
from psyclone.errors import InternalError
from psyclone.psyir.backend.fortran import FortranWriter
from fparser.two import Fortran2003, Fortran2008


def is_array_access(info: AccessInfo) -> bool:
    '''Determine if given access is an array access.'''
    if isinstance(info.node, Reference):
        if info.is_data_access:
            (s, indices) = info.node.get_signature_and_indices()
            has_indices = [i for inds in indices for i in inds] != []
            if has_indices or isinstance(info.node.datatype, ArrayType):
                return True
    return False


def get_nested_loops(node: Node) -> List[Loop]:
    '''Return a list of immediately nested loops'''
    loops = []
    while True:
        if isinstance(node, Loop):
            loops.append(node)
            if len(node.loop_body.children) == 1:
                node = node.loop_body.children[0]
            else:
                return loops
        else:
            return loops


def if_else_chain(node: IfBlock):
    '''This method allows a chain of 'if'/'else if'/.../'else'
    statements to be viewed in its flattened form, without nesting.

    :returns: a list of condition/body pairs. Nested 'else if' chains
       (if there are any) are recursively gathered. The condition for
       the final 'else' in the chain (if there is one) is 'None'.
    '''
    branches = [(node.condition, node.if_body)]
    if node.else_body:
        if (isinstance(node.else_body, Schedule) and
                len(node.else_body.children) == 1 and
                isinstance(node.else_body.children[0], IfBlock)):
            branches.extend(if_else_chain(node.else_body.children[0]))
        else:
            branches.append((None, node.else_body))
    return branches


def parse_fortran_expr(code: str,
                       symbol_table: Optional[SymbolTable] = None) \
                           -> Union[str, Node]:
    '''Parse a Fortran expression.'''
    fortran_reader = FortranReader(
        resolve_modules=False,
        ignore_comments=True,
        ignore_directives=True,
        conditional_openmp_statements=False,
        free_form=True
    )
    try:
        psyir = fortran_reader.psyir_from_expression(code, symbol_table)
    except (InternalError, ValueError, IOError) as err:
        return str(err)
    return psyir


def parse_fortran_stmt(code: str,
                       symbol_table: Optional[SymbolTable] = None) \
                           -> Union[str, Node]:
    '''Parse a Fortran statement.'''
    fortran_reader = FortranReader(
        resolve_modules=False,
        ignore_comments=True,
        ignore_directives=True,
        conditional_openmp_statements=False,
        free_form=True
    )
    try:
        psyir = fortran_reader.psyir_from_statement(code, symbol_table)
    except (InternalError, ValueError, IOError) as err:
        return str(err)
    return psyir


def statement_text(node: Node, max_len: int) -> str:
    '''Return Fortran text for the statement holding the given
    PSyIR node.'''
    if node is None: return ""
    node = node.ancestor(Statement, include_self=True)
    return node_text(node, max_len)


def node_text(node: Node, max_len: int) -> str:
    '''Return Fortran text for the given PSyIR node.'''
    if node is None: return ""
    text = ""
    try:
        writer = FortranWriter()
        # Convert the PSyIR to Fortran text
        # For efficiency, copy (hence isolate) the node
        isolated_node = node.copy()
        # Ignore preceeding comment, if there is one
        isolated_node._preceding_comment = None
        text = writer(isolated_node)
        # Trim the text and step back for more detail if needed
        text = text.strip()
        re.sub(" +", " ", text)
        text = repr(text[:max_len])
    except Exception:
        pass
    return text


def get_line_num(node: Node) -> Optional[int]:
    '''Determine line number of given PSyIR node.'''
    stmt = node.ancestor(Statement, include_self=True)
    if (hasattr(stmt, "ast") and
            stmt.ast and
            hasattr(stmt.ast.item, "span") and
            stmt.ast.item.span and
            len(stmt.ast.item.span) >= 1):
        return stmt.ast.item.span[0]
    return None


def is_stop(node: Node) -> bool:
    '''Determines whether or not the given PSyIR node represents a
    Fortran "stop" or "error stop" statement.'''
    if isinstance(node, CodeBlock) and len(node.parse_tree_nodes) == 1:
        stmt = node.parse_tree_nodes[0]
        if (isinstance(stmt, Fortran2003.Stop_Stmt) or
                isinstance(stmt, Fortran2008.Error_Stop_Stmt)):
            return True
    return False


def is_exit(node: Node) -> bool:
    '''Determines whether or not the given PSyIR node represents a
    Fortran "exit" statement with no argument, i.e. it returns True
    for an "exit" statement but False for an "exit named_construct"
    statement'''
    if isinstance(node, CodeBlock) and len(node.parse_tree_nodes) == 1:
        stmt = node.parse_tree_nodes[0]
        if isinstance(stmt, Fortran2003.Exit_Stmt):
            return True
    return False
