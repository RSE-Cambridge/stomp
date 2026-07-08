from typing import Optional
from stomp.openmp_directives import \
    OpenMPDirective, \
    identify_openmp_directives, \
    merge_multiline_directives
from stomp.message import StompLogger
import stomp.static_checks as checks
import stomp.inference as inference


def main(psyir, infer: bool = False) -> Optional[int]:
    # Merge multiline directives into a single line
    merge_multiline_directives(psyir)

    # Identify OpenMP directives
    identify_openmp_directives(psyir)

    for d in psyir.walk(OpenMPDirective):
        checks.check_loose_end(d)
        checks.check_loop_directive_is_followed_by_loop(d)
        checks.check_singleton_directive_num_stmts(d)
        checks.check_singleton_directive_not_empty(d)
        checks.check_standalone_directive_not_end(d)
        checks.check_directive_is_recognised(d)

    if len(StompLogger.get_messages()) > 0:
        return

    for d in psyir.walk(OpenMPDirective):
        checks.check_collapse_clause(d)
        checks.check_data_sharing_clauses(d)
        checks.check_ordered_directives(d)
        checks.check_nested_directives(d)
        checks.check_reduction_clauses(d)

    if len(StompLogger.get_messages()) > 0:
        return

    # Scalar conflict checks
    checks.check_parallel_scalar_accesses(psyir)

    # Parallel array conflict checks
    checks.check_parallel_array_accesses(psyir)

    # Check SIMD loops
    checks.check_simd_loops(psyir)

    # Parallel loop inference
    if infer:
        inference.infer_parallel_loops(psyir)

    # Count number of directives analaysed
    num_omp_dir = len(psyir.walk(OpenMPDirective))
    return num_omp_dir
