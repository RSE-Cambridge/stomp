# SPDX-License-Identifier: BSD-3-Clause

'''This module provides a class to represent messages reported by the
tool to the user.
'''

import re
from enum import Enum, auto
from typing import Optional
from psyclone.psyir.nodes import Node
from psyclone.psyir.backend.fortran import FortranWriter
from stomp.misc import statement_text
from stomp.colours import Colour


class StompMessageCode(Enum):
    '''A unique message code capturing the kind of issue found.'''
    ArrayDataRace              = auto()
    BadNowait                  = auto()
    BadReductionClause         = auto()
    BadUniqueDirective         = auto()
    DataSharingConflict        = auto()
    EndStandaloneDir           = auto()
    FileLoadFailure            = auto()
    FoundParallelisableLoop    = auto()
    ImpureParallelCall         = auto()
    InvalidCollapseClause      = auto()
    LoopDirectiveHasNoLoop     = auto()
    MalformedSectionsDirective = auto()
    MisplacedDirective         = auto()
    ModuleLoadFailure          = auto()
    NonRectangularLoop         = auto()
    OpenMPParseError           = auto()
    ReadUninitialisedPrivate   = auto()
    ScalarDataRace             = auto()
    SingleStatementExpected    = auto()
    SingletonDirEmpty          = auto()
    StrayOrderedDirective      = auto()
    UnmatchedEnd               = auto()
    UnrecognisedDirective      = auto()
    UnresolvedCall             = auto()
    UnsupportedArrayReduction  = auto()
    WildcardImportInSubroutine = auto()

    def is_warning(self):
        return self in [StompMessageCode.FileLoadFailure,
                        StompMessageCode.ModuleLoadFailure]

    def is_good(self):
        return self in [StompMessageCode.FoundParallelisableLoop]


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
               line_num: Optional[int] = None
               ):
        '''Render the message as a string.'''

        # Helper function to display field header in colour
        def header(text: str):
            return Colour.blue(text) + ": "

        # Message code
        out = header("Issue")
        if self.code.is_warning():
            out += Colour.amber(self.code.name)
        elif self.code.is_good():
            out += Colour.green(self.code.name)
        else:
            out += Colour.red(self.code.name)
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
                text = statement_text(self.node, max_len=60)
                out += header("Statement") + text + "\n"

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
    '''Global logger class for recording messages. Currently not
    thread safe.'''

    # List of messages gathered so far
    messages: list[StompMessage] = []

    # List of messages to ignore
    ignore: list[StompMessageCode] = []

    # Number of SMT solver queries
    smt_queries: int = 0

    # Number of SMT timeouts
    smt_timeouts: int = 0

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
    def has_message(cls, code: StompMessageCode):
        return code in [msg.code for msg in cls.get_messages()]

    @classmethod
    def get_all_messages(cls):
        return cls.messages

    @classmethod
    def log_smt_query(cls):
        cls.smt_queries += 1

    @classmethod
    def log_smt_timeout(cls):
        cls.smt_timeouts += 1

    @classmethod
    def clear(cls):
        cls.messages = []
        cls.smt_queries = 0
        cls.smt_timeouts = 0
