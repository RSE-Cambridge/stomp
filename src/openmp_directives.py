# SPDX-License-Identifier: BSD-3-Clause

'''This module provides a liberal abstract syntax and parsing for OpenMP
directives.'''

from __future__ import annotations
import re
from typing import Optional, Dict, Any, List, Union, Tuple, Set
from parser_lib import lift, char, many, token, \
  ParseError, sepby, choice, many1, optional, space, natural
from psyclone.psyir.nodes import Node, Statement, UnknownDirective, Loop
from stomp_message import StompMessage, StompMessageCode, StompLogger

# Recognised OpenMP directives
# ============================

recognised_directives_list = [
    ["allocate"],
    ["allocators"],
    ["assumes"],
    ["atomic"],
    ["barrier"],
    ["cancel"],
    ["cancellation", "point"],
    ["critical"],
    ["declare", "mapper"],
    ["declare", "reduction"],
    ["declare", "simd"],
    ["declare", "target"],
    ["declare", "variant"],
    ["depobj"],
    ["dispatch"],
    ["distribute"],
    ["distribute", "parallel", "do"],
    ["distribute", "parallel", "do", "simd"],
    ["distribute", "simd"],
    ["do"],
    ["do", "simd"],
    ["error"],
    ["flush"],
    ["groupprivate"],
    ["interop"],
    ["loop"],
    ["masked"],
    ["masked", "taskloop"],
    ["masked", "taskloop", "simd"],
    ["master"],
    ["master", "taskloop"],
    ["master", "taskloop", "simd"],
    ["metadirective"],
    ["nothing"],
    ["ordered"],
    ["parallel"],
    ["parallel", "do"],
    ["parallel", "do", "simd"],
    ["parallel", "loop"],
    ["parallel", "masked"],
    ["parallel", "masked", "taskloop"],
    ["parallel", "masked", "taskloop", "simd"],
    ["parallel", "master"],
    ["parallel", "master", "taskloop"],
    ["parallel", "master", "taskloop", "simd"],
    ["parallel", "sections"],
    ["parallel", "workshare"],
    ["prefetch", "data"],
    ["requires"],
    ["scan"],
    ["scope"],
    ["sections"],
    ["simd"],
    ["single"],
    ["target"],
    ["target", "data"],
    ["target", "enter", "data"],
    ["target", "exit", "data"],
    ["target", "parallel"],
    ["target", "parallel", "do"],
    ["target", "parallel", "do", "simd"],
    ["target", "parallel", "loop"],
    ["target", "simd"],
    ["target", "teams"],
    ["target", "teams", "distribute"],
    ["target", "teams", "distribute", "parallel", "do"],
    ["target", "teams", "distribute", "parallel", "do", "simd"],
    ["target", "teams", "distribute", "simd"],
    ["target", "teams", "loop"],
    ["target", "update"],
    ["task"],
    ["taskgroup"],
    ["taskloop"],
    ["taskloop", "simd"],
    ["taskwait"],
    ["taskyield"],
    ["teams"],
    ["teams", "distribute"],
    ["teams", "distribute", "parallel", "do"],
    ["teams", "distribute", "parallel", "do", "simd"],
    ["teams", "distribute", "simd"],
    ["teams", "loop"],
    ["threadprivate"],
    ["tile"],
    ["unroll"],
    ["workshare"]
]

# As a set for fast membership checking
recognised_directives_set = set([
    tuple(kw_list) for kw_list in recognised_directives_list])

# All directive keywords as a set for fast membership checking
recognised_directive_keywords = set([
    kw for kw_list in recognised_directives_list for kw in kw_list])

# Abstract syntax for OpenMP directives
# =====================================

