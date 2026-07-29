# SPDX-License-Identifier: BSD-3-Clause

'''This module implements static checks.'''

from typing import Optional
from psyclone.core import Signature
from psyclone.psyir.nodes import \
  Node, Routine, Loop, Call, IntrinsicCall, \
  FileContainer, CodeBlock
from psyclone.psyir.tools import ReductionInferenceTool
from psyclone.core.access_type import AccessType
from psyclone.psyir.symbols import DataTypeSymbol
from stomp.openmp_directives import \
    OpenMPDirective, \
    get_enclosing_directives, \
    MAP_REDUCTION_OP_TO_STR, \
    is_within_directive
from stomp.message import StompMessageCode, StompLogger
from stomp.fortran_to_z3 import \
    FortranToZ3, TranslationNotSupported
from stomp.loop_conflict_analysis import \
    LoopConflictAnalysis, LoopConflictAnalysisOptions
from stomp.region_conflict_analysis import \
    RegionConflictAnalysis, RegionConflictAnalysisOptions
from stomp.misc import is_array_access, get_nested_loops, node_text
from stomp.module_spec_directives import is_threadsafe
from stomp.solver_options import SMTSolverOptions


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
    if tuple(kws) not in d.get_allowed_keywords_set():
        StompLogger.add_message(
            StompMessageCode.UnrecognisedDirective,
            description = "This is not a recognised OpenMP directive.",
            directive_node = d.original_directive)


def check_ordered_directives(d: OpenMPDirective):
    '''For an "ordered" directive inside a "do" directive, the "do"
    directive must contain the "ordered" clause.'''
    if "end" in d.clauses: return
    if "ordered" in d.clauses and "do" not in d.clauses:
        for e in get_enclosing_directives(d):
            if "do" in e.clauses:
                if "ordered" not in e.clauses:
                    StompLogger.add_message(
                        StompMessageCode.StrayOrderedDirective,
                        description = "Found 'ordered' directive enclosed "
                            "by a 'do' directive without the 'ordered' "
                            "clause.",
                        directive_node = d.original_directive)
                break


def check_sections_directive(d: OpenMPDirective):
    '''Check that the first statement in the body of a "sections"
    directive is a "section" directive.'''
    if "sections" in d.clauses:
        body = d.get_body()
        if body is None: return
        for stmt in body:
            if isinstance(stmt, OpenMPDirective):
                if "section" in stmt.clauses:
                    return
                else:
                    break
        StompLogger.add_message(
            StompMessageCode.MalformedSectionsDirective,
            description = "The first statement in the body of "
                "'sections' directive must be a 'section' directive.",
            directive_node = d.original_directive)


def check_nowait(d: OpenMPDirective):
    '''Check for directives where "nowait" is used but not allowed.'''
    if "end" not in d.clauses and "nowait" in d.clauses:
        StompLogger.add_message(
            StompMessageCode.BadNowait,
            description = "The 'nowait' clause is only allowed"
                "in an 'end' directive.",
            directive_node = d.original_directive)
    if "end" in d.clauses and "nowait" in d.clauses:
        disallowed = ["parallel"]
        for c in disallowed:
            if c in d.clauses:
                StompLogger.add_message(
                    StompMessageCode.BadNowait,
                    description = f"The 'nowait' clause is not allowed "
                        f"in a '{c}' directive.",
                    directive_node = d.original_directive)
                return
    if "copyprivate" in d.clauses and d.ended_by:
        if "nowait" in d.ended_by.clauses:
                 StompLogger.add_message(
                    StompMessageCode.BadNowait,
                    description = "The 'nowait' clause is not allowed "
                        "in combination with the 'copyprivate' clause.",
                    directive_node = d.original_directive,
                    node = d.ended_by)


def check_misplaced_directive(d: OpenMPDirective):
    '''Check that directives are used within a valid context.'''
    valid_nesting = {
        "teams": ["target"],
        "distribute": ["teams"],
        "parallel": ["teams", "distribute", "target"],
        "do": ["parallel"],
        "single": ["parallel"],
        "master": ["parallel"],
        "sections": ["parallel"],
        "barrier": ["parallel"],
        "critical": ["parallel"]
    }
    # Ignore "end" directives
    if "end" in d.clauses: return
    # Get enclosing directives
    enclosing = get_enclosing_directives(d)
    # Allow no enclosing directives
    if not enclosing: return
    # Otherwise, check for a valid nesting
    for (inner, outers) in valid_nesting.items():
        if inner in d.clauses:
            if any([outer in d.clauses for outer in outers]): continue
            ok = False
            for outer in outers:
                ok = any([outer in e.clauses for e in enclosing])
                if ok: break
            if not ok:
                StompLogger.add_message(
                    StompMessageCode.MisplacedDirective,
                    description = f"A '{inner}' directive can only occur "
                        f"in the body of the following directives: "
                        f"{outers}. (Note that stomp does not support "
                        f"nested parallelism.)",
                    directive_node = d.original_directive)
                return


