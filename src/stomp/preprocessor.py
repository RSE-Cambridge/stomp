# SPDX-License-Identifier: BSD-3-Clause

'''This module provides functions that enable a preprocessor to applied
to source code as it is loaded by PSyclone'''

import os
import shlex
import subprocess
import types
import logging
import hashlib
from psyclone.parse.file_info import FileInfo
from psyclone.parse.module_manager import ModuleManager


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


# Subclass of FileInfo allowing preprocessor to be applied to loaded code
class FileInfoPreProc(FileInfo):
    def set_preprocessor(self, command: str):
        self._preprocessor = command

    def get_source_code(self) -> str:
        apply_preprocessor = hasattr(self, "_preprocessor")
        if not apply_preprocessor:
            super().get_source_code()
        else:
            if self._source_code:
                return self._source_code

            logger = logging.getLogger(__name__)
            logger.info(f"Source file '{self._filename}': loading source "
                        f"code with preprocessor {self._preprocessor}.")

            self._source_code = preprocess(self._preprocessor, self._filename)

            logger.info(f"Source file '{self._filename}': loaded OK")

            if self._cache_active:
                # Update the hash sum
                self._source_code_hash_sum = hashlib.md5(
                    self._source_code.encode()).hexdigest()

            return self._source_code


# Monkey patch ModuleManager to use FileInfoPreProc instead of FileInfo
def enable_preprocessor(mod_manager: ModuleManager, command: str):
    # Replacement method for ModuleManager's _add_all_files_from_dir().
    # This definition is a copy of the original method with minor changes.
    # This method should be kept up to date with the original.
    def add_files_new(self, directory: str):
        new_files = []
        with os.scandir(directory) as all_entries:
            for entry in all_entries:
                _, ext = os.path.splitext(entry.name)
                if (not entry.is_file() or
                        ext not in [".F90", ".f90", ".X90", ".x90"]):
                    continue
                full_path = os.path.join(directory, entry.name)
                if full_path in self._visited_files:
                    continue
                # Check if the full path contains an ignore pattern:
                if any(i in full_path for i in self._ignore_files):
                    continue
                self._visited_files[full_path] = \
                    FileInfoPreProc(
                            full_path,
                            cache_active=self._cache_active,
                            cache_path=self._cache_path,
                            resolve_imports=self._resolve_indirect_imports
                        )
                self._visited_files[full_path].set_preprocessor(command)
                new_files.append(self._visited_files[full_path])
        return new_files

    # Replace the method
    mod_manager._add_all_files_from_dir = types.MethodType(
        add_files_new, mod_manager)
