#!/usr/bin/env python3
"""luau-type-coverage — Track Luau type annotation coverage in your codebase."""

import argparse
import json
import os
import re
import sys

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_CYAN = "\033[96m"
ANSI_MAGENTA = "\033[95m"
ANSI_DIM = "\033[2m"

FUNC_RE = re.compile(
    r"(?:(?:local\s+)?function\s+|local\s+function\s+)"
    r"(?P<name>[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*(?:::[a-zA-Z_]\w*)*)"
    r"\s*\((?P<params>[^)]*)\)"
    r"(?:\s*:\s*(?P<return_type>[a-zA-Z_]\w*(?:\s*\|\s*[a-zA-Z_]\w*)*"
    r"|\"[^\"]*\"|'[^']*'|nil|boolean|number|string|thread|function|table|any"
    r"|\{[^}]*\}|\([^)]*\)))?"
)

PARAM_RE = re.compile(
    r"(?P<name>[a-zA-Z_]\w*)\s*(?::\s*(?P<type>[^,]+?))?(?:\s*,\s*|$)"
)

STRICT_RE = re.compile(r"^--!strict\s*$")
NOCHECK_RE = re.compile(r"^--!nocheck\s*$")
EXPORT_TYPE_RE = re.compile(
    r"(?:export\s+)?type\s+(?P<name>[a-zA-Z_]\w*)"
    r"\s*=\s*(?P<def>.+)"
)
CHECKED_ANNOTATION_RE = re.compile(r"--\s*@checked")
TYPE_ANNOTATION_RE = re.compile(r"--\s*(@\w+)")


def use_color():
    return sys.stdout.isatty()


def c(text, code):
    if not use_color():
        return text
    return f"{code}{text}{ANSI_RESET}"


def scan_params(params_str):
    typed = 0
    total = 0
    for m in PARAM_RE.finditer(params_str.strip()):
        name = m.group("name").strip()
        if not name or name == "...":
            continue
        total += 1
        if m.group("type") and m.group("type").strip():
            typed += 1
    return typed, total


def classify_function(params_str, has_return_type, is_strict, is_checked):
    typed, total = scan_params(params_str)
    params_fully_typed = total > 0 and typed == total
    any_params_typed = typed > 0

    if is_checked:
        return "typed"

    if has_return_type and params_fully_typed:
        return "typed"
    elif has_return_type and any_params_typed and total > typed:
        return "partial"
    elif params_fully_typed and total > 0:
        return "typed"
    elif any_params_typed and total > typed:
        return "partial"

    if is_strict:
        if total == 0:
            if has_return_type:
                return "typed"
            return "untyped"
        if params_fully_typed:
            return "typed"
        elif any_params_typed:
            return "partial"
        else:
            return "untyped"

    if has_return_type and total == 0:
        return "typed"

    return "untyped"


def analyze_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None

    content = "".join(lines)

    is_strict = any(STRICT_RE.match(line.strip()) for line in lines)
    is_nocheck = any(NOCHECK_RE.match(line.strip()) for line in lines)

    export_types = []
    for m in EXPORT_TYPE_RE.finditer(content):
        export_types.append({
            "name": m.group("name"),
            "definition": m.group("def").strip(),
        })

    annotations = []
    for m in TYPE_ANNOTATION_RE.finditer(content):
        annotations.append(m.group(1))

    functions = []
    for m in FUNC_RE.finditer(content):
        name = m.group("name")
        params_str = m.group("params")
        return_type = m.group("return_type")
        func_text = m.group(0)

        line_start = content[:m.start()].count("\n") + 1

        has_return = return_type is not None and return_type.strip() != ""
        is_checked = bool(CHECKED_ANNOTATION_RE.search(
            content[:m.start()]
        ))

        classification = classify_function(
            params_str, has_return, is_strict, is_checked
        )

        typed_param, total_param = scan_params(params_str)

        functions.append({
            "name": name,
            "line": line_start,
            "params_total": total_param,
            "params_typed": typed_param,
            "has_return_type": has_return,
            "return_type": return_type.strip() if return_type else None,
            "classification": classification,
            "is_checked": is_checked,
        })

    total_funcs = len(functions)
    typed_count = sum(1 for f in functions if f["classification"] == "typed")
    partial_count = sum(1 for f in functions if f["classification"] == "partial")
    untyped_count = sum(1 for f in functions if f["classification"] == "untyped")
    type_defs_count = len(export_types)

    file_score = (
        (typed_count / total_funcs * 100) if total_funcs > 0 else
        (100.0 if type_defs_count > 0 else 0.0)
    )

    return {
        "file": filepath,
        "is_strict": is_strict,
        "is_nocheck": is_nocheck,
        "functions": functions,
        "export_types": export_types,
        "annotations": annotations,
        "total_funcs": total_funcs,
        "typed_count": typed_count,
        "partial_count": partial_count,
        "untyped_count": untyped_count,
        "type_defs_count": type_defs_count,
        "file_score": file_score,
    }


