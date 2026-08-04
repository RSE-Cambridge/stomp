#!/usr/bin/python3

# SPDX-License-Identifier: BSD-3-Clause

import sys
import argparse
from pathlib import Path
from psyclone.configuration import Config
from psyclone.parse import ModuleManager
from psyclone.errors import InternalError
from psyclone.psyir.frontend.fortran import FortranReader
from stomp.preprocessor import enable_preprocessor, preprocess
from stomp.message import StompLogger, StompMessageCode
from stomp.main import main
from stomp.module_spec_directives import parse_module_spec_directives
from stomp.solver_options import SMTSolverOptions
from stomp.module_loader import load_modules
from stomp.progress_reporter import ProgressReporter
from stomp.colours import Colour

def entry():
    # Arguments
    # =========

    arg_parser = argparse.ArgumentParser("stomp")
    arg_parser.add_argument("input_file")
    arg_parser.add_argument(
        "--infer",
        help="infer parallel loops",
        action="store_true")
    arg_parser.add_argument(
        "-l",
        help="load given Fortran file for import resolution",
        metavar="FILE",
        action="append",
        default=[])
    arg_parser.add_argument(
        "-L",
        help="load all Fortran files in given directory for "
             "import resolution",
        metavar="DIR",
        action="append",
        default=[])
    arg_parser.add_argument(
        "--no-colour",
        help="disable colour output",
        action="store_true")
    arg_parser.add_argument(
        "--no-progress",
        help="disable progress reporting",
        action="store_true")
    arg_parser.add_argument(
        "--cpp",
        help="enable preprocessor (auto-enabled for .F* files)",
        action="store_true")
    arg_parser.add_argument(
        "--no-cpp",
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
    arg_parser.add_argument(
        "-e",
        help="exclude (don't report) issues with the given code",
        metavar="CODE",
        action="append",
        default=[])
    arg_parser.add_argument(
        "--threadsafe",
        help="assume that the given function/subroutine is safe to call "
             "in parallel",
        metavar="NAME",
        action="append",
        default=[])
    arg_parser.add_argument(
        "--sweep-seed",
        type=int,
        help="specify the random seed for the SMT solver",
        metavar="N",
        action="store",
        default=1)
    arg_parser.add_argument(
        "--sweep-threads",
        type=int,
        help="specify number of threads to use when solving SMT formulae "
             "(default=4)",
        metavar="N",
        action="store",
        default=4)
    arg_parser.add_argument(
        "--smt-timeout",
        type=int,
        help="specify the SMT solver timeout in milliseconds "
             "(default=5000)",
        metavar="MS",
        action="store",
        default=5000)
    arg_parser.add_argument(
        "--smt-use-bit-vec",
        help="use bit vectors (rather than unbounded integers) in the SMT "
             "solver",
        action="store_true")
    arg_parser.add_argument(
        "--smt-bit-vec-width",
        type=int,
        help="SMT bit-vector width (default=32)",
        metavar="WIDTH",
        action="store",
        default=32)

    args = arg_parser.parse_args()

    # Frontend
    # ========

    # Avoid loading the PSyclone config file
    Config.get(do_not_load_file=True)

    # Create module manager
    mod_manager = ModuleManager.get()

    # Enable preprocessor for top-level source file?
    preprocess_exts = (".F", ".F90", ".F95", ".F03",
                       ".F08", ".fpp", ".FPP", ".FOR", ".FTN")
    apply_preprocessor = False
    if args.cpp or args.input_file.endswith(preprocess_exts):
        apply_preprocessor = True
    if args.no_cpp:
        apply_preprocessor = False
    preprocessor_command = args.cpp_cmd
    for inc_path in args.I:
        preprocessor_command += f" -I'{inc_path}'"
    for macro in args.D:
        preprocessor_command += f" -D'{macro}'"

    # Enable preprocessing when loading modules?
    if not args.no_cpp:
        enable_preprocessor(preprocessor_command, args.cpp)

    # Disable progress reporting?
    if args.no_progress: ProgressReporter.enabled = False

    # Disable colour printing?
    if args.no_colour: Colour.enabled = False

    # Inform logger about isssues to exclude
    for code_str in args.e:
        try:
            code = StompMessageCode[code_str]
        except KeyError:
            print(f"CLI error: unrecognised issue code '{code_str}'.")
            sys.exit(-1)
        StompLogger.add_ignore(code)

    # Disabling unnecessary check in module manager
    mod_manager._doesnt_need_preprocessing = lambda self: True

    # Check file extension
    free_form_exts = (".f90", ".f95", ".f03", ".f08",
                      ".F90", ".F95", ".F03", ".F08")
    if not args.input_file.endswith(free_form_exts):
        print(f"Uncrecognised file extension in '{args.input_file}'")
        sys.exit(1)

    # Determine all files to load
    files_to_load = []
    files_to_load.extend(args.l)
    for pathname in args.L:
        path = Path(pathname)
        for ext in free_form_exts:
           files_to_load.extend(
               sorted([str(f) for f in path.glob("*" + ext)]))

    # Load modules
    loader_report = load_modules(
        mod_manager, args.input_file, files_to_load)

    # Report result loading
    if loader_report.modules_loaded:
        print(Colour.green("Modules loaded") + ":",
              ", ".join(sorted(loader_report.modules_loaded)))
    if loader_report.modules_not_loaded:
        print(Colour.amber("Modules not loaded") + ":",
              ", ".join(sorted(loader_report.modules_not_loaded)))
    if loader_report.modules_loaded or loader_report.modules_not_loaded:
        print()

    # Report loading errors as user messages
    for (filename, err) in loader_report.file_errors.items():
        StompLogger.add_message(
            StompMessageCode.FileLoadFailure,
            description = f"Failed to load '{filename}': " + err)
    for (mod_name, err) in loader_report.module_errors.items():
        StompLogger.add_message(
            StompMessageCode.ModuleLoadFailure,
            description = f"Failed to load module '{mod_name}': " + err)

    # Load Fortran code
    fortran_reader = FortranReader(
        resolve_modules=loader_report.modules_loaded,
        ignore_comments=False,
        ignore_directives=False,
        conditional_openmp_statements=True,
        free_form=True
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

    # Parse directives in the specification part of Fortran modules
    parse_module_spec_directives(source_code, psyir, mod_manager)

    # SMT solver options
    solver_opts = SMTSolverOptions(args.sweep_seed,
                                   args.sweep_threads,
                                   args.smt_timeout,
                                   args.smt_use_bit_vec,
                                   args.smt_bit_vec_width)

    # Invoke the tool
    result = main(psyir,
                  infer=args.infer,
                  assume_pure=args.threadsafe,
                  solver_options=solver_opts)

    # Generate output
    note = ""
    if result.failed_mandatory is not None:
        msgs = StompLogger.get_messages()
    else:
        note = " (non-excludable)"
        msgs = StompLogger.get_all_messages()

    # Emit messages
    issue_count = 0
    for msg in msgs:
        print(msg.render())
        issue_count += 1

    # Emit summary
    print(Colour.underline("Summary"))
    print(f"Directives found: {result.num_directives}")
    print(f"Issues found: {issue_count}{note}")
    if StompLogger.smt_timeouts > 0:
        smt_header = Colour.amber("SMT queries/timeouts")
    else:
        smt_header = "SMT queries/timeouts"
    print(f"{smt_header}: "
          f"{StompLogger.smt_queries}/"
          f"{StompLogger.smt_timeouts}")
    if result.ran_all_checks:
        if issue_count == 0:
            print(Colour.green("All checks passed!"))
        else:
            print("All checks completed: yes")
    else:
        print("All checks completed: no")


if __name__ == "__main__":
    entry()
