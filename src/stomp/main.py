from typing import Optional, List
from stomp.openmp_directives import \
    OpenMPDirective, \
    identify_openmp_directives, \
    merge_multiline_directives
from stomp.message import StompLogger, StompMessageCode
import stomp.static_checks as checks
import stomp.inference as inference
from stomp.solver_options import SMTSolverOptions


def main(psyir,
         infer: bool = False,
         assume_pure: List[str] = [],
         solver_options: Optional[SMTSolverOptions] = None) -> Optional[int]:
    '''Returns the number of directives analysed, or None if there
    was non-recoverable error.'''

    # Number of messages currently in the logger
    num_msgs = len(StompLogger.get_messages())

    # Merge multiline directives into a single line
    merge_multiline_directives(psyir)

    # Identify OpenMP directives
    identify_openmp_directives(psyir)

    # Mandatory directive checks
    for d in psyir.walk(OpenMPDirective):
        checks.check_loose_end(d)
        checks.check_loop_directive_is_followed_by_loop(d)
        checks.check_singleton_directive_num_stmts(d)
        checks.check_singleton_directive_not_empty(d)
        checks.check_standalone_directive_not_end(d)
        checks.check_directive_is_recognised(d)
        checks.check_sections_directive(d)
        checks.check_stomp_directive(d)

    # Exit early if a mandatory check fails
    if len(StompLogger.get_messages()) > num_msgs: return None

    # Check for poorly supported subroutine-local wildcard imports
    checks.check_wildcard_imports(psyir)
    if len(StompLogger.get_messages()) > num_msgs: return None

    # Count number of directives present
    num_dir = len(psyir.walk(OpenMPDirective))

    # Basic checks
    for d in psyir.walk(OpenMPDirective):
        checks.check_unsupported_directives(d)
        checks.check_misplaced_directive(d)
        checks.check_nowait(d)
        checks.check_collapse_clause(d)
        checks.check_data_sharing_clauses(d)
        checks.check_ordered_directives(d)
        checks.check_reduction_clauses(d)
        checks.check_calls(d, assume_pure=set(assume_pure))

    # Exit early for unresolved/impure calls as they lead to too many
    # false positives
    if StompLogger.has_message(StompMessageCode.UnresolvedCall):
        return num_dir
    if StompLogger.has_message(StompMessageCode.ImpureParallelCall):
        return num_dir

    # Uninitialised read checks
    for d in psyir.walk(OpenMPDirective):
        checks.check_uninitialised_read(d)

    # Data race checks
    checks.check_data_races(psyir, solver_options)

    # Lone SIMD loop data race checks
    checks.check_simd_loops(psyir, solver_options)

    # Parallel loop inference
    if infer:
        inference.infer_parallel_loops(psyir, solver_options)

    return num_dir
