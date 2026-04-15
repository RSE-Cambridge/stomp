# SPDX-License-Identifier: BSD-3-Clause

'''This module provides a liberal abstract syntax and parsing for OpenMP
directives.'''

from __future__ import annotations
import re
from typing import Optional, Dict, Any, List, Union, Tuple, Set
from psyclone.psyir.nodes import Node, Statement, UnknownDirective, Loop, \
    BinaryOperation, IntrinsicCall
from psyclone.core import VariablesAccessMap
from stomp.parser_lib import lift, char, many, token, \
    ParseError, sepby, choice, many1, optional, space, natural
from stomp.message import StompMessage, StompMessageCode, StompLogger


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

    def is_loop(self, isolated: bool = False) -> bool:
        '''Is it a loop directive? If the isolated flag is provided,
        the loop must not be enclosed within a parallel region.'''
        if "end" in self.clauses:
            return False
        inherits_from = [("do", "parallel"),
                         ("distribute", "teams")]
        for (child, parent) in inherits_from:
            if child in self.clauses:
                if isolated and is_within_directive(self, [[parent]]):
                    return False
                return True
        return False

    def is_parallel_region(self) -> bool:
        '''Is it a parallel-region directive?'''
        if "end" in self.clauses.keys():
            return False
        for kw in self.clauses.keys():
            if kw in ["parallel", "teams"]:
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
            if kw in ["loop", "do", "distribute", "atomic"]:
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

    def get_all_vars(self) -> Set[str]:
        '''Get all variables referenced in the directive body.'''
        stmts = self.get_body()
        if stmts is None:
            return set()
        accesses = VariablesAccessMap()
        for stmt in stmts:
            accs = stmt.reference_accesses()
            accesses.update(accs)
        return set([sig.var_name for sig in accesses.all_data_accesses])

    def body_reference_accesses(self) -> VariablesAccessMap:
        accesses = VariablesAccessMap()
        stmts = self.get_body()
        if stmts is None:
            return accesses
        for stmt in stmts:
            accs = stmt.reference_accesses()
            accesses.update(accs)
        return accesses

    def get_always_private(self) -> Set[str]:
        '''Determine variables, such as loop variables, that are always
        private within the body of the directive.'''
        stmts = self.get_body()
        if stmts is None:
            return set()
        loop_vars = [loop.variable.name for stmt in stmts
                                        for loop in stmt.walk(Loop)]
        return set(loop_vars)

    def is_always_private(self, v: str) -> bool:
        '''Determine if given variable must be private within the body
        of the directive.'''
        return v in self.get_always_private()

    def is_private_var(
            self,
            v: str,
            kinds: List[str] = ["private", "firstprivate", "lastprivate"]
            ) -> bool:
        '''Determine if the given variable is private within the
        scope of the directive.'''
        # Check immediate clauses
        for kind in kinds:
            if v in self.clauses.get(kind, []): return True
        if v in self.clauses.get("shared", []): return False
        reduction_vars = [x for (op, x) in self.clauses.get("reduction", [])]
        if v in reduction_vars: return False
        if "private" in kinds and self.is_always_private(v): return True
        # For some directives, we need to look at enclosing directives
        inherits_from = [("do", "parallel"),
                         ("distribute", "teams")]
        for (child, parent) in inherits_from:
            if child in self.clauses and parent not in self.clauses:
                enclosing = get_enclosing_directives(self)
                for d in enclosing:
                    if parent in d.clauses:
                        return d.is_private_var(v, kinds)
                # If we reach here, we must be in a subroutine/function that
                # is called from a parallel/teams region, in which case
                # the variable is private iff it is a local variable, i.e.
                # not an argument or global.
                if "private" in kinds:
                    try:
                        symbol_table = self.scope.symbol_table
                        symbol = symbol_table.lookup(v)
                        return symbol.is_automatic
                    except Exception:
                        return False
        # If we are a parent directive, we need to resolve the default clause
        for (child, parent) in inherits_from:
            if parent in self.clauses:
                default = self.clauses.get("default", "shared")
                return default.strip() in kinds
        return False

    def is_firstprivate_var(self, v: str) -> bool:
        return self.is_private_var(v, kinds=["firstprivate"])

    def is_reduction_var(self, v: str) -> Optional[str]:
        '''Determine if given variable is a reduction variable within
        the scope of the directive. If not, return None, otherwise
        return the assoicated reduction operator.'''
        for (op, x) in self.clauses.get("reduction", []):
            if v == x:
                return op
        # For some directives, we need to look at enclosing directives
        inherits_from = [("do", "parallel"),
                         ("distribute", "teams")]
        for (child, parent) in inherits_from:
            if child in self.clauses and parent not in self.clauses:
                enclosing = get_enclosing_directives(self)
                for d in enclosing:
                    if parent in d.clauses:
                        return d.is_reduction_var(v)
        return None

    def is_shared_var(self, v: str) -> bool:
        '''Determine if the given variable is shared within the
        scope of the directive.'''
        if self.is_private_var(v) or self.is_reduction_var(v):
            return False
        return True

    def get_private_shared_red(self) \
            -> Tuple[Set[str], Set[str], Set[Tuple[str, str]]]:
        '''Get the set of private variables, shared variables, and reduction
        clauses for the scope of the directive.'''
        all_vars = self.get_all_vars()
        private = set([])
        shared = set([])
        red = set([])
        for v in all_vars:
            if self.is_private_var(v):
                private.add(v)
            else:
                red_op = self.is_reduction_var(v)
                if red_op:
                    red.add((red_op, v))
                else:
                    shared.add(v)
        return (private, shared, red)


