# SPDX-License-Identifier: BSD-3-Clause

'''This file provides functionality to identify and mark all threadprivate
module variables. Local theadprivate variables with the save attribute are not
yet supported. Unfortunately, the required information for this pass is not
currently provided by PSyIR, so we use imperfect regex matching on the raw
source code. In future, we could search the parse tree rather than the raw
source for a more robust solution.'''

import re
from typing import List, Tuple
from psyclone.parse.module_manager import ModuleManager
from psyclone.psyir.nodes import Node, Container


def mark_threadprivate(top_source_code: str,
                       top_psyir: Node,
                       mod_manager: ModuleManager):
    '''Iterate over each module, determine the threadprivate variables
    declared in that module, and mark these variables as threadprivate in
    in the module's symbol table.'''
    mod_manager.load_all_module_infos()
    mod_infos = mod_manager.all_module_infos
    source_code_list = [top_source_code] + \
                       [m.get_source_code() for m in mod_infos]
    psyir_list = [top_psyir] + [m.get_psyir() for m in mod_infos]
    for (source_code, psyir) in zip(source_code_list, psyir_list):
        for (mod_name, spec) in get_module_specs(source_code):
            threadprivate = get_threadprivate(spec)
            for c in psyir.walk(Container):
                if c.name == mod_name:
                    for v in threadprivate:
                        try:
                            sym = c.symbol_table.lookup(v)
                            # Mark symbol as threadprivate inside the
                            # "visibility" field of the symbol. This update
                            # will be visible in all symbol tables /
                            # references.
                            if hasattr(sym, "visibility"):
                                sym.visibility.is_threadprivate = True
                        except Exception:
                            pass


def get_module_specs(source_code: str) -> List[Tuple[str, str]]:
    '''Use a regex to find the specification part of all modules in
    in the given source code.'''
    result = []
    begin_module = r"(^|\n)\s*module\s(.*?)\s(.*?)"
    end_module = r"\n\s*(end\s*module|contains)"
    pattern = begin_module + end_module
    for match in re.finditer(pattern, source_code.lower(), flags=re.DOTALL):
        mod_name = match.group(2)
        spec = match.group(3)
        result.append((mod_name, spec))
    return result


def get_threadprivate(source_code: str):
    '''Use a regex to find all variables occuring in an OpenMP
    "threadprivate" directive in the given source code.'''
    threadprivate = []
    pattern = r"(^|\n)\s*!\$omp\s+threadprivate\(([^\)]*)\)"
    for match in re.finditer(pattern, source_code):
        s = match.group(2)
        s = s.replace("!$omp", "")
        s = s.replace("&", "")
        s = s.replace(",", " ")
        threadprivate.extend(s.split())
    return threadprivate