def check_unsupported_directives(d: OpenMPDirective):
    '''Check for unsupported directives.'''
    if "end" in d.clauses: return
    if "task" in d.clauses:
        StompLogger.add_message(
            StompMessageCode.UnsupportedTaskDirective,
            description = "'task' directives are not currently "
                "supported by stomp.",
            directive_node = d.original_directive)
    elif "workshare" in d.clauses:
        StompLogger.add_message(
            StompMessageCode.UnsupportedTaskDirective,
            description = "'workshare' directives are not currently "
                "supported by stomp.",
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
    # Collect variables for each kind of data sharing attribute
    private = set(d.clauses.get("private", []))
    firstprivate = set(d.clauses.get("firstprivate", []))
    lastprivate = set(d.clauses.get("lastprivate", []))
    reduction_vars = set()
    if "reduction" in d.clauses:
        reduction_vars.update([red[1] for red in d.clauses["reduction"]])
    shared = set(d.clauses.get("shared", []))

    # Check that variables are not listed ambiguously
    attrib = {
        "private": private,
        "firstprivate": firstprivate,
        "lastprivate": lastprivate,
        "reduction": reduction_vars,
        "shared": shared
    }
    for (attrib_a, vars_a) in attrib.items():
        for (attrib_b, vars_b) in attrib.items():
            common = vars_a & vars_b
            if attrib_a != attrib_b and common:
                StompLogger.add_message(
                    StompMessageCode.DataSharingConflict,
                        description = f"Variables in set {common} are "
                        f"declared as both '{attrib_a}' and '{attrib_b}'.",
                        directive_node = d.original_directive)

    # Check that must-be-private variables are not shared
    must_be_private = d.get_always_private()
    common = must_be_private & shared
    if must_be_private & shared:
        StompLogger.add_message(
            StompMessageCode.DataSharingConflict,
            description = f"Variables in set {common} "
                f"must be private but are declared as 'shared'.",
            directive_node = d.original_directive)


# Reduction clause checks
# =======================


def check_reduction_clauses(d: OpenMPDirective):
    '''Check that reduction clauses describe valid reductions.'''
    if "end" in d.clauses: return

    if "reduction" in d.clauses:
        # Create mapping from string to reduction operator
        str_to_red_op = {}
        for (op, s) in MAP_REDUCTION_OP_TO_STR.items():
           str_to_red_op[s] = op

        # Get accesses in directive body
        accesses = d.body_reference_accesses()

        # Check reduction clauses
        for (op, x) in d.clauses["reduction"]:
          if op in str_to_red_op:
              x_sig = Signature(x)
              if x_sig not in accesses:
                  StompLogger.add_message(
                      StompMessageCode.BadReductionClause,
                      description =
                          f"Found a reduction clause involving a variable "
                          f"'{x}' that is not referenced in the body of "
                          f"the directive.",
                      directive_node = d.original_directive)
              else:
                  seq = accesses[x_sig]

                  # Array reductions not yet supported
                  if any([is_array_access(info) for info in seq]):
                      StompLogger.add_message(
                          StompMessageCode.UnsupportedArrayReduction,
                          description =
                              f"Variable '{x}' is an array. Array reductions "
                              f"are not yet supported by the checker.",
                          directive_node = d.original_directive)
                      continue

                  # Check for valid reduction forms in loops
                  if not d.is_loop(): continue
                  red_infer = ReductionInferenceTool([str_to_red_op[op]])
                  red_clause = red_infer.attempt_reduction(x_sig, seq)
                  if not red_clause:
                      StompLogger.add_message(
                          StompMessageCode.BadReductionClause,
                          description =
                              f"Not all references to variable '{x}' "
                              f"are valid reduction forms involving the "
                              f"operator '{op}'.",
                          directive_node = d.original_directive)
          else:
              StompLogger.add_message(
                  StompMessageCode.BadReductionClause,
                  description =
                      f"Unrecognised reduction operator '{op}'.",
                  directive_node = d.original_directive)


# Data race checks
# ================


def check_data_races(psyir: Node, 
                     solver_options: Optional[SMTSolverOptions] = None):
    '''Check all OpenMP teams/parallel regions for data races,
    where at least two accesses (one of which is a write)
    access the same indices of the same array in different threads,
    or access the same scalar in different threads.'''

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
            opts = RegionConflictAnalysisOptions()
            if solver_options:
                opts.sweep_seed = solver_options.sweep_seed
                opts.num_sweep_threads = solver_options.sweep_threads
                opts.smt_timeout_ms = solver_options.solver_timeout_ms
                opts.use_bv = solver_options.use_bit_vec
                opts.int_width = solver_options.bit_vec_width
                opts.prohibit_overflow = opts.use_bv
            analysis = RegionConflictAnalysis(opts)
            conflicts = analysis.get_region_conflicts(d)
            for c in conflicts:
                if c.msg is None:
                    continue
                if c.is_scalar:
                    code = StompMessageCode.ScalarDataRace
                else:
                    code = StompMessageCode.ArrayDataRace
                StompLogger.add_message(
                    code,
                    description = "Data race in "
                        "parallel region. " + c.msg + ".",
                    directive_node = d.original_directive,
                    node = c.node,
                    routine_name = routine.name)


# SIMD loop checks
# ================


def check_simd_loops(psyir: Node,
                     solver_options: Optional[SMTSolverOptions] = None):
    '''Check that 'simd' directives have non-conflicting loop iterations.
    The 'safelen' clause is not yet supported.'''
    for routine in psyir.walk(Routine):
        for d in routine.walk(OpenMPDirective):
            if "end" in d.clauses: continue
            if "simd" in d.clauses and "do" not in d.clauses:
                collapse = 1
                if "collapse" in d.clauses:
                    collapse = d.clauses["collapse"]
                outer_loop = d.get_singleton_body()
                all_loops = outer_loop.walk(Loop)
                loop_vars = [loop.variable.name for loop in all_loops]
                par_loops = all_loops[0:collapse]

                # Compute private variables
                private_vars = set(loop_vars)
                clauses = ["private", "firstprivate", "lastprivate"]
                for c in clauses:
                    if c in d.clauses:
                        private_vars.update(d.clauses[c])
                for (op, x) in d.clauses.get("reduction", []):
                    private_vars.add(x)

                # Analyse loop
                opts = LoopConflictAnalysisOptions()
                opts.check_scalars = True
                if solver_options:
                    opts.sweep_seed = solver_options.sweep_seed
                    opts.num_sweep_threads = solver_options.sweep_threads
                    opts.smt_timeout_ms = solver_options.solver_timeout_ms
                    opts.use_bv = solver_options.use_bit_vec
                    opts.int_width = solver_options.bit_vec_width
                    opts.prohibit_overflow = opts.use_bv
                analysis = LoopConflictAnalysis(opts)
                for loop in par_loops:
                    conflicts = analysis.get_loop_conflicts(loop,
                                   private=private_vars)
                    for c in conflicts:
                        if c.msg is None:
                            continue
                        if c.is_scalar:
                            code = StompMessageCode.ScalarDataRace
                        else:
                            code = StompMessageCode.ArrayDataRace
                        StompLogger.add_message(
                            code,
                            description = "Data race in "
                                "SIMD loop. " + c.msg + ".",
                            node = c.node,
                            directive_node = d.original_directive,
                            routine_name = routine.name)


# Subroutine/function call checks
# ===============================


def check_calls(d: OpenMPDirective, assume_pure: set[str] = set()):
    '''Report calls to unresolved or impure functions/routines in
    parallel regions'''

    # The following calls are ignored by the checking routines
    ignore_calls = {
        "omp_get_team_num",
        "omp_get_thread_num",
        "omp_get_num_teams",
        "omp_get_num_threads",
        "sleep",
    }

    # Scan calls in parallel regions
    is_parallel_region = "teams" in d.clauses or (
        "parallel" in d.clauses and not is_within_directive(d, ["teams"]))
    if is_parallel_region:
        region_body = d.get_body()
        if region_body:
            for stmt in region_body:
                for call in stmt.walk(Call):
                    name = call.routine.name

                    # Skip intrinsic calls
                    if isinstance(call, IntrinsicCall): continue

                    # Skip data constructors
                    if isinstance(call.routine.symbol, DataTypeSymbol):
                        continue

                    # Skip ignored calls
                    if name in ignore_calls: continue

                    # Try to resolve call
                    resolved = True
                    try:
                        call.get_callee()
                    except Exception as err:
                        reason = str(err)
                        resolved = False

                    if not resolved:
                        StompLogger.add_message(
                            StompMessageCode.UnresolvedCall,
                            description = f"Call to unresolved "
                                f"symbol '{name}' in parallel "
                                f"region. The reason for the resolution "
                                f"failure is: '{reason}'. "
                                f"Additional source files can be loaded "
                                f"using stomp's -F option.",
                            directive_node = d.original_directive,
                            node = call)
                        break

                    # Ignore assumed-pure calls
                    if name in assume_pure: continue

                    # Ignore routines marked as "threadsafe"
                    if is_threadsafe(call.routine.symbol): continue

                    # Catch all remaining impure calls
                    if not call.is_pure:
                        StompLogger.add_message(
                            StompMessageCode.ImpureParallelCall,
                            description = f"Call to impure "
                                f"function/subroutine '{name}' in parallel "
                                f"region. Use the command-line option "
                                f"'--pure {name}' to assume that this call is "
                                f"pure or '-e ImpureParallelCall' to assume "
                                f"that all calls are pure.",
                            directive_node = d.original_directive,
                            node = call)


# Wildcard import checks
# ======================


def check_wildcard_imports(psyir: Node):
    '''Report wilcard imports in subroutines containing parallel regions.'''
    for routine in psyir.walk(Routine):
        omp_dirs = routine.walk(OpenMPDirective)
        has_par_region = any([d for d in omp_dirs
                                  if "parallel" in d.clauses
                                  or "teams" in d.clauses])
        if not has_par_region: continue
        if isinstance(routine.parent, FileContainer): continue
        wildcard_imports = set(
            routine.symbol_table.wildcard_imports(scope_limit=routine))
        if wildcard_imports:
            module = wildcard_imports.pop()
            StompLogger.add_message(
                StompMessageCode.WildcardImportInSubroutine,
                description =
                    f"Found wildcard import 'use {module.name}' "
                    f"inside a subroutine, which is not well supported "
                    f"by the tool. You can swap it for a module-level "
                    f"import, or for a named import of the form "
                    f"'use {module.name}, only: ...', or you can disable "
                    f"this warning, but the latter may lead to symbol "
                    f"resolution issues.",
                routine_name = routine.name)


# Uninitialised read checks
# =========================


def check_uninitialised_read(d: OpenMPDirective):
    '''Check for reads of uninitialised private variables.'''
    accesses = d.body_reference_accesses()
    if accesses:
        (private, _) = d.get_private_shared(ignore_firstprivate=True,
                                            ignore_reduction=True,
                                            ignore_always_private=True)
        for p in private:
            sig = Signature(p)
            if sig not in accesses: continue
            for info in accesses[sig]:
                if info.access_type == AccessType.WRITE: break
                if (info.access_type == AccessType.READ or
                        info.access_type == AccessType.READWRITE):
                    StompLogger.add_message(
                        StompMessageCode.ReadUninitialisedPrivate,
                        description = f"Parallel region reads "
                            f"uninitialised private variable '{p}'.",
                        node = info.node,
                        directive_node = d.original_directive)
                    break


# PSyIR CodeBlock checks
# ======================


def check_codeblocks(d: OpenMPDirective):
    '''Report calls to PSyIR CodeBlocks in parallel regions.'''
    if "end" in d.clauses: return
    is_parallel_region = "teams" in d.clauses or (
        "parallel" in d.clauses and not is_within_directive(d, ["teams"]))
    if is_parallel_region:
        region_body = d.get_body()
        if region_body:
            for stmt in region_body:
                for block in stmt.walk(CodeBlock):
                    StompLogger.add_message(
                        StompMessageCode.PSyIRLimitation,
                        description = "Parallel region contains "
                            "a PSyIR CodeBlock, which captures a block of "
                            "code that is not fully understood by PSyclone. "
                            "This message can be ignored with the "
                            "'-e PSyIRLimitation' option but that "
                            "may lead to false positives.",
                        directive_node = d.original_directive,
                        node = block)


# Stomp directive checks
# ======================


def check_stomp_directive(d: OpenMPDirective):
    '''Check that the "expr" in a "!$stomp assume(expr)" directive or
    a "!$stomp unique(expr)" has a fully supported translation to Z3.'''
    if "end" in d.clauses: return
    if "assume" in d.clauses:
        trans = FortranToZ3(handle_array_intrins=True,
                            allow_unsupported=False)
        try:
            trans.translate_logical_expr(d.clauses["assume"])
        except TranslationNotSupported as err:
            text = node_text(err.expr, max_len=40)
            StompLogger.add_message(
                StompMessageCode.BadAssumeDirective,
                description = f"The 'assume' clause contains a "
                    f"subexpression for which there is no supported "
                    f"translation to a Z3 boolean: {text}.",
                directive_node = d.original_directive)
    if "unique" in d.clauses:
        trans = FortranToZ3(handle_array_intrins=True,
                            allow_unsupported=False)
        try:
            trans.translate_integer_expr(d.clauses["unique"])
        except TranslationNotSupported as err:
            text = node_text(err.expr, max_len=40)
            StompLogger.add_message(
                StompMessageCode.BadUniqueDirective,
                description = f"The 'unique' clause contains a "
                    f"subexpression for which there is no supported "
                    f"translation to a Z3 integer: {text}.",
                directive_node = d.original_directive)
