# SPDX-License-Identifier: BSD-3-Clause

'''This module provides miscelaneous functions.'''

from psyclone.psyir.nodes import Reference
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
