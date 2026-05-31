#!/usr/bin/env python3
"""localization-extractor – Scan Luau scripts for hardcoded user-facing strings
and auto-generate localization tables for Roblox games."""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

ROBLOX_SERVICES = {
    "ServerScriptService", "ServerStorage", "ReplicatedStorage",
    "ReplicatedFirst", "StarterPack", "StarterPlayer", "StarterGui",
    "StarterCharacter", "Workspace", "Players", "Lighting", "SoundService",
    "TeleportService", "MarketplaceService", "DataStoreService",
    "HttpService", "InsertService", "Chat", "CollectionService",
    "ContextActionService", "RunService", "TweenService", "UserInputService",
    "BadgeService", "LogService", "PolicyService", "AnalyticsService",
    "SocialService", "AvatarEditorService", "GroupService",
    "PathfindingService", "ProximityPromptService", "TextService",
    "Debris", "Game", "script", "PluginManager",
}

FORMAT_PATTERN = re.compile(r"%[sdqixf]|\{[^}]*\}")

CATEGORY_KEYWORDS = {
    "GUI text": ["Text", "TextLabel", "TextButton", "Frame", "Label",
                 "Button", "Title", "Header", "Gui", "ScreenGui", "SurfaceGui"],
    "Notifications": ["Notification", "Alert", "Toast", "Prompt", "Popup",
                      "Warning", "Error", "Info", "Notify", "Hint"],
    "Game messages": ["Message", "Chat", "Say", "Announce", "Broadcast",
                      "SystemMessage", "GameMessage", "Status", "Event"],
    "Menu/UI": ["Menu", "Option", "Setting", "Dropdown", "Slider", "Toggle",
                "Tab", "Panel", "Page", "Navigation", "Sidebar", "Toolbar"],
}


