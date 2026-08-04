# SPDX-License-Identifier: BSD-3-Clause

import copy
from typing import List, Dict, Set, Tuple
from psyclone.parse import ModuleManager, FileInfo, ModuleInfo
from psyclone.psyir.nodes import Container
from psyclone.psyir.frontend.fparser2 import Fparser2Reader
import fparser.two.Fortran2003 as ast
from stomp.progress_reporter import ProgressReporter


class ModuleLoaderReport:
    '''Class to report progress of the module loader.'''
    def __init__(self):
        # Map from file names to file/parse errors
        self.file_errors: Dict[str, str] = {}
        # Map from module names to load errors
        self.module_errors: Dict[str, str] = {}
        # List of module names sucessfully loaded
        self.modules_loaded: List[str] = []
        # List of module names encountered but not loaded
        self.modules_not_loaded: Set[str] = set()


def get_modules(report: ModuleLoaderReport,
                file_infos: List[FileInfo]) -> \
        Tuple[Dict[str, ast.Module], Dict[str, FileInfo]]:
    '''Get the modules defined in the given files. Returns a mapping
    from module name to module abstract syntax tree and a mapping
    from module name to file info.'''
    mod_to_tree = {}
    mod_to_file_info = {}
    for info in file_infos:
        ProgressReporter.begin(f"Loading file '{info.filename}'...")
        try:
            tree = info.get_fparser_tree()
        except Exception as err:
            report.file_errors[info.filename] = str(err)
            continue
        ProgressReporter.end()
        for mod in ast.walk(tree, ast.Module):
            # Get the module name
            mod_name = None
            for child in mod.content:
                if isinstance(child, ast.Module_Stmt):
                    mod_name = str(child.items[1]).lower()
                    break
            if mod_name is None: continue
            # Add it to the dict
            mod_to_tree[mod_name] = mod
            mod_to_file_info[mod_name] = info
    return (mod_to_tree, mod_to_file_info)
 

def get_module_deps(mods: Dict[str, ast.Module]) -> Dict[str, Set[str]]:
    '''Compute module dependencies for all modules provided.'''
    deps = {}
    for (mod_name, mod_tree) in mods.items():
       uses = set()
       for child in mod_tree.content:
           for use in ast.walk(child, ast.Use_Stmt):
               uses.add(str(use.items[2]).lower())
           deps[mod_name] = uses
    return deps


def get_imports(report: ModuleLoaderReport,
                info: FileInfo) -> Set[str]:
    '''Compute imports for given source file.'''
    uses = set()
    try:
        tree = info.get_fparser_tree()
    except Exception as err:
        report.file_errors[info.filename] = str(err)
        return uses
    for use in ast.walk(tree, ast.Use_Stmt):
        uses.add(str(use.items[2]).lower())
    return uses


def sort_deps(original_deps: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    '''Sort the dependencies such that any module comes before
    the modules that it depends on.'''
    deps = copy.deepcopy(original_deps)
    sorted_mods = []
    while deps:
       # Get all modules with no dependencies
       no_dep = None
       for (mod, uses) in deps.items():
           if not uses:
               no_dep = mod
               break
       # For a circular dependency, just pick arbitrarily
       if not no_dep:
           no_dep = deps.keys()[0]
       # Add module to sorted dependencies
       sorted_mods.append(no_dep)
       # Remove module from dependencies
       del deps[no_dep]
       # Remove module from dependency set of every other module
       for uses in deps.values():
           uses.discard(no_dep)
    # Return sorted dependencies
    sorted_deps = {}
    for mod in sorted_mods:
        sorted_deps[mod] = original_deps[mod]
    return sorted_deps


def prune_deps(roots: Set[str], deps: Dict[str, Set[str]]) -> \
        Dict[str, Set[str]]:
    '''Prune dependencies that are not reachable from the given roots.'''
    pruned = {}
    frontier = copy.copy(roots)
    visited = set()
    while frontier:
        mod_name = frontier.pop()
        if mod_name in visited: continue
        visited.add(mod_name)
        if mod_name not in deps: continue
        uses = deps[mod_name]
        pruned[mod_name] = uses
        frontier.update(uses - visited)
    return pruned


def load_modules(mod_manager: ModuleManager,
                 top_file: str,
                 files: List[str]) -> ModuleLoaderReport:
    '''Load all modules in given list of files.'''
    # Create the report
    report = ModuleLoaderReport()

    # Add the files to the module manager
    mod_manager.add_files(files + [top_file])
    file_infos = mod_manager._filepath_to_file_info.values()

    # Determine the root modules from the top file
    top_file_info = mod_manager._filepath_to_file_info[top_file]
    roots = get_imports(report, top_file_info)
    if not roots: return report

    # Determine the contained modules and parse trees
    (mod_to_tree, mod_to_file_info) = get_modules(report, file_infos)

    # Determine the contained modules and their dependencies
    deps = get_module_deps(mod_to_tree)

    # Filter out dependencies that are not avilable in the supplied files
    mod_set = set(deps.keys())
    for mod in mod_set:
        # Log imports encountered but not being loaded
        report.modules_not_loaded.update(deps[mod] - mod_set)
        # Ignore modules that are not to be loaded
        deps[mod] &= mod_set

    # Prune dependencies that are not reachable from the roots
    deps = prune_deps(roots, deps)

    # Sort the dependencies
    deps = sort_deps(deps)

    # Generate a ModuleInfo for each module
    mod_infos = {}
    mod_list = list(deps.keys())
    mod_loaded_list = []
    for mod_name in mod_list:
        ProgressReporter.begin(f"Loading module '{mod_name}'...")
        processor = Fparser2Reader(resolve_modules=mod_loaded_list)
        try:
            mod_psyir = module_to_psyir(processor, mod_to_tree[mod_name])
        except Exception as err:
            report.module_errors[mod_name] = str(err)
            report.modules_not_loaded.add(mod_name)
            continue
        ProgressReporter.end()
        mod_loaded_list.append(mod_name)
        mod_infos[mod_name] = ModuleInfo(
            mod_name,
            mod_to_file_info[mod_name], 
            mod_psyir)
        mod_manager._modules[mod_name] = mod_infos[mod_name]

    report.modules_loaded.extend(mod_loaded_list)
    return report


def module_to_psyir(processor: Fparser2Reader,
                    tree: ast.Module) -> Container:
    '''Convert module parse tree to a PSyIR container.'''
    node = Container("dummy")
    processor.process_nodes(node, [tree])
    result = node.children[0]
    return result.detach()
