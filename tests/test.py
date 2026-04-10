#!/usr/bin/python3

import os
import sys
import pathlib
import argparse
import subprocess

tests_path = pathlib.Path("./")
src_path = pathlib.Path("../src")
exec_path = pathlib.Path(src_path, "stomp.py")

# Colours
class Colour:
    '''Colour codes for colourful text.'''
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ENDC = '\033[0m'

def green(text: str):
    return Colour.GREEN + text + Colour.ENDC

def red(text: str):
    return Colour.RED + text + Colour.ENDC

# Command line arguments
parser = argparse.ArgumentParser("test.py")
parser.add_argument(
    "--update",
    help="Update the expected output of the given test",
    metavar="<TEST>.F90",
    type=str)
parser.add_argument(
    "--update-all",
    help="Update the expected outputs of all tests",
    action="store_true")

args = parser.parse_args()

# Top-level control
if args.update is not None:
    # Recompute the output file for the given test
    file_path = pathlib.Path(tests_path, args.update)
    out_path = file_path.with_suffix('.out')
    print(str(file_path) + ": ", end='')
    # Run the test and update the file
    try:
        got = subprocess.check_output(
                  [exec_path, file_path]).decode("utf-8")
        out_path.write_text(got)
    except Exception:
        print(red("FAILED"))
        sys.exit(1)
    print(green("UPDATED"))
else:
    # Run all tests
    for f in sorted(os.listdir(tests_path)):
        if f.endswith(".F90"):
            print(f + ": ", end='')
            file_path = pathlib.Path(tests_path, f)
            out_path = file_path.with_suffix('.out')
            # Run the test
            try:
                got = subprocess.check_output(
                          [exec_path, file_path]).decode("utf-8")
            except Exception:
                print(red("FAILED"))
                sys.exit(1)
            if args.update_all:
                # Update the output file
                try:
                    out_path.write_text(got)
                except Exception:
                    print(red("FAILED"))
                    sys.exit(1)
                print(green("UPDATED"))
            else:
                # Determine the expected output
                try:
                    expected = out_path.read_text()
                except:
                    print(red("FAILED"))
                    print(f"Couldn't read '{out_path}'")
                    sys.exit(1)
                # Check the output against the expected output
                if got == expected:
                    print(green("PASSED"))
                else:
                    print(red("FAILED"))
                    print("Got:")
                    print(got)
                    sys.exit(1)