def get_enclosing_directives(origin: Node) -> List[OpenMPDirective]:
    '''Get the stack of OpenMP directives that enlose the given node,
    innermost first. If the node itself is a directive, it will not
    be counted as an enclosing directive.'''
    enclosing = []
    cursor = origin
    while cursor:
        if isinstance(cursor, Statement):
            start_pos = cursor.position
            pos = start_pos
            while pos >= 0:
                node = cursor.siblings[pos]
                if isinstance(node, OpenMPDirective):
                    if node.started_by is not None:
                        # Skip over directive body
                        pos = node.started_by.position
                    elif node.is_standalone():
                        # Ignore standalone directives
                        pass
                    elif node.is_singleton() and pos+1 != start_pos:
                        # Skip singleton directives
                        pass
                    else:
                        if node is not origin:
                            enclosing.append(node)
                pos -= 1
        cursor = cursor.parent
    return enclosing


def is_within_directive(node: Node,
                        within: List[List[str]],
                        not_within: List[List[str]] = []) -> OpenMPDirective:
    '''Determine if the given node is enslosed by one of a list of directives
    (within) before being enclosed by one of a list of other directives
    (not_within). If the node itself is a directive, it will be considered
    as an enclosing directive.'''
    enclosing = []
    if isinstance(node, OpenMPDirective):
        enclosing.append(node)
    enclosing.extend(get_enclosing_directives(node))
    for enc in enclosing:
        for dir_list in not_within:
            if all([d in enc.clauses for d in dir_list]):
                return None
        for dir_list in within:
            if all([d in enc.clauses for d in dir_list]):
                return enc
    return None


def is_child_directive(child: Node, parent: OpenMPDirective) -> bool:
    '''Determine if the given node is enslosed by the parent directive node.'''
    if child is parent:
        return True
    for enc in get_enclosing_directives(child):
        if enc is parent:
            return True
    return False


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


# OpenMP reduction operators
# ==========================

# Mapping from PSyIR reduction operator to string.
MAP_REDUCTION_OP_TO_STR = {
    BinaryOperation.Operator.ADD: "+",
    BinaryOperation.Operator.SUB: "-",
    BinaryOperation.Operator.MUL: "*",
    BinaryOperation.Operator.AND: ".and.",
    BinaryOperation.Operator.OR: ".or.",
    BinaryOperation.Operator.EQV: ".eqv.",
    BinaryOperation.Operator.NEQV: ".neqv.",
    IntrinsicCall.Intrinsic.MAX: "max",
    IntrinsicCall.Intrinsic.MIN: "min",
    IntrinsicCall.Intrinsic.IAND: "iand",
    IntrinsicCall.Intrinsic.IOR: "ior",
    IntrinsicCall.Intrinsic.IEOR: "ieor",
}
