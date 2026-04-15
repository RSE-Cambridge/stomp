#!/usr/bin/python3

import sys
import argparse
from psyclone.parse import ModuleManager
from psyclone.errors import InternalError
from psyclone.psyir.frontend.fortran import FortranReader
from stomp.message import StompLogger
from stomp.main import main

# Arguments
# =========

arg_parser = argparse.ArgumentParser("stomp.py")
arg_parser.add_argument("input_file")
arg_parser.add_argument(
    "--infer",
    help="Infer parallel loops",
    action="store_true")

args = arg_parser.parse_args()

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
if args.input_file.endswith(free_form_exts):
    free_form = True
elif args.input_file.endswith(fixed_form_exts):
    free_form = False
else:
    print(f"Uncrecognised file extension in '{args.input_file}'")
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
    psyir = fortran_reader.psyir_from_file(args.input_file)
except (InternalError, ValueError, IOError) as err:
    print(f"Failed to create PSyIR from file '{args.input_file}'"
          f"due to: {str(err)}", file=sys.stderr)
    sys.exit(1)

# Invoke the tool
main(psyir, infer=args.infer)

# Emit messages
for msg in StompLogger.get_messages():
    print(msg.render(), end="")
