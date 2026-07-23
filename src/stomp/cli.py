#!/usr/bin/python3

import sys
import argparse
from psyclone.configuration import Config
from psyclone.parse import ModuleManager
from psyclone.errors import InternalError
from psyclone.psyir.frontend.fortran import FortranReader
from stomp.preprocessor import enable_preprocessor, preprocess
from stomp.message import StompLogger, StompMessageCode
from stomp.colours import green, red, amber, blue
from stomp.main import main
from stomp.module_spec_directives import parse_module_spec_directives
from stomp.solver_options import SMTSolverOptions
from stomp.module_loader import load_modules, ModuleLoaderReport

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
        "-F",
        help="add given Fortran file for imported modules",
        metavar="FILE",
        action="append",
        default=[])
    arg_parser.add_argument(
        "--no-progress",
        help="disable progress reports",
        action="store_true")
    arg_parser.add_argument(
        "--cpp",
        help="enable preprocessor (auto-enabled for .F* files)",
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
    arg_parser.add_argument(
        "--ignore",
        help="ignore (don't try to load) given module",
        metavar="MOD",
        action="append",
        default=[])
    arg_parser.add_argument(
        "-e",
        help="don't report (exclude) issues with the given code",
        metavar="CODE",
        action="append",
        default=[])
    arg_parser.add_argument(
        "--pure",
        help="assume that the given function/subroutine is pure",
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

    # Add modules to ignore
    for mod_ignore in args.ignore:
        mod_manager.add_ignore_module(mod_ignore)

    # Load modules from all input files
    files = args.F + [args.input_file]
    loader_report = load_modules(mod_manager, files, args.no_progress)

    # Report result loading
    if loader_report.modules_loaded:
        print(green("Modules loaded") + ":",
              ", ".join(loader_report.modules_loaded))
    if loader_report.modules_not_loaded:
        print(amber("Modules not loaded") + ":",
              ", ".join(loader_report.modules_not_loaded))
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
        resolve_modules=loader_report.modules_loaded,
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

    # Parse directives in the specification part of Fortran modules
    parse_module_spec_directives(source_code, psyir, mod_manager)

    # SMT solver options
    solver_opts = SMTSolverOptions(args.sweep_seed,
                                   args.sweep_threads,
                                   args.smt_timeout,
                                   args.smt_use_bit_vec,
                                   args.smt_bit_vec_width)

    # Invoke the tool
    num_omp_dir = main(psyir,
                       infer=args.infer,
                       assume_pure=args.pure,
                       solver_options=solver_opts)

    note = ""
    if num_omp_dir is not None:
        msgs = StompLogger.get_messages()
    else:
        num_omp_dir = 0
        note = " (non-excludable)"
        msgs = StompLogger.get_all_messages()

    # Emit messages
    issue_count = 0
    for msg in msgs:
        print(msg.render())
        issue_count += 1

    # Emit number of directives analysed
    print(f"All done. Analysed {num_omp_dir} directives and "
          f"found {issue_count} issues{note}.")

if __name__ == "__main__":
    entry()
