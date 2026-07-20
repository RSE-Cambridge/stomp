# SPDX-License-Identifier: BSD-3-Clause

'''This file provides functionality to handle directives that appear in the
specifiation part of a module definition, e.g. OpenMP's "threadprivate"
directive and stomp's "threadsafe" directive. These directives are not
available in the PSyIR, so we use use imperfect regex matching on the raw
source code to locate them.  In future, we could search the parse tree rather
than the raw source for a more robust solution.
'''

import re
from typing import List, Tuple
from psyclone.parse.module_manager import ModuleManager
from psyclone.psyir.nodes import Node, Container, Reference
from psyclone.psyir.symbols import ImportInterface, Symbol, RoutineSymbol


def parse_module_spec_directives(
        top_source_code: str,
        top_psyir: Node,
        mod_manager: ModuleManager = None):
    '''Iterate over each module and handle directives in the specification
    part of the module definition, e.g. "threadprivate" and "threadsafe"
    directives.'''
    if mod_manager is None:
        source_code_list = [top_source_code]
        psyir_list = [top_psyir]
    else:
        mod_infos = mod_manager.all_module_infos
        source_code_list = [top_source_code] + \
                           [m.get_source_code() for m in mod_infos]
        psyir_list = [top_psyir] + [m.get_psyir() for m in mod_infos]
    for (source_code, psyir) in zip(source_code_list, psyir_list):
        if not psyir: continue
        for (mod_name, spec) in get_module_specs(source_code):
            threadprivate = get_threadprivate(spec)
            threadsafe = get_threadsafe(spec)
            for c in psyir.walk(Container):
                if c.name.lower() == mod_name:
                    for v in threadprivate:
                        try:
                            sym = c.symbol_table.lookup(v)
                            # Mark symbol as threadprivate
                            sym.is_threadprivate = True
                        except Exception:
                            continue
                    for v in threadsafe:
                        try:
                            sym = c.symbol_table.lookup(v)
                            # Mark symbol as threadsafe
                            sym.is_threadsafe = True
                        except Exception:
                            continue


def get_module_specs(source_code: str) -> List[Tuple[str, str]]:
    '''Use a regex to find the specification part of all modules in
    in the given source code.'''
    result = []
    begin_module = r"(^|\n)\s*module\s(.*?)\s(.*?)"
    end_module = r"\n\s*(end\s*module|contains)"
    pattern = begin_module + end_module
    for m in re.finditer(pattern, source_code.lower(), flags=re.DOTALL):
        mod_name = m.group(2)
        spec = m.group(3)
        result.append((mod_name, spec))
    return result


def get_threadprivate(source_code: str):
    '''Use a regex to find all variables occuring in an OpenMP
    "threadprivate" directive in the given source code.'''
    threadprivate = []
    pattern = r"(^|\n)\s*!\$omp\s+threadprivate\s*\(([^\)]*)\)"
    for m in re.finditer(pattern, source_code):
        s = m.group(2)
        s = s.replace("!$omp", "")
        s = s.replace("&", "")
        s = s.replace(",", " ")
        threadprivate.extend(s.split())
    return threadprivate


def get_threadsafe(source_code: str):
    '''Use a regex to find all identifiers occuring in a stomp
    "threadsafe" directive in the given source code.'''
    threadsafe = []
    pattern = r"(^|\n)\s*!\$stomp\s+threadsafe\s*\(([^\)]*)\)"
    for m in re.finditer(pattern, source_code):
        s = m.group(2)
        s = s.replace("!$stomp", "")
        s = s.replace("&", "")
        s = s.replace(",", " ")
        threadsafe.extend(s.split())
    return threadsafe


def sym_has_field(sym: Symbol, field_name: str) -> bool:
    '''Chase down the given symbol and determine if it has the given
    field name present.'''
    seen = set()
    while True:
        if hasattr(sym, "is_threadprivate"):
            return True
        if hasattr(sym, "is_threadsafe"):
            return True
        elif isinstance(sym.interface, ImportInterface):
            con_sym = sym.interface.container_symbol
            try:
                sym_tab = con_sym.find_container_psyir().symbol_table
            except Exception:
                return False
            if id(sym_tab) in seen:
                return False
            else:
                seen.add(id(sym_tab))
            try:
                if sym.interface.orig_name is None:
                    sym = sym_tab.lookup(sym.name)
                else:
                    sym = sym_tab.lookup(sym.interface.orig_name)
            except Exception:
                return False
        else:
            return False


def is_threadprivate(ref: Reference) -> bool:
    '''Determine whether the given reference is a reference to a
    threadprivate variable.'''
    return sym_has_field(ref.symbol, "is_threadprivate")


def is_threadsafe(sym: RoutineSymbol) -> bool:
    '''Determine whether the given routine symbol is a reference to
    a routine that is marked as threadsafe.''' 
    return sym_has_field(sym, "is_threadsafe")