class OpenMPDirective(Statement):
    '''Abstract syntax node for parsed OpenMP directives.'''

    def __init__(self,
                 clauses: Dict[str, Any] = {},
                 original: UnknownDirective = None):
        super().__init__()
        # Directive keywords and clauses are all considered to be
        # "clauses", represented as a dict mapping keywords to clause
        # contents.  Directive keywords, or clauses with no contents,
        # are mapped to None. For some clauses, the contents will be
        # a raw string. For others, it will be represented using richer types.
        self.clauses = clauses
        self.original_directive = original
        # Corresponding "end" directive
        self.ended_by = None
        # Corresponding starting directive
        self.started_by = None

    def __str__(self):
        return ("OpenMPDirective[" + str(self.clauses) + "]")

    def get_directive_keywords(self) -> List[str]:
        '''Return a list of directive keywords present in the directive.'''
        return [kw for kw in self.clauses.keys()
                   if kw in recognised_directive_keywords
                   if self.clauses[kw] is None]

    def is_loop(self) -> bool:
        '''Is it a loop directive?'''
        if "end" in self.clauses.keys():
            return False
        for kw in self.clauses.keys():
            if kw in ["loop", "do", "distribute"]:
               return True
        return False

    def is_standalone(self) -> bool:
        '''Is it a standalone directive enclosing no statements?'''
        if "end" in self.clauses.keys():
            return False
        for kw in self.clauses.keys():
            if kw in ["barrier", "update"]:
               return True
        return False

    def is_singleton(self) -> bool:
        '''Is it a singleton directive enclosing a single statement?'''
        if "end" in self.clauses.keys():
            return False
        for kw in self.clauses.keys():
            if kw in ["loop", "do", "distribute"]:
               return True
        return False

    def get_singleton_body(self) -> Statement:
        '''Get the statement associated with a singleton directive.'''
        pos = self.position
        if self.is_singleton() and len(self.siblings[pos+1:]) > 0:
            return self.siblings[pos+1]
        # Shouldn't reach here as basic checks will have already caught it
        assert ValueError("OpenMP singleton directive has no statement")

    def get_body(self) -> Optional[List[Statement]]:
        '''Get the statements associated with the directive.'''
        pos = self.position
        if self.is_singleton() and len(self.siblings[pos+1:]) > 0:
            return [self.siblings[pos+1]]
        elif self.ended_by is not None:
            return self.siblings[pos+1:self.ended_by.position]
        return None

    def get_enclosing_directives(self) -> List[OpenMPDirective]:
        '''Get the stack of OpenMP directives that enlose this directive,
        innermost first.'''
        # Return empty list for an 'end' directive
        if self.started_by is not None:
            return []
        enclosing = []
        cursor = self
        pos = cursor.position - 1
        while pos >= 0:
            node = cursor.siblings[pos]
            if isinstance(node, OpenMPDirective):
                if node.started_by is not None:
                    pos = node.started_by.position
                elif not (node.is_standalone() or node.is_singleton()):
                    enclosing.append(node)
            pos -= 1
            if pos < 0 and cursor.parent is not None \
                       and isinstance(cursor.parent, Statement):
                cursor = cursor.parent
                pos = cursor.position
        return enclosing

    def get_inherited_clauses(self,
                              clause: str,
                              inherits_from: List[Tuple[str, str]] = \
                                  [("do", "parallel"),
                                   ("distribute", "teams")]
                             ) -> List[Any]:
        '''Get requested clause from the directive and its parent
        directive if clauses are inherited from the parent directive.'''
        clauses = []
        if clause in self.clauses and self.clauses[clause] is not None:
            clauses.append(self.clauses[clause])
        # Look for parent directive
        for (child, parent) in inherits_from:
            if child in self.clauses and parent not in self.clauses:
                enclosing = self.get_enclosing_directives()
                for d in enclosing:
                    if parent in d.clauses:
                        if (clause in d.clauses and
                                d.clauses[clause] is not None):
                            clauses.append(d.clauses[clause])
                        break
        return clauses

    def get_all_vars(self) -> Set[str]:
        '''Get all variables referenced in the directive body.'''
        stmts = self.get_body()
        if stmts is None:
            return []
        accesses = VariablesAccessMap()
        for stmt in stmts:
            accs = stmt.reference_accesses()
            accesses.update(accs)
        var_set = set([sig.var_name for sig in accesses.all_data_accesses()])

    def get_always_private(self) -> Set[str]:
        '''Determine variables, such as loop variables, that are always
        private within the body of a directive.'''
        stmts = self.get_body()
        if stmts is None:
            return set()
        loop_vars = [loop.variable.name for stmt in stmts
                                        for loop in stmt.walk(Loop)]
        return set(loop_vars)

    def get_vars_with_explicit_sharing_attribute(
            self,
            attributes: List[str]) -> Set[str]:
        '''Get variables with the given explicit sharing attribute.'''
        explicit_set = set()
        for attribute in attributes:
            for var_list in self.get_inherited_clauses(attribute):
                if isinstance(var_list, list):
                    explicit_set.update(var_list)
        return explicit_set

    def get_private_shared_vars(self) -> Tuple[Set[str], Set[str]]:
        '''Get the set of private variables and the set of shared variables.'''
        # Explicitly private variables
        private_attributes = ["private", "firstprivate", "lastprivate"]
        private = \
            self.get_vars_with_explicit_sharing_attribute(private_attributes)
        private.update(self.get_always_private())
        # Explicitly shared variables
        shared = self.get_vars_with_explicit_sharing_attribute(["shared"])
        # Removed shared vars that are declared as inner private vars
        for attribute in private_attributes:
            if attribute in self.clauses:
                for var in self.clauses[attribute]:
                    shared.discard(var)
        # Handle "default" clause
        defaults = self.get_inherited_clauses("default")
        if defaults and defaults[0] == "shared":
            shared.update(self.get_all_vars())
            shared.remove(private)
        elif defaults and defaults[0] in ["private", "firstprivate"]:
            private.update(self.get_all_vars())
            private.remove(shared)
        return (private, shared)

    def get_reduction_clauses(self) -> Set[Tuple[str, str]]:
        '''Get the reduction clauses for the directive.'''
        return self.get_vars_with_explicit_sharing_attribute(["reduction"])


