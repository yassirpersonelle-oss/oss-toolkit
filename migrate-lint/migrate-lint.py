#!/usr/bin/env python3
"""migrate-lint: Lint Django migrations for dangerous patterns before they hit production."""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------
ERROR = "error"
WARNING = "warning"
INFO = "info"

SEVERITY_ICONS = {
    ERROR: "🔴",
    WARNING: "🟡",
    INFO: "⚪",
}

SEVERITY_ORDER = [ERROR, WARNING, INFO]


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------
class Issue:
    def __init__(self, filename, line, rule_id, severity, message):
        self.filename = filename
        self.line = line
        self.rule_id = rule_id
        self.severity = severity
        self.message = message

    def to_dict(self):
        return {
            "file": self.filename,
            "line": self.line,
            "rule": self.rule_id,
            "severity": self.severity,
            "message": self.message,
        }


def _parse_migration(filepath):
    """Parse a migration file and return the AST tree, or None on error."""
    try:
        source = Path(filepath).read_text(encoding="utf-8")
        return ast.parse(source, filename=filepath)
    except SyntaxError:
        return None


def _get_call_name(node):
    """Return a dotted name for a Call node (e.g. 'migrations.RunSQL')."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = [node.func.attr]
        current = node.func.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return ""


def _call_has_keyword(call, keyword_name):
    return any(kw.arg == keyword_name for kw in call.keywords)


def _get_keyword_value(call, keyword_name):
    for kw in call.keywords:
        if kw.arg == keyword_name:
            return kw.value
    return None


def _is_string_constant(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    return False


def _string_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _is_elidable(sql_text):
    """Check if the SQL is marked as elidable."""
    return "-- elidable" in sql_text.lower()


def _is_destructive_sql(sql_text):
    upper = sql_text.upper()
    for pattern in [r"\bDROP\b", r"\bDELETE\b", r"\bTRUNCATE\b", r"\bALTER\s+TABLE.*DROP\b"]:
        if re.search(pattern, upper):
            return True
    return False


def _collect_field_names(tree):
    """Collect all field names referenced in AddField / AlterField / RemoveField."""
    field_names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _get_call_name(node)
        if name in ("migrations.AddField", "migrations.AlterField", "migrations.RemoveField"):
            for kw in node.keywords:
                if kw.arg == "name" and _is_string_constant(kw.value):
                    field_names.append(_string_value(kw.value))
    return field_names


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

def rule_raw_sql_destructive(filepath, tree, source):
    """RunSQL with destructive SQL and no --elidable."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _get_call_name(node) != "migrations.RunSQL":
            continue
        sql_node = None
        for kw in node.keywords:
            if kw.arg == "sql" and _is_string_constant(kw.value):
                sql_node = kw.value
                break
        if not sql_node:
            args = [a for a in node.args if _is_string_constant(a)]
            if args:
                sql_node = args[0]
        if sql_node is None:
            continue
        sql_text = _string_value(sql_node)
        if _is_destructive_sql(sql_text) and not _is_elidable(sql_text):
            issues.append(Issue(
                filepath, node.lineno, "destructive-sql", WARNING,
                "RunSQL with destructive SQL (DROP/DELETE/TRUNCATE) — no --elidable marker"
            ))
    return issues


def rule_missing_reverse_sql(filepath, tree, source):
    """RunSQL without reverse_sql."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _get_call_name(node) != "migrations.RunSQL":
            continue
        if not _call_has_keyword(node, "reverse_sql"):
            issues.append(Issue(
                filepath, node.lineno, "missing-reverse-sql", ERROR,
                "RunSQL without reverse_sql — cannot reverse this migration"
            ))
    return issues


def rule_dangerous_field_rename(filepath, tree, source):
    """RenameField without prior AlterField in the same migration."""
    rename_fields = []
    alter_fields = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _get_call_name(node)
        if name == "migrations.RenameField":
            old = new = None
            for kw in node.keywords:
                if kw.arg == "old_name" and _is_string_constant(kw.value):
                    old = _string_value(kw.value)
                if kw.arg == "new_name" and _is_string_constant(kw.value):
                    new = _string_value(kw.value)
            if old and new:
                rename_fields.append((old, new, node.lineno))
        elif name == "migrations.AlterField":
            for kw in node.keywords:
                if kw.arg == "name" and _is_string_constant(kw.value):
                    alter_fields.add(_string_value(kw.value))
    issues = []
    for old, new, lineno in rename_fields:
        if old not in alter_fields:
            issues.append(Issue(
                filepath, lineno, "dangerous-rename", WARNING,
                f"RenameField '{old}' -> '{new}' without AlterField first — may break in-flight requests"
            ))
    return issues


def rule_remove_field_still_referenced(filepath, tree, source, all_migrations):
    """RemoveField where the field name appears in other files' AddField/AlterField."""
    remove_fields = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _get_call_name(node) != "migrations.RemoveField":
            continue
        model = field = None
        for kw in node.keywords:
            if kw.arg == "model_name" and _is_string_constant(kw.value):
                model = _string_value(kw.value)
            if kw.arg == "name" and _is_string_constant(kw.value):
                field = _string_value(kw.value)
        if model and field:
            remove_fields.append((model, field, node.lineno))
    if not remove_fields:
        return []
    issues = []
    for model, field, lineno in remove_fields:
        for other_file, other_tree in all_migrations.items():
            if other_file == filepath:
                continue
            for n in ast.walk(other_tree):
                if not isinstance(n, ast.Call):
                    continue
                cn = _get_call_name(n)
                if cn in ("migrations.AddField", "migrations.AlterField"):
                    f_model = f_name = None
                    for kw in n.keywords:
                        if kw.arg == "model_name" and _is_string_constant(kw.value):
                            f_model = _string_value(kw.value)
                        if kw.arg == "name" and _is_string_constant(kw.value):
                            f_name = _string_value(kw.value)
                    if f_model == model and f_name == field:
                        issues.append(Issue(
                            filepath, lineno, "remove-still-referenced", WARNING,
                            f"RemoveField '{field}' on '{model}' — still referenced in {other_file}; use AlterField first"
                        ))
                        break
    return issues


