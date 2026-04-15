# SPDX-License-Identifier: BSD-3-Clause

'''This module provides miscelaneous functions.'''

from psyclone.psyir.nodes import Reference, IfBlock, Node, Schedule
from psyclone.core import AccessInfo
from psyclone.psyir.symbols import ArrayType


def is_array_access(info: AccessInfo) -> bool:
    '''Determine if given access is an array access.'''
    if isinstance(info.node, Reference):
        if info.is_data_access:
            (s, indices) = info.node.get_signature_and_indices()
            has_indices = [i for inds in indices for i in inds] != []
            if has_indices or isinstance(info.node.datatype, ArrayType):
                return True
    return False


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
