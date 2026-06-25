# SPDX-License-Identifier: BSD-3-Clause

'''This module provides functions that enable a preprocessor to applied
to source code as it is loaded by PSyclone'''

import shlex
import subprocess
import logging
import hashlib
from psyclone.parse.file_info import FileInfo


# Function to load and preprocess the given file
def preprocess(preprocessor_command: str, filename: str):
    try:
        command = preprocessor_command + " " + filename
        result = subprocess.run(shlex.split(command),
                                capture_output=True,
                                text=True,
                                encoding='utf-8',
                                errors='ignore')
    except Exception:
        raise ValueError(
            f"Error running preprocessor {preprocessor_command} "
            f"on input file {filename}.")

    if result.returncode != 0:
        raise ValueError(
            f"Error running preprocessor {preprocessor_command} "
            f"on input file {filename}: {result.stderr}.")

    return result.stdout


# Monkey patch FileInfo with support for preprocessing
def enable_preprocessor(command: str):
    # Replace FileInfo.get_source_code() with the following method
    def get_source_code(self) -> str:
        if self._source_code:
            return self._source_code

        logger = logging.getLogger(__name__)
        logger.info(f"Source file '{self._filename}': loading source "
                    f"code with preprocessor {command}.")

        self._source_code = preprocess(command, self._filename)

        logger.info(f"Source file '{self._filename}': loaded OK")

        if self._cache_active:
            # Update the hash sum
            self._source_code_hash_sum = hashlib.md5(
                self._source_code.encode()).hexdigest()

        return self._source_code

    # Install new method
    FileInfo.get_source_code = get_source_code