def rule_add_not_null_no_default(filepath, tree, source):
    """AddField with null=False and no default / preserve_default=False."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _get_call_name(node) != "migrations.AddField":
            continue
        has_null_false = False
        has_default = False
        preserve_default_false = False
        field_name = ""
        for kw in node.keywords:
            if kw.arg == "name" and _is_string_constant(kw.value):
                field_name = _string_value(kw.value)
            if kw.arg == "field":
                if isinstance(kw.value, ast.Call):
                    for fkw in kw.value.keywords:
                        if fkw.arg == "null":
                            val = fkw.value
                            if isinstance(val, ast.Constant) and val.value is False:
                                has_null_false = True
                        if fkw.arg == "default":
                            has_default = True
                        if fkw.arg == "preserve_default":
                            if isinstance(fkw.value, ast.Constant) and fkw.value.value is False:
                                preserve_default_false = True
        if has_null_false and not has_default and not preserve_default_false:
            issues.append(Issue(
                filepath, node.lineno, "not-null-no-default", ERROR,
                f"AddField '{field_name}' with null=False, no default — will fail on existing rows"
            ))
    return issues


def rule_add_index_huge_table(filepath, tree, source):
    """AddIndex without mentioning table size (warning)."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _get_call_name(node)
        if name in ("migrations.AddIndex", "migrations.AddIndexConcurrently"):
            if not _call_has_keyword(node, "table_size"):
                issues.append(Issue(
                    filepath, node.lineno, "index-huge-table", WARNING,
                    "AddIndex without table_size hint — may lock a large table"
                ))
    return issues


def rule_runpython_no_reverse(filepath, tree, source):
    """RunPython without reverse_code=noop for non-reversible ops."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _get_call_name(node) != "migrations.RunPython":
            continue
        if _call_has_keyword(node, "reverse_code"):
            continue
        issues.append(Issue(
            filepath, node.lineno, "runpython-no-reverse", INFO,
            "RunPython without reverse_code=migrations.RunPython.noop — non-reversible"
        ))
    return issues


def rule_empty_migration(filepath, tree, source):
    """Migration with no operations."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "operations":
                    if isinstance(node.value, ast.List) and len(node.value.elts) == 0:
                        return [Issue(
                            filepath, node.lineno, "empty-migration", INFO,
                            "Empty migration — no operations defined"
                        )]
    return []


