import sys
from typing import List
from psyclone.errors import InternalError
from psyclone.configuration import Config
from psyclone.psyir.frontend.fortran import FortranReader
from stomp.message import StompLogger, StompMessageCode
from stomp.module_spec_directives import parse_module_spec_directives
from stomp.main import main


# Shorthand for message codes
Msg = StompMessageCode


def stomp_test(code: str,
               expected_msgs: List[StompMessageCode],
               infer: bool = False):
    '''Function to check that the given code yeilds the given messages.'''
    # Avoid loading the PSyclone config file
    Config.get(do_not_load_file=True)

    # Clear messages
    StompLogger.clear()

    # Load Fortran code
    fortran_reader = FortranReader(
        resolve_modules=True,
        ignore_comments=False,
        ignore_directives=False,
        conditional_openmp_statements=True,
        free_form=True
    )
    try:
        psyir = fortran_reader.psyir_from_source(code)
    except (InternalError, ValueError, IOError) as err:
        print(f"Failed to create PSyIR from source "
              f"due to: {str(err)}", file=sys.stderr)
        assert False
    parse_module_spec_directives(code, psyir)

    # Invoke the tool
    main(psyir, infer=infer)

    # Check messages
    msgs = [msg.code for msg in StompLogger.get_messages()]
    assert msgs == expected_msgs