def is_numeric(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def count_args(s):
    fmt = len(re.findall(r"%[sdqixf]", s))
    brace = len(re.findall(r"\{[^}]*\}", s))
    return fmt + brace


def guess_category(context):
    if not context:
        return "Game messages"
    ctx_lower = context.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in ctx_lower:
                return cat
    return "Game messages"


def generate_key(context, content, prefix, existing_keys):
    if context:
        parts = [p.strip().lower() for p in context.replace(":", ".").split(".") if p.strip()]
        keyed = False
        if len(parts) >= 2:
            candidate = "_".join(parts[-2:])
            keyed = True
        else:
            words = re.findall(r"[A-Z][a-z]*|[a-z]+", context)
            if len(words) >= 2:
                candidate = "_".join(w.lower() for w in words)
                keyed = True
            else:
                keyed = False
    else:
        keyed = False

    if not keyed:
        words = re.findall(r"[A-Za-z]+", content)
        candidate = "_".join(w.lower() for w in words)
        if not candidate:
            candidate = "str"

    candidate = re.sub(r"[^a-z0-9_]", "", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")

    if not candidate or len(candidate) < 2:
        candidate = prefix

    base = f"{prefix}_{candidate}" if not candidate.startswith(prefix) else candidate

    key = base
    n = 2
    while key in existing_keys:
        key = f"{base}_{n}"
        n += 1

    existing_keys.add(key)
    return key


def should_skip_source_line(line, pos, content):
    stripped = line.strip()

    if stripped.startswith("--"):
        return True

    if re.match(r"^\s*require\s*\(", stripped):
        return True

    if re.match(r"^\s*assert\s*\(", stripped) and not (
        " " in content or len(content.split()) > 1
    ):
        return True

    return False


def extract_strings(filepath, min_length, include_comments, verbose):
    results = []
    debug_seen = set()
    non_user_seen = set()

    try:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
    except Exception as e:
        if verbose:
            print(f"  ⚠ Skipped {filepath}: {e}", file=sys.stderr)
        return results

    filename = os.path.basename(filepath)
    content = raw

    if not include_comments:
        content = re.sub(r"--\[\[.*?\]\]", "", content, flags=re.DOTALL)
        content = re.sub(r"--\[=+\[.*?\]=+\]", "", content, flags=re.DOTALL)

    patterns = [
        (re.compile(r"\"((?:[^\"\\]|\\.)*)\""), '"'),
        (re.compile(r"'((?:[^'\\]|\\.)*)'"), "'"),
        (re.compile(r"\[=*\[(.*?)\]=*\]"), "[["),
    ]

    debug_calls = {"print", "warn", "warning", "error", "debug", "info", "log", "trace"}

    lines = content.split("\n")

    line_starts = [0]
    pos = 0
    for line in lines:
        pos += len(line) + 1
        line_starts.append(pos)

    def line_of(pos):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    seen_literals = set()

    for regex, _qtype in patterns:
        for m in regex.finditer(content):
            start, end = m.start(), m.end()
            raw_str = m.group(1)

            clean = raw_str
            if _qtype != "[[":
                try:
                    clean = re.sub(r"\\(.)", r"\1", raw_str)
                except Exception:
                    clean = raw_str

            if (start, end) in seen_literals:
                continue
            seen_literals.add((start, end))

            if not include_comments:
                pre = content[max(0, start - 5):start]
                if "--" in pre:
                    continue

            if len(clean) < min_length:
                continue

            if is_numeric(clean):
                continue

            if clean.strip() in ROBLOX_SERVICES:
                continue

            line_num = line_of(start)
            src_line = lines[line_num - 1] if line_num <= len(lines) else ""

            if should_skip_source_line(src_line, start, clean):
                continue

            is_debug = False
            is_non_user = False

            for dc in debug_calls:
                pat = re.compile(r"\b" + re.escape(dc) + r"\s*\(\s*" + re.escape(m.group(0)))
                if pat.search(src_line):
                    is_debug = True
                    break

            if not is_debug:
                for nuf in {"warn", "error", "assert"}:
                    pat = re.compile(r"\b" + re.escape(nuf) + r"\s*\(\s*" + re.escape(m.group(0)))
                    if pat.search(src_line):
                        is_non_user = True
                        break

            is_format = False
            concat_pattern = re.escape(m.group(0)) + r"\s*\.\."
            if re.search(concat_pattern, src_line):
                is_format = True

            if "string.format" in src_line and m.group(0) in src_line:
                is_format = True

            if FORMAT_PATTERN.search(clean):
                is_format = True

            context = ""
            context_match = re.search(
                r"([\w.]+)\s*=\s*" + re.escape(m.group(0)),
                src_line
            )
            if context_match:
                context = context_match.group(1)
            else:
                context_match = re.search(
                    r"([\w.]+)\s*\(\s*" + re.escape(m.group(0)),
                    src_line
                )
                if context_match:
                    context = context_match.group(1)

            if is_debug:
                debug_seen.add(clean)
                continue

            if is_non_user:
                non_user_seen.add(clean)
                continue

            results.append({
                "file": filename,
                "line": line_num,
                "original": clean,
                "context": context,
                "is_format": is_format,
                "is_debug": is_debug,
            })

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Scan Luau scripts for hardcoded user-facing strings and "
                    "generate localization tables."
    )
    parser.add_argument("--path", required=True,
                        help="Directory to scan for .lua/.luau files")
    parser.add_argument("--output", "-o", default="strings.csv",
                        help="Output file (default: strings.csv)")
    parser.add_argument("--format", choices=["csv", "json"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--key-prefix", default="str",
                        help="Prefix for auto-generated keys (default: str)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON report to stdout (alias for --format json)")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose output")
    parser.add_argument("--include-comments", action="store_true",
                        help="Include strings inside comments")
    parser.add_argument("--min-length", type=int, default=3,
                        help="Minimum string length (default: 3)")

    args = parser.parse_args()

    if args.json:
        args.format = "json"

    scan_path = os.path.abspath(args.path)
    if not os.path.isdir(scan_path):
        print(f"Error: --path '{args.path}' is not a directory", file=sys.stderr)
        sys.exit(1)

    luau_files = []
    for root, dirs, files in os.walk(scan_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith((".lua", ".luau")):
                luau_files.append(os.path.join(root, f))

    if not luau_files:
        print("No .lua or .luau files found in the specified path.")
        sys.exit(0)

    all_strings = []
    skipped_count = 0
    total_scanned = len(luau_files)

    for fp in luau_files:
        extracted = extract_strings(fp, args.min_length, args.include_comments, args.verbose)
        all_strings.extend(extracted)

    existing_keys = set()

    for entry in all_strings:
        entry["key"] = generate_key(
            entry["context"], entry["original"], args.key_prefix, existing_keys
        )

    category_counter = Counter()
    for entry in all_strings:
        cat = guess_category(entry["context"])
        entry["category"] = cat
        category_counter[cat] += 1

    fmt_count = sum(1 for e in all_strings if e["is_format"])
    total = len(all_strings)

    output_file = args.output
    if args.format == "csv":
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Key", "SourceFile", "Line", "OriginalString",
                             "Context", "ReplaceWith"])
            for entry in all_strings:
                if entry["is_format"]:
                    fmt_args = re.findall(r"\{(\w+)\}", entry["original"])
                    if fmt_args:
                        args_exprs = ", ".join(f"{a} = {a}" for a in fmt_args)
                        replace = f'localization:format("{entry["key"]}",{{{args_exprs}}})'
                    else:
                        replace = f'localization:format("{entry["key"]}")'
                else:
                    replace = f'localization:format("{entry["key"]}")'
                writer.writerow([
                    entry["key"],
                    entry["file"],
                    entry["line"],
                    f'"{entry["original"]}"',
                    entry["context"],
                    replace,
                ])

    elif args.format == "json":
        output_data = {
            "strings": [
                {
                    "key": e["key"],
                    "file": e["file"],
                    "line": e["line"],
                    "original": e["original"],
                    "context": e["context"],
                    "is_format": e["is_format"],
                    "category": e["category"],
                }
                for e in all_strings
            ],
            "source_language": "en",
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n🌐 Localization Extractor — {os.path.basename(scan_path)}\\\n"
          f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print(f"  📁 Scanned: {total_scanned} files\n")
    print(f"  📝 Extracted: {total} user-facing strings")
    print(f"  🗑️  Skipped: {skipped_count} (debug, paths, internal)")
    print(f"  🔤 Format strings: {fmt_count} (need runtime substitution)\n")

    if category_counter:
        print("  📊 By category:")
        for cat, cnt in sorted(category_counter.items()):
            pct = (cnt / total * 100) if total else 0
            print(f"     {cat}:".ljust(18) + f"{cnt} ({pct:.1f}%)")
        print()

    print(f"  📄 Generated: {output_file} ({total} entries)\n")
    print("  💡 Next steps:")
    print("     1. Translate strings.csv columns for each language")
    print("     2. Add LocalizationService to your game")
    print('     3. Replace hardcoded strings with localization:format(key)')
    print()


if __name__ == "__main__":
    main()