def rule_missing_dependencies(filepath, tree, source):
    """Migration without a dependencies list."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "dependencies":
                    if isinstance(node.value, ast.List):
                        return []
    return [Issue(
        filepath, 1, "missing-dependencies", INFO,
        "Migration without dependencies list"
    )]


# ---------------------------------------------------------------------------
# Main scanning logic
# ---------------------------------------------------------------------------

def find_migration_files(root):
    """Find all migration Python files under root."""
    files = []
    root_path = Path(root)
    for path in root_path.rglob("migrations"):
        if path.is_dir():
            for py in sorted(path.glob("*.py")):
                if py.name.startswith("_"):
                    continue
                files.append(str(py))
    return files


def lint_file(filepath, all_migrations):
    """Run all rules on a single file and return a list of Issues."""
    tree = _parse_migration(filepath)
    if tree is None:
        return [Issue(filepath, 0, "parse-error", ERROR, "Could not parse migration file (syntax error)")]

    source = Path(filepath).read_text(encoding="utf-8")
    issues = []
    issues.extend(rule_raw_sql_destructive(filepath, tree, source))
    issues.extend(rule_missing_reverse_sql(filepath, tree, source))
    issues.extend(rule_dangerous_field_rename(filepath, tree, source))
    issues.extend(rule_remove_field_still_referenced(filepath, tree, source, all_migrations))
    issues.extend(rule_add_not_null_no_default(filepath, tree, source))
    issues.extend(rule_add_index_huge_table(filepath, tree, source))
    issues.extend(rule_runpython_no_reverse(filepath, tree, source))
    issues.extend(rule_empty_migration(filepath, tree, source))
    issues.extend(rule_missing_dependencies(filepath, tree, source))
    return issues


def detect_duplicate_numbers(files):
    """Detect duplicate migration numbers within the same app."""
    from collections import defaultdict
    app_groups = defaultdict(list)
    num_re = re.compile(r"^(\d+)")
    for f in files:
        name = Path(f).stem
        match = num_re.match(name)
        if match:
            parts = Path(f).parts
            # find the 'migrations' folder and use parent as app
            for i, part in enumerate(parts):
                if part == "migrations" and i > 0:
                    app = parts[i - 1]
                    app_groups[app].append((match.group(1), f))
                    break
    issues = []
    for app, entries in app_groups.items():
        seen = {}
        for num, f in entries:
            if num in seen:
                issues.append(Issue(
                    f, 0, "duplicate-number", WARNING,
                    f"Duplicate migration number {num} in app '{app}' — conflicts with {Path(seen[num]).name}"
                ))
            else:
                seen[num] = f
    return issues


def lint_directory(root, migrate_files=None):
    """Lint all migration files under a directory."""
    if migrate_files is None:
        migrate_files = find_migration_files(root)
    if not migrate_files:
        return [], []

    # First pass: parse all files
    parsed = {}
    for f in migrate_files:
        tree = _parse_migration(f)
        if tree is not None:
            parsed[f] = tree

    # Second pass: run rules
    all_issues = []
    for f in migrate_files:
        all_issues.extend(lint_file(f, parsed))

    # Duplicate numbers
    all_issues.extend(detect_duplicate_numbers(migrate_files))

    return all_issues, migrate_files


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_text_output(issues, scan_path, file_count):
    """Format issues as human-readable text."""
    lines = []
    lines.append(f"\U0001f50d migrate-lint: {scan_path}")
    lines.append("\u2501" * 40)
    lines.append("")

    counts = {ERROR: 0, WARNING: 0, INFO: 0}
    for issue in issues:
        counts[issue.severity] += 1

    if counts[ERROR]:
        lines.append(f"\U0001f534 ERRORS ({counts[ERROR]})")
        for issue in issues:
            if issue.severity == ERROR:
                lines.append(f"  {issue.filename}:{issue.line}")
                lines.append(f"    {issue.message}")
                lines.append("")

    if counts[WARNING]:
        lines.append(f"\U0001f7e1 WARNINGS ({counts[WARNING]})")
        for issue in issues:
            if issue.severity == WARNING:
                lines.append(f"  {issue.filename}:{issue.line}")
                lines.append(f"    {issue.message}")
                lines.append("")

    if counts[INFO]:
        lines.append(f"\u26aa INFO ({counts[INFO]})")
        for issue in issues:
            if issue.severity == INFO:
                lines.append(f"  {issue.filename}:{issue.line}")
                lines.append(f"    {issue.message}")
                lines.append("")

    lines.append(f"\U0001f4ca Summary: {file_count} migrations scanned. {counts[ERROR]} errors, {counts[WARNING]} warnings, {counts[INFO]} info.")
    lines.append("\U0001f4a1 Tip: Run `python manage.py sqlmigrate <app> <migration>` to see SQL for each operation")
    return "\n".join(lines)


def format_json_output(issues, scan_path, file_count):
    """Format issues as JSON."""
    data = {
        "scan_path": scan_path,
        "migrations_scanned": file_count,
        "errors": sum(1 for i in issues if i.severity == ERROR),
        "warnings": sum(1 for i in issues if i.severity == WARNING),
        "info": sum(1 for i in issues if i.severity == INFO),
        "issues": [i.to_dict() for i in issues],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Lint Django migrations for dangerous patterns before they hit production."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--path",
        help="Root directory to scan (default: current directory)"
    )
    group.add_argument(
        "--migrations",
        help="Explicit migrations directory to scan"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show detailed info for each issue")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 on warnings too")
    args = parser.parse_args()

    if args.migrations:
        scan_path = args.migrations
    elif args.path:
        scan_path = args.path
    else:
        scan_path = os.getcwd()

    if not Path(scan_path).is_dir():
        print(f"Error: {scan_path} is not a directory", file=sys.stderr)
        sys.exit(2)

    issues, files = lint_directory(scan_path)

    if args.json:
        print(format_json_output(issues, scan_path, len(files)))
    else:
        print(format_text_output(issues, scan_path, len(files)))

    has_errors = any(i.severity == ERROR for i in issues)
    has_warnings = any(i.severity == WARNING for i in issues)

    if has_errors:
        sys.exit(1)
    if args.strict and has_warnings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
