#!/usr/bin/env python3
"""Auto-generate Vim help docs from Vimscript and Lua plugin source."""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Function:
    name: str
    args: str = ""
    description: str = ""
    file: str = ""
    line: int = 0


@dataclass
class Command:
    name: str
    args_flag: str = ""
    description: str = ""
    file: str = ""
    line: int = 0


@dataclass
class Autocmd:
    event: str
    pattern: str = ""
    description: str = ""
    file: str = ""
    line: int = 0


@dataclass
class Option:
    name: str
    default: str = ""
    description: str = ""
    file: str = ""
    line: int = 0


@dataclass
class PluginDoc:
    name: str
    functions: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    autocmds: list = field(default_factory=list)
    options: list = field(default_factory=list)


def extract_comment_above(lines: list, target_line: int) -> str:
    """Extract comment lines above a given line number."""
    comments = []
    idx = target_line - 2
    while idx >= 0:
        line = lines[idx].rstrip()
        stripped = line.lstrip()
        if stripped.startswith('"'):
            comment_text = stripped[1:].strip()
            if comment_text.startswith("-"):
                comment_text = comment_text[1:].strip()
            comments.insert(0, comment_text)
        elif stripped.startswith("---") or stripped.startswith("--"):
            comment_text = stripped.lstrip("-").strip()
            comments.insert(0, comment_text)
        else:
            break
        idx -= 1
    return " ".join(comments).strip() if comments else ""


