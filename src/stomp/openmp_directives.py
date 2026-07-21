# SPDX-License-Identifier: BSD-3-Clause

'''This module provides a liberal abstract syntax and parsing for OpenMP
directives.'''

from __future__ import annotations
import re
from typing import Optional, Dict, Any, List, Union, Tuple, Set
from psyclone.psyir.nodes import Node, Statement, UnknownDirective, Loop, \
    BinaryOperation, IntrinsicCall, Reference
from psyclone.core import VariablesAccessMap
from psyclone.psyir.symbols import SymbolTable
from stomp.parser_lib import lift, char, many, token, \
    ParseError, sepby, choice, many1, optional, space, natural, chain
from stomp.module_spec_directives import is_threadprivate
from stomp.message import StompMessage, StompMessageCode, StompLogger
from stomp.misc import parse_fortran_expr


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
    ["section"],
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


# Recognised stomp directives
# ===========================

# As well as standard "!$omp" directives, we also support custom "!$stomp"
# directives.

stomp_recognised_directives_list = [
    ["assume"],
    ["pure"],
    ["safe"],
    ["unique"],
]

# As a set for fast membership checking
stomp_recognised_directives_set = set([
    tuple(kw_list) for kw_list in stomp_recognised_directives_list])

# Abstract syntax for OpenMP directives
# =====================================