# Partial OpenMP parser
# =====================


# Fortran identifier parser
def identifier():
    '''Parse a Fortran identifier'''
    return lift(lambda first, rest, _: first + "".join(rest),
                char(lambda x: x.isalpha()),
                many(char(lambda x: x.isalnum() or x == "_")),
                space())


# OpenMP keyword parser
# (For now, just any non-empty string of letters)
def keyword():
    '''Parse an OpenMP keyword'''
    return lift(lambda chars, _: "".join(chars),
                many1(char(lambda x: x.isalpha())),
                space())


# Liberal parser for OpenMP clause contents
def clause_contents():
    '''Consume raw text inside brackets, accounting for nested brackets'''
    def parse(txt, pos):
        if pos >= len(txt) or txt[pos] != "(":
            return ParseError(txt, pos)
        pos += 1
        start = pos
        nesting_level = 0
        while pos < len(txt):
            c = txt[pos]
            if c == "(":
                nesting_level += 1
            elif c == ")":
                if nesting_level == 0:
                    s = txt[start:pos]
                    pos += 1
                    while pos < len(txt) and txt[pos].isspace():
                        pos += 1
                    return (s, pos)
                nesting_level -= 1
            pos += 1
        return ParseError(txt, pos)
    return parse

# Parser for reduction operators
def omp_reduction_op():
    '''Parse an OpenMP reduction operator'''
    ops = ["+", "-", "*", ".and.", ".or.", ".eqv.", ".neqv",
           "max", "min", "iand", "ior", "ieor"]
    toks = [token(op) for op in ops]
    return choice(*toks)

# OpenMP clause parser
def omp_clause():
    '''Parse an OpenMP clause'''

    # Parser for data sharing clauses
    data_sharing_clause = lift(
        lambda keyword, _l, ids, _r: (keyword, ids),
        choice(token("private"),
               token("shared"),
               token("firstprivate"),
               token("lastprivate")),
        token("("),
        sepby(token(","), identifier()),
        token(")"))

    # Parser for reduction clauses
    reduction_clause = lift(
        lambda keyword, _l, op, _c, ids, _r:
            (keyword, [(op, i) for i in ids]), 
        token("reduction"),
        token("("),
        omp_reduction_op(),
        token(":"),
        sepby(token(","), identifier()),
        token(")"))

    # Parser for collapse clauses
    collapse_clause = lift(
        lambda keyword, _l, n, _r: (keyword, n), 
        token("collapse"),
        token("("),
        natural(),
        token(")"))

    # Generic clause parser
    other_clause = lift(
        lambda keyword, contents: (keyword, contents),
        keyword(),
        optional(clause_contents()))

    return choice(data_sharing_clause,
                  reduction_clause,
                  collapse_clause,
                  other_clause)


