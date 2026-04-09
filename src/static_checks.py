# SPDX-License-Identifier: BSD-3-Clause

'''This module implements static checks.'''

import re
from typing import List
from psyclone.psyir.nodes import Node, Statement, Routine, Loop
from openmp_directives import OpenMPDirective, recognised_directives_set
from stomp_message import StompMessage, StompMessageCode, StompLogger
from array_index_analysis import ArrayIndexAnalysis


# Basic checks that apply to every directive
# ==========================================


def check_loose_end(d: OpenMPDirective):
    '''Check that an "end" directive has a matching starting directive.'''
    if "end" in d.clauses and d.started_by is None:
        StompLogger.add_message(
            StompMessageCode.UnmatchedEnd,
            description = "Could not find associated starting "
                "directive for this OpenMP 'end' directive.",
            node = d.original_directive)


def check_loop_directive_is_followed_by_loop(d: OpenMPDirective):
    '''Check that a loop directive is followed by a loop.'''
    if "end" not in d.clauses:
        if d.is_loop():
            is_loop = d.position+1 < len(d.siblings) and \
                      isinstance(d.siblings[d.position+1], Loop)
            if not is_loop:
                StompLogger.add_message(
                    StompMessageCode.LoopDirectiveHasNoLoop,
                    description = "OpenMP loop directive is not "
                                  "followed by a loop.",
                    node = d.original_directive)


def check_singleton_directive_num_stmts(d: OpenMPDirective):
    '''Check that singleton directives with an associated "end" directive
    contain exactly one statement.'''
    if "end" not in d.clauses:
        if d.is_singleton():
            if d.ended_by is not None:
                num_stmts = d.ended_by.position - d.position - 1
                if num_stmts != 1:
                    StompLogger.add_message(
                        StompMessageCode.SingleStatementExpected,
                        description = f"OpenMP directive should hold a "
                            f"single statement but {num_stmts} statements "
                            f"have been provided.",
                        node = d.original_directive)


def check_singleton_directive_not_empty(d: OpenMPDirective):
    '''Check that singleton directives are followed by a statement.'''
    if "end" not in d.clauses:
        if d.is_singleton():
            if len(d.siblings[d.position+1:]) == 0:
                StompLogger.add_message(
                    StompMessageCode.SingletonDirEmpty,
                    description = "OpenMP singleton directive has "
                        "no associated statement.",
                    node = d.original_directive)


def check_standalone_directive_not_end(d: OpenMPDirective):
    '''Check that standalone directives are not end directives.'''
    if "end" in d.clauses and d.is_standalone():
        StompLogger.add_message(
            StompMessageCode.EndStandaloneDir,
            description = "Standalone OpenMP directive should not "
                "have an associated 'end' directive.",
            node = d.original_directive)


def check_directive_is_recognised(d: OpenMPDirective):
    '''Check that directives are recognised OpenMP directives.'''
    kws = d.get_directive_keywords()
    if kws and kws[0] == "end":
        del kws[0]
    if tuple(kws) not in recognised_directives_set:
        StompLogger.add_message(
            StompMessageCode.UnrecognisedDirective,
            description = "This is not a recognised OpenMP directive.",
            node = d.original_directive)


# Collapsed loop checks
# =====================


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


def check_collapse_clause(d: OpenMPDirective):
    '''Check that all OpenMP loops with a collapse(n) clause preceed an
    n-element loop nest, and the loop ranges are not data dependent.'''
    if d.is_loop() and d.is_singleton() and "collapse" in d.clauses:
        # Check that collapse clause is non-zero
        if d.clauses["collapse"] == 0:
            StompLogger.add_message(
                StompMessageCode.InvalidCollapseClause,
                description = "A 'collapse' clause with a value of 0 "
                    "is not allowed.",
                node = d.original_directive)
        # Check that num loops are consistent with collapse clause
        loop = d.get_singleton_body()
        loops = get_nested_loops(loop)
        expected = d.clauses["collapse"]
        got = len(loops)
        if got < expected:
            StompLogger.add_message(
                 StompMessageCode.InvalidCollapseClause,
                 description = f"Collapse clause suggests "
                     f"{expected} nested loops but only {got} found.",
                 node = d.original_directive)
        # Check for data dependencies between the variable of an outer loop
        # and the ranges of its inner loops
        found = False
        loop = loops.pop(0)
        while loops:
            loop_exprs = []
            loop_exprs.extend([loop.start_expr for loop in loops])
            loop_exprs.extend([loop.stop_expr for loop in loops])
            loop_exprs.extend([loop.step_expr for loop in loops])
            for expr in loop_exprs:
                if expr is None: continue
                for sig in expr.reference_accesses().all_data_accesses:
                    if loop.variable.name == str(sig):
                        found = True
                        break
                if found: break
            if found: break
            loop = loops.pop(0)
        if found:
            StompLogger.add_message(
                StompMessageCode.NonRectangularLoop,
                description = f"Found a non-rectangular collapsed loop nest: "
                    f"the range of an inner loop depends on an outer loop "
                    f"variable, namely '{loop.variable.name}'. This may not "
                    f"be supported by your OpenMP implementation.",
                node = d.original_directive)
                        

# Data sharing checks
# ===================


def check_data_sharing_clauses(d: OpenMPDirective):
    '''Basic checks for variables mentioned in data sharing clauses.'''
    # Check that loop variables are not declared as shared
    must_be_private = d.get_always_private()
    (private, shared) = d.get_private_shared_vars()
    contradiction = must_be_private & shared
    if contradiction:
        StompLogger.add_message(
            StompMessageCode.DataSharingConflict,
            description = f"Variable '{contradiction.pop()}' "
                f"must be private but occurs in a 'shared' clause.",
            node = d.original_directive)


# Parallel array access checks
# ============================


def check_loop_array_accesses(psyir: Node):
    '''Check all OpenMP loops for parallel array access conflicts, where at
    least two accesses (one of which is a write) access the same indices of
    the same array in different loop iterations.'''

    for routine in psyir.walk(Routine):
        for d in routine.walk(OpenMPDirective):
            if d.is_loop() and d.is_singleton():
                # Ignore loops executed by a single thread
                single = False
                enclosing = d.get_enclosing_directives()
                enclosing.insert(0, d)
                for enc in enclosing:
                    if "parallel" in enc.clauses:
                        break
                    if ("master" in enc.clauses or
                            "single" in enc.clauses):
                        single = True
                        break
                if single:
                    return

                # Analyse loops executed by a multiple threads
                num_loops = 1
                if "collapse" in d.clauses:
                    num_loops = d.clauses["collapse"]
                outer_loop = d.get_singleton_body()
                loops = get_nested_loops(outer_loop)[0:num_loops]
                for loop in loops:
                    (private, shared) = d.get_private_shared_vars()
                    reduction_vars = {c[1] for c in d.get_reduction_clauses()}
                    analysis = ArrayIndexAnalysis()
                    conflicts = analysis.get_loop_conflicts(
                                    loop,
                                    private = private | reduction_vars,
                                    shared = shared)
                    for (sig, msg) in conflicts:
                        if msg is None:
                            continue
                        StompLogger.add_message(
                            StompMessageCode.LoopArrayConflict,
                            description = "Array access conflict in "
                                "parallel loop. " + msg + ".",
                            node = d.original_directive)
