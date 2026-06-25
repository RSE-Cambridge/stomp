#!/usr/bin/python3

import sys
import argparse
from psyclone.configuration import Config
from psyclone.parse import ModuleManager
from psyclone.errors import InternalError
from psyclone.psyir.frontend.fortran import FortranReader
from stomp.preprocessor import enable_preprocessor, preprocess
from stomp.message import StompLogger
from stomp.main import main
from stomp.threadprivate import mark_threadprivate

def entry():
    # Arguments
    # =========

    arg_parser = argparse.ArgumentParser("stomp.py")
    arg_parser.add_argument("input_file")
    arg_parser.add_argument(
        "--infer",
        help="infer parallel loops",
        action="store_true")
    arg_parser.add_argument(
        "-M",
        help="add search path for imported modules",
        metavar="PATH",
        action="append",
        default=[])
    arg_parser.add_argument(
        "-R",
        help="add recursive search path for imported modules",
        metavar="PATH",
        action="append",
        default=[])
    arg_parser.add_argument(
        "-F",
        help="add given Fortran file for imported modules",
        metavar="PATH",
        action="append",
        default=[])
    arg_parser.add_argument(
        "--cpp",
        help="enable preprocessor",
        action="store_true")
    arg_parser.add_argument(
        "--nocpp",
        help="disable preprocessor",
        action="store_true")
    arg_parser.add_argument(
        "--cpp-cmd",
        help="specify preprocessor command (the default is "
             "'cpp -traditional -P' but other possibilities include "
             "'gfortran -E -P' or 'ifx -E -P')",
        metavar="CMD",
        action="store",
        default='cpp -traditional -P')
    arg_parser.add_argument(
        "-I",
        help="add preprocessor include path",
        metavar="PATH",
        action="append",
        default=[])
    arg_parser.add_argument(
        "-D",
        help="define preprocessor macro",
        metavar="MACRO",
        action="append",
        default=[])
    args = arg_parser.parse_args()

    # Frontend
    # ========

    # Avoid loading the PSyclone config file
    Config.get(do_not_load_file=True)

    # Enable caching
    mod_manager = ModuleManager.get()
    mod_manager.cache_active = True

    # Enable preprocessor?
    preprocess_exts = (".F", ".F90", ".F95", ".F03",
                       ".F08", ".fpp", ".FPP", ".FOR", ".FTN")
    apply_preprocessor = False
    if args.cpp or args.input_file.endswith(preprocess_exts):
        apply_preprocessor = True
    if args.nocpp:
        apply_preprocessor = False
    preprocessor_command = args.cpp_cmd
    for inc_path in args.I:
        preprocessor_command += f" -I'{inc_path}'"
    for macro in args.D:
        preprocessor_command += f" -D'{macro}'"
    if apply_preprocessor:
        enable_preprocessor(preprocessor_command)

    # Add working dir as a (non-recursive) search path
    mod_manager.add_search_path("./", False)

    # Add -M arguments to search path
    for mod_path in args.M:
        mod_manager.add_search_path(mod_path, False)

    # Add -R arguments to search path
    for mod_path in args.R:
        mod_manager.add_search_path(mod_path, True)

    # Load any files specified by -F arguments
    if args.F:
        mod_manager.add_files(args.F)
        mod_manager.load_all_module_infos()

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
        if apply_preprocessor:
            source_code = preprocess(preprocessor_command, args.input_file)
            psyir = fortran_reader.psyir_from_source(source_code)
        else:
            with open(args.input_file, "r",
                      encoding="utf-8", errors="ignore") as file_in:
                source_code = file_in.read()
            psyir = fortran_reader.psyir_from_source(source_code)
    except (InternalError, ValueError, IOError, FileNotFoundError) as err:
        print(f"Failed to create PSyIR from file '{args.input_file}'"
              f"due to: {str(err)}", file=sys.stderr)
        sys.exit(1)
    psyir.name = args.input_file

    # Give a warning if the PSyIR container is empty
    if not psyir.children:
        print(f"Warning: PSyIR from file '{args.input_file}' is empty.",
              file=sys.stderr)
        sys.exit(1)

    # Identify and mark threadprivate variables (the info needed for this pass
    # is not available in the PSyIR, so we use the raw source code)
    mark_threadprivate(source_code, psyir, mod_manager)

    # Invoke the tool
    num_omp_dir = main(psyir, infer=args.infer)

    # Emit messages
    issue_count = 0
    for msg in StompLogger.get_messages():
        print(msg.render())
        issue_count += 1

    # Emit number of directives analysed
    print(f"All done. Analysed {num_omp_dir} directives and "
          f"found {issue_count} issues.")

if __name__ == "__main__":
    entry()
