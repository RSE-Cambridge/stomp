# SPDX-License-Identifier: BSD-3-Clause

'''This module implements static checks.'''

from psyclone.psyir.nodes import Node, Routine, Loop
from stomp.openmp_directives import \
    OpenMPDirective, recognised_directives_set, \
    is_within_directive, is_child_directive, \
    get_enclosing_directives
from stomp.message import StompMessageCode, StompLogger
from stomp.region_conflict_analysis import RegionConflictAnalysis
from stomp.misc import is_array_access, get_nested_loops


# Basic checks that apply to every directive
# ==========================================


def check_loose_end(d: OpenMPDirective):
    '''Check that an "end" directive has a matching starting directive.'''
    if "end" in d.clauses and d.started_by is None:
        StompLogger.add_message(
            StompMessageCode.UnmatchedEnd,
            description = "Could not find associated starting "
                "directive for this OpenMP 'end' directive.",
            directive_node = d.original_directive)


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
                    directive_node = d.original_directive)


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
                        directive_node = d.original_directive)


def check_singleton_directive_not_empty(d: OpenMPDirective):
    '''Check that singleton directives are followed by a statement.'''
    if "end" not in d.clauses:
        if d.is_singleton():
            if len(d.siblings[d.position+1:]) == 0:
                StompLogger.add_message(
                    StompMessageCode.SingletonDirEmpty,
                    description = "OpenMP singleton directive has "
                        "no associated statement.",
                    directive_node = d.original_directive)


def check_standalone_directive_not_end(d: OpenMPDirective):
    '''Check that standalone directives are not end directives.'''
    if "end" in d.clauses and d.is_standalone():
        StompLogger.add_message(
            StompMessageCode.EndStandaloneDir,
            description = "Standalone OpenMP directive should not "
                "have an associated 'end' directive.",
            directive_node = d.original_directive)


def check_directive_is_recognised(d: OpenMPDirective):
    '''Check that directives are recognised OpenMP directives.'''
    kws = d.get_directive_keywords()
    if kws and kws[0] == "end":
        del kws[0]
    if tuple(kws) not in recognised_directives_set:
        StompLogger.add_message(
            StompMessageCode.UnrecognisedDirective,
            description = "This is not a recognised OpenMP directive.",
            directive_node = d.original_directive)


# Collapsed loop checks
# =====================


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
                directive_node = d.original_directive)
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
                 directive_node = d.original_directive)
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
                directive_node = d.original_directive,
                node = loop)


# Data sharing checks
# ===================


def check_data_sharing_clauses(d: OpenMPDirective):
    '''Basic checks for variables mentioned in data sharing clauses.'''
    # Check that loop variables are not declared as shared
    must_be_private = d.get_always_private()
    (private, shared, red) = d.get_private_shared_red()
    contradiction = must_be_private & shared
    if contradiction:
        StompLogger.add_message(
            StompMessageCode.DataSharingConflict,
            description = f"Variable '{contradiction.pop()}' "
                f"must be private but is declared as 'shared'.",
            directive_node = d.original_directive)


# Parallel scalar access checks
# =============================


def check_parallel_scalar_accesses(psyir: Node):
    '''Various checks for scalar accesses within parallel directives.'''
    # Iterate over all accesses that are enclosed by parallel directive
    par_region = [["parallel"], ["teams"]]
    par_loop = [["do"], ["distribute"]]
    par = par_region + par_loop
    safe = [["critical"], ["atomic"], ["single"], ["master"]]
    for routine in psyir.walk(Routine):
        accesses = routine.reference_accesses()
        for (sig, seq) in accesses.items():
            for (i, info) in enumerate(seq):
                d = is_within_directive(info.node, par)

                # Write access to a shared variable must be protected
                bad = d and \
                      info.is_any_write() and \
                      not is_array_access(info) and \
                      d.is_shared_var(sig.var_name) and \
                      not is_within_directive(info.node, safe)
                if bad:
                    StompLogger.add_message(
                        StompMessageCode.ParallelScalarConflict,
                        description = f"Unprotected parallel write to shared "
                            f"variable '{sig.var_name}'.",
                        node = info.node,
                        directive_node = d.original_directive,
                        routine_name = routine.name)
                    break

                # Read of private (not firstprivate) scalar must be initialised
                region = is_within_directive(info.node, par_region)
                bad = d and \
                      info.is_any_read() and \
                      not is_array_access(info) and \
                      d.is_private_var(sig.var_name) and \
                      not d.is_firstprivate_var(sig.var_name) and \
                      not d.is_always_private(sig.var_name)
                if bad:
                    # Look for preceeding initialiser
                    ok = False
                    for pre in reversed(seq[0:i]):
                        ok = pre.is_any_write() and \
                                 (region is None or
                                  is_child_directive(pre.node, region))
                        if ok: break
                    if not ok:
                        StompLogger.add_message(
                            StompMessageCode.ReadUninitialisedPrivate,
                            description = f"Parallel loop reads "
                                f"uninitialised private variable "
                                f"'{sig.var_name}'.",
                            node = info.node,
                            directive_node = d.original_directive,
                            routine_name = routine.name)
                        break


# Parallel array access checks
# ============================


def check_parallel_array_accesses(psyir: Node):
    '''Check all OpenMP teams/parallel regions for array access
    conflicts, where at least two accesses (one of which is a write)
    access the same indices of the same array in different threads.'''

    for routine in psyir.walk(Routine):
        for d in routine.walk(OpenMPDirective):
            if "end" in d.clauses: continue
            # Look for "teams" directives, or parallel directives not
            # enclosed by a "teams" directive
            ok = False
            if "teams" in d.clauses:
                ok = True
            elif "parallel" in d.clauses:
                enclosing = get_enclosing_directives(d)
                ok = all(["teams" not in e.clauses for e in enclosing])
            if not ok: continue

            # Apply the region conflict analysis
            analysis = RegionConflictAnalysis()
            conflicts = analysis.get_region_conflicts(d)
            for (sig, msg) in conflicts:
                if msg is None:
                    continue
                StompLogger.add_message(
                    StompMessageCode.ParallelArrayConflict,
                    description = "Array access conflict in "
                        "parallel region. " + msg + ".",
                    directive_node = d.original_directive,
                    routine_name = routine.name)