class OpenMPDirective(Statement):
    '''Abstract syntax node for parsed OpenMP directives. Both "!$omp" 
    and "!$stomp" directives get parsed as OpenMPDirective but the two
    can be distinguished using the "is_stomp_directive" member variable.
    '''

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
        # All references accessed by directive body
        self.accesses = None
        # Variables accessed in the directive body that must be private
        self.always_private = None
        # Is it a stomp-specific directive?
        self.is_stomp_directive = False

    def __str__(self):
        return ("OpenMPDirective[" + str(self.clauses) + "]")

    def get_allowed_keywords_set(self):
        '''Get the set of recognised directive keywords.'''
        if self.is_stomp_directive:
            return stomp_recognised_directives_set
        else:
            return recognised_directives_set

    def get_directive_keywords(self) -> List[str]:
        '''Return a list of directive keywords present in the directive.'''
        kws = list(self.clauses.keys())
        if kws and kws[0] == "end":
            kws.pop(0)
        while kws:
            if tuple(kws) in self.get_allowed_keywords_set():
                return kws
            else:
                kws.pop(-1)
        return []

    def is_loop(self, isolated: bool = False) -> bool:
        '''Is it a loop directive? If the isolated flag is provided,
        the loop must not be enclosed within a parallel region.'''
        if "end" in self.clauses:
            return False
        inherits_from = [("do", "parallel"),
                         ("simd", "parallel"),
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
            if self.is_stomp_directive:
                if kw in ["assume", "pure", "unique"]:
                    return True
            else:
                if kw in ["barrier", "update", "flush", "section"]:
                    return True
        return False

    def is_singleton(self) -> bool:
        '''Is it a singleton directive enclosing a single statement?'''
        if "end" in self.clauses.keys():
            return False
        for kw in self.clauses.keys():
            if kw in ["loop", "do", "distribute", "atomic", "simd"]:
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

    def body_reference_accesses(self) -> VariablesAccessMap:
        '''Get all variable accesses in the directive body. These are cached
        for performance.'''
        if self.accesses is None:
            self.accesses = VariablesAccessMap()
            stmts = self.get_body()
            if stmts is not None:
                for stmt in stmts:
                    accs = stmt.reference_accesses()
                    self.accesses.update(accs)
        return self.accesses

    def get_all_vars(self) -> Set[str]:
        '''Get all variables referenced in the directive body.'''
        accesses = self.body_reference_accesses()
        return set([sig.var_name for sig in accesses.all_data_accesses])

    def get_always_private(self) -> Set[str]:
        '''Determine variables, such as loop variables and threadprivate
        variables, that are always private within the body of the directive.'''
        if self.always_private is None:
            stmts = self.get_body()
            if stmts is None:
                return set()
            self.always_private = set()
            # Add loop variables
            self.always_private.update([
                loop.variable.name for stmt in stmts
                                   for loop in stmt.walk(Loop)])
            # Add threadprivate variables
            accesses = self.body_reference_accesses()
            for (sig, seq) in accesses.items():
                for info in seq:
                    if (isinstance(info.node, Reference) and
                           is_threadprivate(info.node)):
                        self.always_private.add(sig.var_name)
                        break
        return self.always_private

    def is_always_private(self, v: str) -> bool:
        '''Determine if given variable must be private within the body
        of the directive.'''
        return v in self.get_always_private()

    def get_private_shared(self: OpenMPDirective,
                           ignore_firstprivate: bool = False) -> \
            Tuple[set[str], set[str]]:
        '''Get the set of private variables/shared variables for the 
        directives. For "teams" and "parallel" directives, the "default"
        clause is resolved.'''

        # Determine private variables
        private = self.get_always_private()
        private.update(self.clauses.get("private", []))
        firstprivate = set(self.clauses.get("firstprivate", []))
        if not ignore_firstprivate:
            private.update(firstprivate)
        private.update(self.clauses.get("lastprivate", []))
        if "reduction" in self.clauses:
            private.update([red[1] for red in self.clauses["reduction"]])

        # Determine shared variables
        shared = set(self.clauses.get("shared", []))

        # Resolve the "default" clause
        if "teams" in self.clauses or "parallel" in self.clauses:
            unspecified = (self.get_all_vars() - private -
                firstprivate - shared)
            default = self.clauses.get("default", "shared")
            if default == "none":
                pass
            elif default == "shared":
                shared.update(unspecified)
            elif default == "firstprivate" and ignore_firstprivate:
                pass
            else:
                private.update(unspecified)

        return (private, shared)


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
# (For now, just any non-empty string of letters and underscores)
def keyword():
    '''Parse an OpenMP keyword'''
    return lift(lambda chars, _: "".join(chars),
                many1(char(lambda x: x.isalpha() or x == "_")),
                space())


# Bracket-aware text parser
def raw_text():
    '''Consume raw text until the next non-nested ")", allowing
    nested brackets. The closing bracket is not consumed.'''
    def parse(txt, pos):
        if pos >= len(txt):
            return ParseError(txt, pos)
        nesting_level = 0
        start = pos
        while pos < len(txt):
            c = txt[pos]
            if c == "(":
                nesting_level += 1
            elif c == ")":
                if nesting_level == 0:
                    s = txt[start:pos]
                    return (s, pos)
                nesting_level -= 1
            pos += 1
        return ParseError(txt, pos)
    return parse


# Fortran expression parser
def fortran_expr(symbol_table: Optional[SymbolTable] = None):
    '''Parse Fortran expression up until next non-nested ")"'''
    def parse(txt, pos):
        result = raw_text()(txt, pos)
        if isinstance(result, ParseError):
            return result
        node = parse_fortran_expr(result[0], symbol_table)
        if isinstance(node, str):
            return ParseError(txt, pos)
        return (node, result[1])
    return parse


# Parser for reduction operators
def omp_reduction_op():
    '''Parse an OpenMP reduction operator'''
    ops = ["+", "-", "*", ".and.", ".or.", ".eqv.", ".neqv",
           "max", "min", "iand", "ior", "ieor"]
    toks = [token(op) for op in ops]
    return choice(*toks)


# OpenMP clause parser
def omp_clause(symbol_table: Optional[SymbolTable] = None):
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

    # Parser for num_threads clause
    num_threads_clause = lift(
        lambda keyword, _l, expr, _r: (keyword, expr),
        token("num_threads"),
        token("("),
        fortran_expr(symbol_table),
        token(")"))

    # Parser for thread_limit clause
    thread_limit_clause = lift(
        lambda keyword, _l, expr, _r: (keyword, expr),
        token("thread_limit"),
        token("("),
        fortran_expr(symbol_table),
        token(")"))

    # Parser for schedule clause
    schedule_clause = lift(
        lambda keyword, _l, mods, kind, chunk_size, _r:
            (keyword, (mods, kind, chunk_size)),
        token("schedule"),
        token("("),
        sepby(token(","), choice(token("monotonic"),
                                 token("non-monotonic"),
                                 token("simd"))),
        choice(token("auto"),
               token("dynamic"),
               token("guided"),
               token("runtime"),
               token("static")),
        optional(lift(lambda _, chunk_size: chunk_size,
                      token(","),
                      raw_text())),
        token(")"))

    # Parser for critical directive
    critical_clause = lift(
        lambda keyword, name: (keyword, name[1] if name else None),
        token("critical"),
        optional(chain(
            token("("),
            identifier(),
            token(")"))))

    # Generic clause parser for clauses that may be duplicated
    duplicatable_clause = lift(
        lambda keyword, contents: (keyword, [contents]),
        choice(token("map"),
               token("depend")),
        optional(lift(
            lambda _l, text, _r: text,
            token("("),
            raw_text(),
            token(")"))))

    # Generic clause parser
    other_clause = lift(
        lambda keyword, contents: (keyword, contents),
        keyword(),
        optional(lift(
            lambda _l, text, _r: text,
            token("("),
            raw_text(),
            token(")"))))

    return choice(data_sharing_clause,
                  reduction_clause,
                  collapse_clause,
                  num_threads_clause,
                  thread_limit_clause,
                  schedule_clause,
                  critical_clause,
                  duplicatable_clause,
                  other_clause)


# OpenMP directive parser
def omp_directive(symbol_table: Optional[SymbolTable] = None):
    return lift(lambda d, cs: (d, cs),
                token("omp"),
                many(omp_clause(symbol_table)))


# Stomp clause parser
def stomp_clause(symbol_table: Optional[SymbolTable] = None):
    '''Parse a stomp clause'''

    # Parser for fortran-expression clauses
    expr_clause = lift(
        lambda keyword, _l, expr, _r: (keyword, expr),
        choice(token("assume"),
               token("unique")),
        token("("),
        fortran_expr(symbol_table),
        token(")"))

    # Parser identifier-list clauses
    id_list_clause = lift(
        lambda keyword, _l, ids, _r: (keyword, ids),
        token("pure"),
        token("("),
        sepby(token(","), identifier()),
        token(")"))

    # Parser for simple clauses
    simple_clause = lift(
        lambda keyword: (keyword, None),
        choice(token("end"),
               token("safe")))

    return choice(expr_clause,
                  id_list_clause,
                  simple_clause)


# Stomp directive parser
def stomp_directive(symbol_table: Optional[SymbolTable] = None):
    return lift(lambda d, cs: (d, cs),
                token("stomp"),
                many(stomp_clause(symbol_table)))


# Top-level parser
def parse_omp_directive(directive: UnknownDirective) -> \
        Optional[Union[OpenMPDirective, StompMessage]]:
    # Get symbol table
    symbol_table = directive.scope.symbol_table
    # Create and apply parser
    txt = directive.directive_string.partition("!")[0].lower()
    parser = choice(omp_directive(symbol_table),
                    stomp_directive(symbol_table))
    result = parser(txt, 0)
    if isinstance(result, ParseError):
        if result.pos == 0:
            # Ignore directive if no text was consumed at all
            return None
        remaining = result.txt[result.pos:]
        re.sub(" +", " ", remaining)
        return StompMessage(
                   StompMessageCode.OpenMPParseError,
                   "OpenMP directive parse error at " +
                       repr(remaining[:30]) + ".",
                   node=directive)
    # Accumulate clauses, with some basic checks
    ((top_dir, clauses), pos) = result
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
            else:
                clause_map[keyword] = contents
        d = OpenMPDirective(clause_map, directive)
        d.is_stomp_directive = top_dir == "stomp"
        return d
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
        if d is None: continue
        if isinstance(d, StompMessage):
            StompLogger.add_msg(d)
        else:
            unknown.replace_with(d)
    associate_end_directives(psyir)
    insert_end_directives(psyir)


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


def insert_end_directives(psyir: Node):
    '''Insert explicit "end" directives which are otherwise implicit.'''
    for d in psyir.walk(OpenMPDirective):
        if d.ended_by is None and d.is_singleton():
            if d.get_body():
                kws = d.get_directive_keywords()
                end = OpenMPDirective({kw: None for kw in ["end"] + kws})
                d.ended_by = end
                end.started_by = d
                d.siblings.insert(d.position+2, end)


# Helper functions for OpenMP directives
# ======================================


def get_enclosing_directives(origin: Node) -> List[OpenMPDirective]:
    '''Get the stack of OpenMP directives that enlose the given node,
    innermost first. If the node itself is a directive, it will not
    be counted as an enclosing directive.'''
    # Enclosing directives are cached, so first check the cache
    if hasattr(origin, "cached_omp_enclosing_dirs"):
        return origin.cached_omp_enclosing_dirs

    # Find the enclosing directives
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

    # Cache the result
    origin.cached_omp_enclosing_dirs = enclosing

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


def drop_omp_dir_bodies(stmts: List[Statement]):
    '''Drop OpenMP directive bodies, but not their associated opening
    directives, from the given list of statements'''
    result = []
    i = 0
    while i < len(stmts):
        stmt = stmts[i]
        result.append(stmt)
        if isinstance(stmt, OpenMPDirective):
            if stmt.ended_by:
                while i < len(stmts):
                    if stmts[i] is stmt.ended_by: break
                    i += 1
            elif stmt.is_singleton():
                i += 1
        i += 1
    return result


def get_sections(d: OpenMPDirective) -> List[List[Statement]]:
    '''Extract the individual sections from a 'sections' directive.'''
    if "sections" not in d.clauses: return []
    section = []
    sections = []
    region_body = d.get_body()
    if region_body:
        for s in drop_omp_dir_bodies(region_body):
            if isinstance(s, OpenMPDirective):
                if "section" in s.clauses:
                    if section: sections.append(section)
                    section = []
                    continue
            section.append(s)
        if section: sections.append(section)
        return sections
    return []


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