def scan_directory(root_path):
    results = []
    skipped = 0
    for dirpath, _, filenames in os.walk(root_path):
        for fname in filenames:
            if not (fname.endswith(".lua") or fname.endswith(".luau")):
                continue
            full = os.path.join(dirpath, fname)
            analysis = analyze_file(full)
            if analysis is None:
                skipped += 1
                continue
            results.append(analysis)
    return results, skipped


def print_verbose(results):
    for r in results:
        rel = os.path.relpath(r["file"])
        badge = ""
        if r["is_strict"]:
            badge += c(" [strict]", ANSI_CYAN)
        if r["is_nocheck"]:
            badge += c(" [nocheck]", ANSI_DIM)
        score_color = ANSI_RED
        if r["file_score"] >= 80:
            score_color = ANSI_GREEN
        elif r["file_score"] >= 50:
            score_color = ANSI_YELLOW

        file_pct = f"{r['file_score']:.1f}%"
        print(f"\n  {c(rel, ANSI_BOLD)}{badge}  —  "
              f"{c(file_pct, score_color)}  "
              f"[{len(r['functions'])} funcs]")

        for f in r["functions"]:
            icon = {"typed": "✅", "partial": "⚠️ ", "untyped": "❌"}[f["classification"]]
            params_detail = ""
            if f["params_total"] > 0:
                params_detail = f" ({f['params_typed']}/{f['params_total']} typed)"
            ret = f": {f['return_type']}" if f["has_return_type"] else ""
            checked = " @checked" if f["is_checked"] else ""
            print(f"     {icon} L{f['line']:>4d}  {c(f['name'], ANSI_BOLD)}"
                  f"({f['params_total']} params{params_detail}){ret}{checked}")


