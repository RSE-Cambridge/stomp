#!/usr/bin/python3

import sys
from psyclone.parse import ModuleManager
from psyclone.errors import InternalError
from psyclone.psyir.nodes import Directive, UnknownDirective
from psyclone.psyir.frontend.fortran import FortranReader
from openmp_directives import OpenMPDirective, \
                              identify_openmp_directives, \
                              merge_multiline_directives
from stomp_message import StompLogger
import static_checks as checks

# Arguments
# =========

if len(sys.argv) != 2:
    print("Usage: stomp.py <filename>")
    sys.exit(1)
input_file = sys.argv[1]

# Frontend
# ========

# Enable caching
mod_manager = ModuleManager.get()
mod_manager.cache_active = True

# Determine file type
free_form_exts = (".f90", ".f95", ".f03", ".f08",
                  ".F90", ".F95", ".F03", ".F08",
                  ".x90", ".xu90")
fixed_form_exts = (".f", ".for", ".fpp", ".ftn",
                   ".F", ".FOR", ".FPP", ".FTN")
if input_file.endswith(free_form_exts):
    free_form = True
elif input_file.endswith(fixed_form_exts):
    free_form = False
else:
    print(f"Uncrecognised file extension in '{input_file}'")
    sys.exit(1)

# Load Fortran code
fortran_reader = FortranReader(
                     resolve_modules=True,
                     ignore_comments=False,
                     ignore_directives=False,
                     conditional_openmp_statements=True,
                     free_form=free_form
                 )
try:
    psyir = fortran_reader.psyir_from_file(input_file)
except (InternalError, ValueError, IOError) as err:
    print(f"Failed to create PSyIR from file '{input_file}'"
          f"due to: {str(err)}", file=sys.stderr)
    sys.exit(1)

# Merge multiline directives into a single line
merge_multiline_directives(psyir)

# Identify OpenMP directives
identify_openmp_directives(psyir)

# Basic checks
for d in psyir.walk(OpenMPDirective):
    checks.check_loose_end(d)
    checks.check_loop_directive_is_followed_by_loop(d)
    checks.check_singleton_directive_num_stmts(d)
    checks.check_singleton_directive_not_empty(d)
    checks.check_standalone_directive_not_end(d)
    checks.check_directive_is_recognised(d)
    checks.check_collapse_clause(d)
    checks.check_data_sharing_clauses(d)

if len(StompLogger.get_messages()) > 0:
    # Report messages
    for msg in StompLogger.get_messages():
        print(msg.render())
    sys.exit(0)

# Scalar conflict checks
checks.check_parallel_scalar_accesses(psyir)

# Loop array conflict checks
checks.check_loop_array_accesses(psyir)

# Report messages
for msg in StompLogger.get_messages():
    print(msg.render())
