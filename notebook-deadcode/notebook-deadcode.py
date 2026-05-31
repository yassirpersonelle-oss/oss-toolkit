#!/usr/bin/env python3
"""
notebook-deadcode: Analyze Jupyter notebooks and identify dead code.

Detects unused imports, unreferenced variables, unused functions,
comment-only cells, repeated cells, and orphan cells.
"""

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze Jupyter notebooks for dead code."
    )
    parser.add_argument(
        "--path", required=True, help="Path to a .ipynb file or directory of notebooks"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output results as JSON"
    )
    parser.add_argument("--verbose", action="store_true", help="Show detailed info")
    parser.add_argument(
        "--fix", action="store_true", help="Automatically remove dead cells"
    )
    return parser.parse_args()


def load_notebook(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {path}", file=sys.stderr)
        return None

    if nb.get("nbformat") != 4:
        print(f"Error: {path} is not a valid nbformat 4 notebook", file=sys.stderr)
        return None

    return nb


def get_cell_source(cell):
    source = cell.get("source", [])
    if isinstance(source, list):
        return "".join(source)
    return source


def extract_import_names(code):
    """Extract imported names from code using regex (no external deps)."""
    names = set()
    lines = code.splitlines()
    in_multiline_import = False
    continuation = ""

    for line in lines:
        stripped = line.strip()

        if in_multiline_import:
            continuation += " " + stripped
            if stripped.endswith(","):
                continue
            in_multiline_import = False
            stripped = continuation

        # Handle line continuations
        if stripped.endswith("\\"):
            in_multiline_import = True
            continuation = stripped[:-1]
            continue

        # import X, Y, Z
        m = re.match(r"^import\s+(.+)$", stripped)
        if m:
            for part in m.group(1).split(","):
                part = part.strip()
                # import x.y.z as z or import x.y.z
                if " as " in part:
                    names.add(part.split(" as ")[1].strip())
                else:
                    # take last component
                    names.add(part.strip().split(".")[-1])
            continue

        # from X import Y, Z
        m = re.match(r"^from\s+\S+\s+import\s+(.+)$", stripped)
        if m:
            import_part = m.group(1).strip()
            if import_part == "*":
                continue
            for part in import_part.split(","):
                part = part.strip()
                if part.startswith("(") or part.endswith(")"):
                    part = part.strip("()")
                if not part:
                    continue
                if " as " in part:
                    names.add(part.split(" as ")[1].strip())
                else:
                    names.add(part.split(".")[0].strip())
            continue

    return names


def extract_function_names(code):
    """Extract function definitions from code."""
    names = set()
    for line in code.splitlines():
        m = re.match(r"^\s*def\s+(\w+)\s*\(", line)
        if m:
            names.add(m.group(1))
    return names


def extract_assigned_names(code):
    """Extract variable assignments from code (simple heuristic)."""
    names = set()
    lines = code.splitlines()
    for line in lines:
        stripped = line.strip()
        # Simple assignment: var = expr
        m = re.match(r"^([a-zA-Z_]\w*)\s*=", stripped)
        if m:
            name = m.group(1)
            # Exclude common false positives
            if name not in ("if", "while", "for", "with", "def", "class", "return", "else", "elif", "try", "except", "finally", "from", "import"):
                names.add(name)
        # Augmented assignment: var += expr
        m = re.match(r"^([a-zA-Z_]\w*)\s*[+\-*/]=" , stripped)
        if m:
            names.add(m.group(1))
    return names


def extract_all_names(code):
    """Extract all referenced names from code (broad heuristic)."""
    names = set()
    # Words that look like variable/function references
    for word in re.findall(r"[a-zA-Z_]\w*", code):
        # Skip Python keywords
        if word in ("True", "False", "None", "and", "or", "not", "in", "is",
                     "if", "else", "elif", "for", "while", "with", "def", "class",
                     "return", "import", "from", "try", "except", "finally", "raise",
                     "pass", "break", "continue", "del", "global", "nonlocal",
                     "lambda", "yield", "assert", "print", "as"):
            continue
        names.add(word)
    return names


def is_comment_only(code):
    """Check if code is comment-only (comments and blank lines)."""
    lines = [l.strip() for l in code.splitlines()]
    non_empty = [l for l in lines if l]
    if not non_empty:
        return False
    return all(l.startswith("#") for l in non_empty)


def is_empty_or_whitespace(code):
    """Check if code is empty or whitespace only."""
    return not code.strip()


def similarity_ratio(a, b):
    """Compute similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def analyze_notebook(path, verbose=False):
    nb = load_notebook(path)
    if nb is None:
        return None

    cells = nb.get("cells", [])
    code_cells = []
    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        source = get_cell_source(cell)
        code_cells.append({"index": i, "source": source})

    results = {
        "file": path,
        "total_cells": len(cells),
        "code_cells": len(code_cells),
        "unused_imports": [],
        "unreferenced_variables": [],
        "unused_functions": [],
        "comment_only_cells": [],
        "repeated_cells": [],
        "orphan_cells": [],
    }

    dead_count = 0

    # --- Forward analysis: collect names used in all cells ---
    # For each code cell, compute what it references (all names in its code)
    cell_references = []
    cell_assignments = []
    cell_imports = []
    cell_functions = []

    for cc in code_cells:
        src = cc["source"]
        cell_references.append(extract_all_names(src))
        cell_assignments.append(extract_assigned_names(src))
        cell_imports.append(extract_import_names(src))
        cell_functions.append(extract_function_names(src))

    # --- Unused imports ---
    for i, cc in enumerate(code_cells):
        if not cell_imports[i]:
            continue
        # Check if any imported name is used in any later cell
        used = False
        for later_idx in range(i + 1, len(code_cells)):
            if cell_references[later_idx] & cell_imports[i]:
                used = True
                break
        if not used:
            # Also check if the name is used in the same cell after import
            # (rare but possible with multi-line cells)
            same_cell_rest = "\n".join(code_cells[i]["source"].splitlines()[1:])
            if cell_imports[i] & extract_all_names(same_cell_rest):
                used = True
            if not used:
                results["unused_imports"].append({
                    "cell_index": cc["index"],
                    "code": cc["source"].strip()[:80],
                    "names": sorted(cell_imports[i]),
                })
                dead_count += 1

    # --- Unreferenced variables ---
    for i, cc in enumerate(code_cells):
        if not cell_assignments[i]:
            continue
        # Check if any assigned variable is used in any later cell
        unreferenced = set()
        for var in cell_assignments[i]:
            found = False
            for later_idx in range(i + 1, len(code_cells)):
                if var in cell_references[later_idx]:
                    found = True
                    break
            if not found:
                # Check same cell after assignment line
                lines = cc["source"].splitlines()
                assigned_line_idx = None
                for li, line in enumerate(lines):
                    if re.match(rf"^\s*{re.escape(var)}\s*=", line):
                        assigned_line_idx = li
                        break
                if assigned_line_idx is not None:
                    rest = "\n".join(lines[assigned_line_idx + 1:])
                    if var in extract_all_names(rest):
                        found = True
                if not found:
                    unreferenced.add(var)
        if unreferenced:
            results["unreferenced_variables"].append({
                "cell_index": cc["index"],
                "code": cc["source"].strip()[:80],
                "names": sorted(unreferenced),
            })
            dead_count += 1

    # --- Unused functions ---
    for i, cc in enumerate(code_cells):
        if not cell_functions[i]:
            continue
        for func in cell_functions[i]:
            found = False
            for later_idx in range(i + 1, len(code_cells)):
                if func in cell_references[later_idx]:
                    found = True
                    break
            if not found:
                # Check if called in same cell after definition
                lines = cc["source"].splitlines()
                def_line_idx = None
                for li, line in enumerate(lines):
                    if re.match(rf"^\s*def\s+{re.escape(func)}\s*\(", line):
                        def_line_idx = li
                        break
                if def_line_idx is not None:
                    rest = "\n".join(lines[def_line_idx + 1:])
                    if func in extract_all_names(rest):
                        found = True
                if not found:
                    results["unused_functions"].append({
                        "cell_index": cc["index"],
                        "code": cc["source"].strip()[:80],
                        "names": [func],
                    })
                    dead_count += 1

    # --- Comment-only cells ---
    for cc in code_cells:
        if is_comment_only(cc["source"]):
            results["comment_only_cells"].append({
                "cell_index": cc["index"],
                "code": cc["source"].strip()[:80],
            })
            dead_count += 1

    # --- Repeated cells ---
    seen = {}
    for cc in code_cells:
        src_normalized = re.sub(r"\s+", " ", cc["source"].strip())
        if not src_normalized:
            continue
        for other_src, other_idx in seen.items():
            if similarity_ratio(src_normalized, other_src) >= 0.9:
                # Only count the second one as dead
                results["repeated_cells"].append({
                    "cell_index": cc["index"],
                    "pair_with": other_idx,
                    "code": cc["source"].strip()[:80],
                })
                dead_count += 1
                break
        else:
            seen[src_normalized] = cc["index"]

    # --- Orphan cells ---
    for cc in code_cells:
        src = cc["source"].strip()
        if not src or is_empty_or_whitespace(src):
            continue
        has_assignment = bool(extract_assigned_names(cc["source"]))
        has_import = bool(extract_import_names(cc["source"]))
        has_func_def = bool(extract_function_names(cc["source"]))
        has_output_ref = bool(re.search(r"^\s*print\s*\(", cc["source"], re.MULTILINE))
        has_display = bool(re.search(r"^\s*display\s*\(", cc["source"], re.MULTILINE))
        has_plot = bool(re.search(r"\.(plot|scatter|bar|hist|imshow|savefig)\s*\(", cc["source"]))

        # Orphan: no assignment, no import, no function def, no output
        if not has_assignment and not has_import and not has_func_def:
            if not has_output_ref and not has_display and not has_plot:
                if not is_comment_only(cc["source"]):
                    # Check if the cell just has expressions or standalone statements
                    # that don't produce anything meaningful
                    results["orphan_cells"].append({
                        "cell_index": cc["index"],
                        "code": cc["source"].strip()[:80],
                    })
                    dead_count += 1

    results["dead_count"] = dead_count
    return results


def format_report(results, verbose=False):
    if results is None:
        return ""

    lines = []
    lines.append(f"\033[1m📊 notebook-deadcode: {results['file']}\033[0m")
    lines.append("━" * 40)

    if results["unused_imports"]:
        lines.append(f"\n\033[31m  🔴 Unused imports ({len(results['unused_imports'])} cells)\033[0m")
        for item in results["unused_imports"]:
            lines.append(f"     Cell {item['cell_index']}: `{item['code'][:60]}` — never used later")

    if results["unreferenced_variables"]:
        lines.append(f"\n\033[33m  🟡 Unreferenced variables ({len(results['unreferenced_variables'])} cells)\033[0m")
        for item in results["unreferenced_variables"]:
            lines.append(f"     Cell {item['cell_index']}: `{item['code'][:60]}` — never referenced later")

    if results["unused_functions"]:
        lines.append(f"\n\033[33m  🟠 Unused functions ({len(results['unused_functions'])} cells)\033[0m")
        for item in results["unused_functions"]:
            lines.append(f"     Cell {item['cell_index']}: `{item['code'][:60]}` — never called later")

    if results["comment_only_cells"]:
        lines.append(f"\n\033[37m  ⚪ Comment-only cells ({len(results['comment_only_cells'])} cells)\033[0m")
        for item in results["comment_only_cells"]:
            lines.append(f"     Cell {item['cell_index']}: only comments")

    if results["repeated_cells"]:
        lines.append(f"\n\033[33m  ⚠️  Repeated cells ({len(results['repeated_cells'])} pairs)\033[0m")
        for item in results["repeated_cells"]:
            lines.append(f"     Cells {item['cell_index']} & {item['pair_with']}: identical or near-identical code")

    if results["orphan_cells"]:
        lines.append(f"\n\033[37m  ⚪ Orphan cells ({len(results['orphan_cells'])} cells)\033[0m")
        for item in results["orphan_cells"]:
            lines.append(f"     Cell {item['cell_index']}: `{item['code'][:60]}`")

    total = results["code_cells"]
    dead = results["dead_count"]
    pct = (dead / total * 100) if total > 0 else 0
    lines.append(f"\n\033[1m📊 Summary: {total} code cells, {dead} dead ({pct:.1f}%)\033[0m")

    return "\n".join(lines)


def format_json(results):
    if results is None:
        return "{}"
    return json.dumps(results, indent=2, ensure_ascii=False)


def fix_notebook(path, results):
    """Remove dead cells from notebook. Returns count of removed cells."""
    if results is None or results["dead_count"] == 0:
        print("Nothing to fix.")
        return 0

    nb = load_notebook(path)
    if nb is None:
        return 0

    cells = nb.get("cells", [])
    dead_indices = set()

    for category in ["unused_imports", "unreferenced_variables", "unused_functions",
                      "comment_only_cells", "orphan_cells"]:
        for item in results[category]:
            dead_indices.add(item["cell_index"])

    # For repeated cells, only remove the duplicate (higher index)
    for item in results["repeated_cells"]:
        dead_indices.add(item["cell_index"])

    # Sort indices in reverse so removal doesn't shift positions
    for idx in sorted(dead_indices, reverse=True):
        if 0 <= idx < len(cells):
            del cells[idx]

    nb["cells"] = cells

    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

    return len(dead_indices)


def collect_notebooks(path):
    """Collect all .ipynb files from path."""
    p = Path(path)
    if p.is_file() and p.suffix == ".ipynb":
        return [str(p)]
    elif p.is_dir():
        notebooks = []
        for fp in p.rglob("*.ipynb"):
            # Skip .ipynb_checkpoints and hidden dirs
            parts = fp.parts
            if any(part.startswith(".") for part in parts):
                continue
            if ".ipynb_checkpoints" in str(fp):
                continue
            notebooks.append(str(fp))
        return sorted(notebooks)
    else:
        print(f"Error: {path} is not a valid .ipynb file or directory", file=sys.stderr)
        return []


def main():
    # Ensure UTF-8 output on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    args = parse_args()
    notebooks = collect_notebooks(args.path)

    if not notebooks:
        print("No notebooks found.", file=sys.stderr)
        sys.exit(1)

    total_dead = 0
    total_cells = 0

    for nb_path in notebooks:
        results = analyze_notebook(nb_path, verbose=args.verbose)
        if results is None:
            continue

        total_dead += results["dead_count"]
        total_cells += results["code_cells"]

        if args.json_output:
            print(format_json(results))
        else:
            print(format_report(results, verbose=args.verbose))

        if args.fix and results["dead_count"] > 0:
            removed = fix_notebook(nb_path, results)
            print(f"\n  🛠️  Removed {removed} dead cell(s) from {nb_path}")

    if len(notebooks) > 1 and not args.json_output:
        pct = (total_dead / total_cells * 100) if total_cells > 0 else 0
        print(f"\n\033[1m📊 Total: {len(notebooks)} notebooks, {total_cells} code cells, {total_dead} dead ({pct:.1f}%)\033[0m")


if __name__ == "__main__":
    main()
