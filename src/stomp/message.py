# SPDX-License-Identifier: BSD-3-Clause

'''This module provides a class to represent messages reported by the
tool to the user.
'''

import re
from enum import Enum
from typing import Optional
from psyclone.psyir.nodes import Node
from psyclone.psyir.backend.fortran import FortranWriter
from stomp.colours import red, blue


class StompMessageCode(Enum):
    '''A unique message code capturing the kind of issue found.'''
    OpenMPParseError = 1
    LoopDirectiveHasNoLoop = 2
    UnmatchedEnd = 3
    SingleStatementExpected = 4
    SingletonDirEmpty = 5
    EndStandaloneDir = 6
    UnrecognisedDirective = 7
    InvalidCollapseClause = 8
    NonRectangularLoop = 9
    DataSharingConflict = 10
    ReadUninitialisedPrivate = 11
    StrayOrderedDirective = 12
    ParallelArrayConflict = 100
    ParallelScalarConflict = 101
    FoundParallelisableLoop = 200


class StompMessage:
    '''A message to report to the user.'''

    def __init__(self,
                 code: StompMessageCode,
                 description: Optional[str] = None,
                 suggestions: list[str] = [],
                 directive_node: Optional[Node] = None,
                 node: Optional[Node] = None,
                 routine_name: Optional[str] = None):
        self.code = code
        self.description = description
        self.suggestions = suggestions
        self.node = node
        self.directive_node = directive_node
        self.routine_name = routine_name

    def render(self,
               filename: Optional[str] = None,
               line_num: Optional[int] = None,
               enable_colours: bool = True
               ):
        '''Render the message as a string.'''

        # Helper function to display field header in colour
        def header(text: str):
            if enable_colours:
                text = blue(text)
            text += ": "
            return text

        # Message code
        if enable_colours:
            out = red(self.code.name)
        else:
            out = self.code.name
        out += "\n"

        # Location
        if filename:
            out += header("File") + filename + "\n"
        if line_num:
            out += header("Line") + str(line_num) + "\n"
        else:
            if self.routine_name:
                out += header("Routine") + self.routine_name + "\n"
            if self.directive_node:
                try:
                    writer = FortranWriter()
                    text = writer(self.directive_node)
                    text = text.strip()
                    re.sub(" +", " ", text)
                    text = repr(text[:60])
                    out += header("Directive") + text + "\n"
                except Exception:
                    pass
            if self.node:
                try:
                    writer = FortranWriter()
                    node = self.node
                    # Look at node's ancestors for more detail
                    for i in range(0, 3):
                        text = writer(node)
                        text = text.strip()
                        re.sub(" +", " ", text)
                        if self.node.parent and len(text) < 60:
                            node = node.parent
                        else:
                            break
                    text = repr(text[:60])
                    out += header("Node") + text + "\n"
                except Exception:
                    pass

        # Description
        if self.description:
            out += header("Description") + self.description + "\n"

        # Suggestions
        if len(self.suggestions) > 1:
            for (idx, suggestion) in enumerate(self.suggestions):
                out += header(f"Suggestion {idx+1}") + suggestion + "\n"
        else:
            for suggestion in self.suggestions:
                out += header("Suggestion") + suggestion + "\n"

        return out


class StompLogger:
    '''Global logger class for recording messages'''

    # List of messages gathered so far
    messages: list[StompMessage] = []

    # List of messages to ignore
    ignore: list[StompMessageCode] = []

    @classmethod
    def add_ignore(cls, code: StompMessageCode):
        cls.ignore.append(code)

    @classmethod
    def add_msg(cls, msg: StompMessage):
        cls.messages.append(msg)

    @classmethod
    def add_message(cls, *args, **kw_args):
        cls.add_msg(StompMessage(*args, **kw_args))

    @classmethod
    def get_messages(cls):
        # Filter out messages in the ignore list
        msgs = [msg for msg in cls.messages if msg.code not in cls.ignore]
        return msgs

    @classmethod
    def get_all_messages(cls):
        return cls.messages

    @classmethod
    def clear(cls):
        cls.messages = []