def print_report(results, root_path, threshold, verbose):
    total_files = len(results)
    total_funcs = sum(r["total_funcs"] for r in results)
    total_typed = sum(r["typed_count"] for r in results)
    total_partial = sum(r["partial_count"] for r in results)
    total_untyped = sum(r["untyped_count"] for r in results)
    total_type_defs = sum(r["type_defs_count"] for r in results)
    strict_files = sum(1 for r in results if r["is_strict"])
    nocheck_files = sum(1 for r in results if r["is_nocheck"])

    typed_pct = (total_typed / total_funcs * 100) if total_funcs > 0 else 0.0
    partial_pct = (total_partial / total_funcs * 100) if total_funcs > 0 else 0.0
    untyped_pct = (total_untyped / total_funcs * 100) if total_funcs > 0 else 0.0
    strict_pct = (strict_files / total_files * 100) if total_files > 0 else 0.0

    overall_score = typed_pct

    print()
    print(f"  {c('Luau Type Coverage Report', ANSI_BOLD)} — {c(root_path, ANSI_CYAN)}")
    print(f"  {c('─' * 51, ANSI_DIM)}")
    print()
    print(f"    {c('Scanned:', ANSI_DIM)} {total_files} files, {total_funcs} functions, "
          f"{total_type_defs} types defined")
    if nocheck_files > 0:
        print(f"    {c('Skipped (nocheck):', ANSI_DIM)} {nocheck_files} files")
    print()
    print(f"    {c('Fully typed:', ANSI_GREEN)}   {total_typed:>5d} ({typed_pct:.1f}%)")
    print(f"    {c('Partial:', ANSI_YELLOW)}      {total_partial:>5d} ({partial_pct:.1f}%)")
    print(f"    {c('Untyped:', ANSI_RED)}        {total_untyped:>5d} ({untyped_pct:.1f}%)")
    print()
    print(f"    {c('Strict mode:', ANSI_CYAN)}   {strict_files}/{total_files} files "
          f"({strict_pct:.1f}%)")
    print()
    score_color = ANSI_RED
    if overall_score >= 80:
        score_color = ANSI_GREEN
    elif overall_score >= 50:
        score_color = ANSI_YELLOW
    print(f"    {c('Overall coverage:', ANSI_BOLD)} {c(f'{overall_score:.1f}%', score_color)}")
    print()

    if threshold > 0 and overall_score < threshold:
        print(f"  {c(f'Below threshold of {threshold}%', ANSI_RED)}")
        print()

    if verbose:
        print_verbose(results)

    return overall_score


def print_json(results, root_path, skipped):
    total_files = len(results)
    total_funcs = sum(r["total_funcs"] for r in results)
    total_typed = sum(r["typed_count"] for r in results)
    total_partial = sum(r["partial_count"] for r in results)
    total_untyped = sum(r["untyped_count"] for r in results)
    total_type_defs = sum(r["type_defs_count"] for r in results)
    strict_files = sum(1 for r in results if r["is_strict"])

    output = {
        "path": os.path.abspath(root_path),
        "summary": {
            "files_scanned": total_files,
            "files_skipped": skipped,
            "total_functions": total_funcs,
            "typed": total_typed,
            "partial": total_partial,
            "untyped": total_untyped,
            "type_definitions": total_type_defs,
            "strict_files": strict_files,
            "overall_coverage_pct": round(
                (total_typed / total_funcs * 100) if total_funcs > 0 else 0.0, 1
            ),
        },
        "files": [],
    }

    for r in results:
        entry = {
            "file": os.path.relpath(r["file"]),
            "is_strict": r["is_strict"],
            "is_nocheck": r["is_nocheck"],
            "total_funcs": r["total_funcs"],
            "typed": r["typed_count"],
            "partial": r["partial_count"],
            "untyped": r["untyped_count"],
            "type_defs": r["type_defs_count"],
            "file_coverage_pct": round(r["file_score"], 1),
            "functions": [],
            "export_types": r["export_types"],
        }
        for f in r["functions"]:
            entry["functions"].append({
                "name": f["name"],
                "line": f["line"],
                "params_total": f["params_total"],
                "params_typed": f["params_typed"],
                "has_return_type": f["has_return_type"],
                "return_type": f["return_type"],
                "classification": f["classification"],
                "checked": f["is_checked"],
            })
        output["files"].append(entry)

    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Track Luau type annotation coverage in your codebase."
    )
    parser.add_argument(
        "--path", required=True,
        help="Directory to scan for .lua / .luau files"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show per-file breakdown"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.0,
        help="Minimum type coverage %% (exit code 1 if below)"
    )
    args = parser.parse_args()

    if not args.json:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print(f"Error: '{args.path}' is not a directory.", file=sys.stderr)
        sys.exit(2)

    results, skipped = scan_directory(root)

    if not results:
        print(f"No .lua or .luau files found in '{args.path}'.")
        sys.exit(0 if args.threshold == 0 else 1)

    if args.json:
        print_json(results, root, skipped)
    else:
        coverage = print_report(results, root, args.threshold, args.verbose)
        if args.threshold > 0 and coverage < args.threshold:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