# OpenMP directive parser
def omp_directive():
    return lift(lambda _, cs: cs,
               token("omp"),
               many(omp_clause()))


# Top-level parser
def parse_omp_directive(directive: UnknownDirective) -> \
        Union[OpenMPDirective, StompMessage]:
    # Create and apply parser
    txt = directive.directive_string
    parser = omp_directive()
    result = parser(txt, 0)
    if isinstance(result, ParseError):
        remaining = result.txt[result.pos:]
        re.sub(" +", " ", remaining)
        return StompMessage(
                   StompMessageCode.OpenMPParseError,
                   "OpenMP directive parse error at " +
                       repr(remaining[:30]) + ".",
                   node=directive)
    # Accumulate clauses, with some basic checks
    (clauses, pos) = result
    if pos == len(txt):
        clause_map = {}
        for (keyword, contents) in clauses:
            if keyword in clause_map:
                # For duplicate clauses involving lists, merge them
                if (isinstance(clause_map[keyword], list) and
                        isinstance(contents, list)):
                    clause_map[keyword].extend(contents)
                else:
                    # For other duplicates, give an error
                    return StompMessage(
                       StompMessageCode.OpenMPParseError,
                       f"Duplicated keyword '{keyword}' in OpenMP directive.",
                       node=directive)
            clause_map[keyword] = contents
        return OpenMPDirective(clause_map, directive)
    else:
        # There is unparsed text remaining, which is a parse error
        remaining = txt[pos:]
        re.sub(" +", " ", remaining)
        return StompMessage(
                   StompMessageCode.OpenMPParseError,
                   "OpenMP directive parse error at " +
                       repr(remaining[:30]) + ".",
                   node=directive)


def merge_multiline_directives(psyir: Node):
    '''Merge multiline directives into a single directive.'''
    directives = psyir.walk(UnknownDirective)
    while len(directives) >= 2:
        d0 = directives[0]
        d1 = directives[1]
        d0_words = d0.directive_string.split(maxsplit=1)
        d1_words = d1.directive_string.split(maxsplit=1)
        if (d0.position+1 < len(d0.siblings) and
                d0.siblings[d0.position+1] is d1 and
                d0.directive_string.endswith("&") and
                (d0_words[0] == d1_words[0] or
                     d0_words[0] + "&" == d1_words[0])):
            d0._directive_string = (d0._directive_string[:-1] +
                                        " ".join(d1_words[1:]))
            del directives[1]
            del d1.siblings[d1.position]
        else:
            del directives[0]

# Identication of OpenMP directives
# =================================


def identify_openmp_directives(psyir: Node):
    '''Replace each 'UnknownDirective' with 'OpenMPDirective' if it can be
    successfully parsed as an OpenMP directive.'''
    for unknown in psyir.walk(UnknownDirective):
        d = parse_omp_directive(unknown)
        if isinstance(d, StompMessage):
            StompLogger.add_message(d)
        else:
            unknown.replace_with(d)
    associate_end_directives(psyir)


def associate_end_directives(psyir: Node):
    '''Associate each directive with its corresponding "end" directive, 
    if it has one.'''
    for omp_dir in psyir.walk(OpenMPDirective):
        if "end" not in omp_dir.clauses:
            open_dirs = [omp_dir]
            succs = omp_dir.siblings[omp_dir.position+1:]
            for succ in succs:
                if isinstance(succ, OpenMPDirective):
                    if "end" in succ.clauses:
                        # Match "end" directive against those that are open
                        while open_dirs:
                            open_dir = open_dirs.pop()
                            matches = open_dir.get_directive_keywords() == \
                                      succ.get_directive_keywords()
                            if matches and open_dirs == []:
                                omp_dir.ended_by = succ
                                succ.started_by = omp_dir
                            if matches:
                                break
                        if open_dirs == []:
                            break
                    else:
                       # Add directive to those that are open
                       open_dirs.append(succ)