def parse_vimscript(filepath: str, doc: PluginDoc, verbose: bool = False):
    """Parse a .vim file for functions, commands, autocmds, and options."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    rel_path = os.path.basename(filepath)

    for i, line in enumerate(lines):
        stripped = line.strip()

        # function! Name(args) or function Name(args)
        func_match = re.match(r'^\s*function[!]\s+([\w#]+)\(([^)]*)\)', stripped)
        if func_match:
            name = func_match.group(1)
            args = func_match.group(2).strip()
            desc = extract_comment_above(lines, i + 1)
            doc.functions.append(Function(
                name=name, args=args, description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [func] {name}({args}) @ {rel_path}:{i+1}")
            continue

        # command! -nargs=N Name
        cmd_match = re.match(r'^\s*command[!]\s+(-nargs=\S+)\s+(\S+)', stripped)
        if cmd_match:
            args_flag = cmd_match.group(1)
            name = cmd_match.group(2)
            desc = extract_comment_above(lines, i + 1)
            doc.commands.append(Command(
                name=name, args_flag=args_flag, description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [cmd] {name} @ {rel_path}:{i+1}")
            continue

        # autocmd Event pattern
        autocmd_match = re.match(r'^\s*autocmd\s+(\S+)\s+(\S+)', stripped)
        if autocmd_match:
            event = autocmd_match.group(1)
            pattern = autocmd_match.group(2)
            desc = extract_comment_above(lines, i + 1)
            doc.autocmds.append(Autocmd(
                event=event, pattern=pattern, description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [autocmd] {event} {pattern} @ {rel_path}:{i+1}")
            continue

        # let g:plugin_option = value
        opt_match = re.match(r'^\s*let\s+g:(\w+)\s*=\s*(.*)', stripped)
        if opt_match:
            name = "g:" + opt_match.group(1)
            default = opt_match.group(2).strip()
            desc = extract_comment_above(lines, i + 1)
            doc.options.append(Option(
                name=name, default=default, description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [option] {name} = {default} @ {rel_path}:{i+1}")
            continue


def parse_lua(filepath: str, doc: PluginDoc, verbose: bool = False):
    """Parse a .lua file for functions, commands, autocmds, and options."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    rel_path = os.path.basename(filepath)

    for i, line in enumerate(lines):
        stripped = line.strip()

        # function M.name(args) or function module.name(args)
        func_match = re.match(r'^\s*function\s+(\w+)\.([\w.]+)\(([^)]*)\)', stripped)
        if func_match:
            module = func_match.group(1)
            name = func_match.group(2)
            args = func_match.group(3).strip()
            full_name = f"{module}.{name}"
            desc = extract_comment_above(lines, i + 1)
            doc.functions.append(Function(
                name=full_name, args=args, description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [func] {full_name}({args}) @ {rel_path}:{i+1}")
            continue

        # vim.api.nvim_create_user_command
        cmd_match = re.match(
            r'^\s*vim\.api\.nvim_create_user_command\s*\(\s*["\'](\w+)["\']',
            stripped
        )
        if cmd_match:
            name = cmd_match.group(1)
            desc = extract_comment_above(lines, i + 1)
            doc.commands.append(Command(
                name=name, args_flag="", description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [cmd] {name} @ {rel_path}:{i+1}")
            continue

        # vim.api.nvim_create_autocmd
        autocmd_match = re.match(
            r'^\s*vim\.api\.nvim_create_autocmd\s*\(\s*["\'](\w+)["\']',
            stripped
        )
        if autocmd_match:
            event = autocmd_match.group(1)
            desc = extract_comment_above(lines, i + 1)
            doc.autocmds.append(Autocmd(
                event=event, pattern="", description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [autocmd] {event} @ {rel_path}:{i+1}")
            continue

        # vim.g.variable_name = value
        opt_match = re.match(r'^\s*vim\.g\.(\w+)\s*=\s*(.*)', stripped)
        if opt_match:
            name = "g:" + opt_match.group(1)
            default = opt_match.group(2).strip()
            desc = extract_comment_above(lines, i + 1)
            doc.options.append(Option(
                name=name, default=default, description=desc,
                file=rel_path, line=i + 1
            ))
            if verbose:
                print(f"  [option] {name} = {default} @ {rel_path}:{i+1}")
            continue


def generate_vimdoc(doc: PluginDoc) -> str:
    """Generate vimdoc format documentation."""
    slug = doc.name.lower().replace(" ", "-")
    lines = []

    # Header
    lines.append(f"*{slug}.txt*    {doc.name} - Auto-generated documentation")
    lines.append("")
    lines.append("AUTHOR  Generated by vim-doc-gen")
    lines.append("LICENSE See plugin source")
    lines.append("")

    # Contents section
    sections = []
    if doc.commands:
        sections.append("Commands")
    if doc.functions:
        sections.append("Functions")
    if doc.autocmds:
        sections.append("Autocommands")
    if doc.options:
        sections.append("Configuration")

    lines.append("=" * 78)
    lines.append(f"CONTENTS                                         *{slug}-contents*")
    lines.append("")
    for idx, section in enumerate(sections, 1):
        num = f"{idx}."
        sec_slug = section.lower()
        dots = "." * (50 - len(f"{num} {section}"))
        lines.append(f"  {num} {section} {dots}|{slug}-{sec_slug}|")
    lines.append("")

    # Introduction
    lines.append("=" * 78)
    lines.append(f"1. Introduction                                *{slug}-introduction*")
    lines.append("")
    lines.append(f"{doc.name} plugin documentation.")
    lines.append("")

    section_num = 2

    # Commands
    if doc.commands:
        lines.append("=" * 78)
        lines.append(f"{section_num}. Commands                                    *{slug}-commands*")
        lines.append("")
        for cmd in doc.commands:
            lines.append(f":{cmd.name}                            *:{cmd.name}*")
            if cmd.description:
                lines.append(f"    {cmd.description}")
            if cmd.args_flag:
                lines.append(f"    Args: {cmd.args_flag}")
            lines.append("")
        section_num += 1

    # Functions
    if doc.functions:
        lines.append("=" * 78)
        lines.append(f"{section_num}. Functions                                   *{slug}-functions*")
        lines.append("")
        for func in doc.functions:
            args_display = func.args if func.args else ""
            if args_display:
                arg_list = [f"{{{a.strip()}}}" for a in args_display.split(",")]
                args_display = ", ".join(arg_list)
            sig = f"{func.name}({args_display})"
            lines.append(f"{sig:<45}*{func.name}()*")
            if func.description:
                lines.append(f"    {func.description}")
            lines.append("")
        section_num += 1

    # Autocommands
    if doc.autocmds:
        lines.append("=" * 78)
        lines.append(f"{section_num}. Autocommands                                *{slug}-autocommands*")
        lines.append("")
        for ac in doc.autocmds:
            label = f"{ac.event}"
            if ac.pattern:
                label += f" ({ac.pattern})"
            lines.append(f"{label:<45}*{ac.event}*")
            if ac.description:
                lines.append(f"    {ac.description}")
            lines.append("")
        section_num += 1

    # Configuration
    if doc.options:
        lines.append("=" * 78)
        lines.append(f"{section_num}. Configuration                               *{slug}-configuration*")
        lines.append("")
        for opt in doc.options:
            lines.append(f"{opt.name:<45}*{opt.name}*")
            if opt.default:
                lines.append(f"    Default: {opt.default}")
            if opt.description:
                lines.append(f"    {opt.description}")
            lines.append("")
        section_num += 1

    # Footer
    lines.append("=" * 78)
    lines.append(f"Generated by vim-doc-gen")
    lines.append(f"vim:tw=78:ts=8:ft=help:norl:")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Auto-generate Vim help docs from plugin source code."
    )
    parser.add_argument(
        "--path", required=True,
        help="Path to the Vim plugin directory to scan."
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path (default: doc/plugin-name.txt)."
    )
    parser.add_argument(
        "--plugin-name", "-n", default=None,
        help="Plugin name (default: derived from directory name)."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed parsing info."
    )
    args = parser.parse_args()

    plugin_path = Path(args.path).resolve()
    if not plugin_path.is_dir():
        print(f"Error: {plugin_path} is not a directory.", file=sys.stderr)
        sys.exit(1)

    plugin_name = args.plugin_name or plugin_path.name
    slug = plugin_name.lower().replace(" ", "-")

    if args.output:
        output_path = Path(args.output)
    else:
        doc_dir = plugin_path / "doc"
        doc_dir.mkdir(exist_ok=True)
        output_path = doc_dir / f"{slug}.txt"

    doc = PluginDoc(name=plugin_name)

    # Scan for .vim and .lua files
    vim_files = list(plugin_path.rglob("*.vim"))
    lua_files = list(plugin_path.rglob("*.lua"))

    if not vim_files and not lua_files:
        print(f"Error: No .vim or .lua files found in {plugin_path}.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Scanning {plugin_path}...")
        print(f"  Found {len(vim_files)} .vim files, {len(lua_files)} .lua files")

    for vf in vim_files:
        parse_vimscript(str(vf), doc, args.verbose)

    for lf in lua_files:
        parse_lua(str(lf), doc, args.verbose)

    content = generate_vimdoc(doc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    n_func = len(doc.functions)
    n_cmd = len(doc.commands)
    n_opt = len(doc.options)
    print(f"Generated {output_path} with {n_func} functions, {n_cmd} commands, {n_opt} options")


if __name__ == "__main__":
    main()
