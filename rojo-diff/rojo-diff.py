#!/usr/bin/env python3
"""rojo-diff: Validate a Rojo default.project.json structure against the filesystem."""

import json
import os
import sys
import argparse

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

CLASS_NAME_TYPOS = {
    "ServerScripService": "ServerScriptService",
    "RepliicatedStorage": "ReplicatedStorage",
    "StarterPlay": "StarterPlayer",
    "StarterChar": "StarterCharacter",
    "StarterPack": "StarterPlayerScripts",
    "Playergui": "StarterGui",
    "ServerStorage": "ServerStorage",
    "ServerScritService": "ServerScriptService",
    "ReplicatedStrage": "ReplicatedStorage",
    "RunService": "RunService",
}

SUPPORTED_EXTENSIONS = (".lua", ".luau")


def find_project_file():
    for candidate in ("default.project.json", "sourcemap.json", "project.json"):
        if os.path.isfile(candidate):
            return candidate
    return None


def load_project(path):
    if not os.path.isfile(path):
        print(f"{RED}Error:{RESET} Project file not found: {path}")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"{RED}Error:{RESET} Invalid JSON in {path}: {e}")
        sys.exit(1)


def check_class_name_typos(name, issues):
    if not isinstance(name, str):
        return
    for typo, suggestion in CLASS_NAME_TYPOS.items():
        if typo.lower() == name.lower() and typo != name:
            issues.append(("warning", f"Class name typo '{name}' — did you mean '{suggestion}'?"))
            return


def walk_tree(node, base_dir, issues, verbose, visited=None, depth=0):
    if visited is None:
        visited = set()

    node_id = id(node)
    if node_id in visited:
        if verbose:
            print(f"{'  ' * depth}{CYAN}[circular ref detected]{RESET}")
        return
    visited.add(node_id)

    if not isinstance(node, dict):
        return

    class_name = node.get("$className", "Instance")
    path = node.get("$path", "")

    display_name = path or class_name

    if verbose:
        path_info = f" → {path}" if path else ""
        print(f"{'  ' * depth}{BOLD}{CYAN}{class_name}{RESET}: {display_name}{path_info}")

    if path:
        abs_path = os.path.join(base_dir, path)

        if not os.path.exists(abs_path):
            issues.append(("error", f"Missing directory/file: {path}"))
        else:
            if os.path.isdir(abs_path):
                if class_name in ("ModuleScript", "LocalScript", "Script"):
                    issues.append(("warning", f"Path '{path}' is a directory but $className is '{class_name}' — expected a file"))

                if not any(abs_path.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                    has_init = os.path.isfile(os.path.join(abs_path, "init.lua")) or os.path.isfile(os.path.join(abs_path, "init.luau"))
                    if not has_init:
                        dir_has_files = False
                        for entry in os.listdir(abs_path):
                            if entry.endswith(SUPPORTED_EXTENSIONS):
                                dir_has_files = True
                                break
                        if not dir_has_files:
                            issues.append(("warning", f"Directory '{path}' has no .lua/.luau files or init.luau"))
    check_class_name_typos(class_name, issues)

    children = node.get("children", node.get("$children", {}))
    if isinstance(children, dict):
        for child_name, child_node in children.items():
            walk_tree(child_node, base_dir, issues, verbose, visited, depth + 1)
    elif isinstance(children, list):
        for child_node in children:
            walk_tree(child_node, base_dir, issues, verbose, visited, depth + 1)


def main():
    parser = argparse.ArgumentParser(
        description="Validate a Rojo default.project.json structure against the filesystem."
    )
    parser.add_argument("-p", "--project", default=None, help="Path to default.project.json (default: auto-detect)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed tree structure")
    args = parser.parse_args()

    project_path = args.project or find_project_file()
    if not project_path:
        print(f"{RED}Error:{RESET} No project file found. Specify with --project or run from a Rojo project directory.")
        sys.exit(1)

    data = load_project(project_path)
    base_dir = os.path.dirname(os.path.abspath(project_path))
    tree = data.get("tree") or data

    issues = []

    if args.verbose:
        print(f"{BOLD}Project:{RESET} {project_path}")
        print(f"{BOLD}Root dir:{RESET} {base_dir}")
        print(f"{BOLD}Tree structure:{RESET}")
        print("-" * 50)

    walk_tree(tree, base_dir, issues, args.verbose)

    if args.verbose:
        print("-" * 50)

    errors = [i for i in issues if i[0] == "error"]
    warnings = [i for i in issues if i[0] == "warning"]

    if args.json_output:
        result = {
            "project": project_path,
            "valid": len(errors) == 0,
            "errors": [i[1] for i in errors],
            "warnings": [i[1] for i in warnings],
        }
        print(json.dumps(result, indent=2))
        sys.exit(1 if errors else 0)

    if errors:
        print(f"{RED}{BOLD}ERRORS ({len(errors)}):{RESET}")
        for _, msg in errors:
            print(f"  {RED}✗{RESET} {msg}")

    if warnings:
        print(f"{YELLOW}{BOLD}WARNINGS ({len(warnings)}):{RESET}")
        for _, msg in warnings:
            print(f"  {YELLOW}⚠{RESET} {msg}")

    if not errors and not warnings:
        print(f"{GREEN}Rojo project validated successfully{RESET}")
    elif not errors:
        print(f"{GREEN}Validation passed with {len(warnings)} warning(s){RESET}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
