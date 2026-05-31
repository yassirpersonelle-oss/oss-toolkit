#!/usr/bin/env python3
"""
Remote Event Logger — Security Audit Tool for Roblox/Luau Codebases

Scans a Luau codebase for all RemoteEvent, RemoteFunction, and
UnreliableRemoteEvent usage. Generates an attack surface report
highlighting potential exploit vectors.

Every RemoteEvent a client can fire (FireServer) is a potential
exploit surface. This tool finds and assesses them — quantifying
the risk of each entry point so you can harden your game.
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict, OrderedDict


# ═══════════════════════════════════════════════════════════════
#  Pattern Definitions
# ═══════════════════════════════════════════════════════════════

RE_NEW_EVENT = re.compile(
    r'(?:local\s+)?(\w+)\s*=\s*Instance\s*\.\s*new\s*\(\s*"'
    r'(RemoteEvent|RemoteFunction|UnreliableRemoteEvent)"'
    r'(?:\s*,\s*([^(,)]*(?:\([^)]*\)[^,)]*)*))?\s*\)',
    re.IGNORECASE,
)

RE_NEW_EVENT_TABLE = re.compile(
    r'(\w+)\s*\.\s*(\w+)\s*=\s*Instance\s*\.\s*new\s*\(\s*"'
    r'(RemoteEvent|RemoteFunction|UnreliableRemoteEvent)"'
    r'(?:\s*,\s*([^(,)]*(?:\([^)]*\)[^,)]*)*))?\s*\)',
    re.IGNORECASE,
)

RE_EVENT_CLASS_NEW = re.compile(
    r'(?:local\s+)?(\w+)\s*=\s*(RemoteEvent|RemoteFunction|UnreliableRemoteEvent)'
    r'\s*\.\s*new\s*\(',
    re.IGNORECASE,
)

RE_PARENT = re.compile(r'(\w+)\s*\.\s*Parent\s*=\s*([^\s\n\r;]+)', re.IGNORECASE)

RE_NAME = re.compile(r'(\w+)\s*\.\s*Name\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

RE_FIRE = re.compile(
    r'(\w+):(FireServer|FireClient|FireAllClients|InvokeServer|InvokeClient)\s*\(',
    re.IGNORECASE,
)

RE_FIRE_TABLE = re.compile(
    r'(\w+)\.(\w+):(FireServer|FireClient|FireAllClients|InvokeServer|InvokeClient)\s*\(',
    re.IGNORECASE,
)

RE_HANDLER = re.compile(
    r'(?:(\w+)\.)?(\w+)\.(OnServerEvent|OnClientEvent)\s*:\s*Connect\s*\(',
    re.IGNORECASE,
)

RE_INVOKE_HANDLER = re.compile(
    r'(?:(\w+)\.)?(\w+)\.(OnServerInvoke|OnClientInvoke)\s*=\s*',
    re.IGNORECASE,
)

VALIDATION_CHECKS = [
    (re.compile(r'typeof\s*\(', re.IGNORECASE), 'typeof()'),
    (re.compile(r'\bassert\s*\(', re.IGNORECASE), 'assert()'),
    (re.compile(r'if\s+not\s+\w+\s+then\s+return\b', re.IGNORECASE), 'nil-guard'),
    (re.compile(r'\bpcall\s*\(', re.IGNORECASE), 'pcall()'),
    (re.compile(r':IsA\s*\(', re.IGNORECASE), ':IsA()'),
    (re.compile(r'type\s*\([^)]+\)\s*[=~]=\s*["\']', re.IGNORECASE), 'type()'),
    (re.compile(r'if\s+\w+\s*==\s*nil\s+then\s+return', re.IGNORECASE), 'nil-check'),
    (re.compile(r':FindFirstChild\s*\(', re.IGNORECASE), 'FindFirstChild'),
]

RE_FUNC_DEF = re.compile(r'(?:local\s+)?function\s+(\w+)\s*\(')


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def strip_comments(text):
    """Strip Lua comments, preserving line count and string literals."""
    text = re.sub(r'--\[\[.*?\]\]', '', text, flags=re.DOTALL)
    lines = []
    for line in text.split('\n'):
        in_string = False
        string_char = None
        i = 0
        while i < len(line):
            if not in_string:
                if line[i:i+2] == '--':
                    break
                if line[i:i+2] == '[[':
                    i += 2
                    continue
                if line[i] in ('"', "'"):
                    in_string = True
                    string_char = line[i]
            else:
                if line[i] == '\\' and i + 1 < len(line):
                    i += 2
                    continue
                if line[i] == string_char:
                    in_string = False
            i += 1
        lines.append(line[:i])
    return '\n'.join(lines)


def extract_args(text, start):
    """Extract content between matching parentheses starting at `start`."""
    if start >= len(text) or text[start] != '(':
        return ''
    depth = 1
    buf = []
    for i in range(start + 1, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return ''.join(buf)
        if depth > 0:
            buf.append(text[i])
    return ''.join(buf)


def find_function_body(lines, func_name):
    """Locate a named function definition and return its body lines."""
    pattern = re.compile(
        r'(?:local\s+)?function\s+' + re.escape(func_name) + r'\s*\('
    )
    for i, line in enumerate(lines):
        if pattern.search(line):
            body = []
            depth = 1
            for j in range(i + 1, len(lines)):
                funcs = len(re.findall(r'\bfunction\b', lines[j]))
                ends = len(re.findall(r'\bend\b', lines[j]))
                depth += funcs - ends
                if depth <= 0:
                    break
                body.append(lines[j])
            return body
    return []


def get_inline_body(lines, start_line):
    """Extract body of anonymous function starting at start_line."""
    body = []
    depth = 0
    found = False
    for i in range(start_line, min(start_line + 100, len(lines))):
        line = lines[i]
        if not found:
            idx = line.find('function')
            if idx == -1:
                continue
            found = True
            depth = 1
            rest = line[idx:]
            paren_depth = 0
            body_start = 0
            for j, ch in enumerate(rest):
                if ch == '(':
                    paren_depth += 1
                elif ch == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        body_start = j + 1
                        break
            if body_start < len(rest):
                trailing = rest[body_start:].strip()
                if trailing:
                    body.append(trailing)
            depth += (rest[body_start:].count('function')
                      - rest[body_start:].count('end'))
            if depth <= 0:
                break
        else:
            funcs = line.count('function')
            ends = line.count('end')
            depth += funcs - ends
            if depth <= 0:
                break
            body.append(line)
    return body


def check_validation(body_lines):
    """Scan handler body for validation patterns."""
    text = '\n'.join(body_lines)
    found = []
    for pattern, label in VALIDATION_CHECKS:
        if pattern.search(text):
            found.append(label)
    return found


def classify_validation(checks):
    """Classify validation strength from found checks."""
    if not checks:
        return 'none'
    has_type = any(c in ('typeof()', ':IsA()', 'type()') for c in checks)
    has_guard = any(c in ('assert()', 'nil-guard', 'nil-check', 'pcall()')
                    for c in checks)
    if has_type and has_guard:
        return 'full'
    elif has_type or has_guard:
        return 'basic'
    return 'none'


# ═══════════════════════════════════════════════════════════════
#  File Scanner
# ═══════════════════════════════════════════════════════════════

def scan_file(filepath):
    """Parse one Lua(u) file and return a list of remote-event dicts."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            raw = f.read()
    except Exception:
        return []

    text = strip_comments(raw)
    lines = text.split('\n')

    events = OrderedDict()

    def ensure(key, name, etype, ln, tbl=None):
        if key not in events:
            events[key] = {
                'name': name,
                'event_type': etype,
                'file': str(filepath),
                'line': ln,
                'parent': None,
                'table': tbl,
                'fire_server': [],
                'fire_client': [],
                'fire_all': [],
                'invoke_server': [],
                'invoke_client': [],
                'server_handlers': [],
                'client_handlers': [],
                'validation': [],
                'validation_level': 'none',
            }

    # ── Pass 1: declarations ──

    for i, line in enumerate(lines):
        ln = i + 1

        for m in RE_NEW_EVENT.finditer(line):
            name, etype, parent_arg = m.group(1), m.group(2), m.group(3)
            ensure(name.lower(), name, etype, ln)
            if parent_arg:
                events[name.lower()]['parent'] = parent_arg.strip()

        for m in RE_NEW_EVENT_TABLE.finditer(line):
            tbl, name, etype, parent_arg = m.group(1), m.group(2), m.group(3), m.group(4)
            ensure(name.lower(), name, etype, ln, tbl)
            if parent_arg:
                events[name.lower()]['parent'] = parent_arg.strip()

        for m in RE_EVENT_CLASS_NEW.finditer(line):
            name, etype = m.group(1), m.group(2)
            ensure(name.lower(), name, etype, ln)

        for m in RE_PARENT.finditer(line):
            varname, container = m.group(1), m.group(2).strip().rstrip(',;')
            k = varname.lower()
            if k in events and not events[k]['parent']:
                events[k]['parent'] = container

    def add_call(key, field, call):
        """Append a call, avoiding duplicates (same line + same args)."""
        if key in events and field:
            existing = events[key][field]
            if not any(c['line'] == call['line'] and c['args'] == call['args']
                       for c in existing):
                existing.append(call)

    # ── Pass 2: fire / invoke calls ──

    METHOD_MAP = {
        'FireServer': 'fire_server',
        'FireClient': 'fire_client',
        'FireAllClients': 'fire_all',
        'InvokeServer': 'invoke_server',
        'InvokeClient': 'invoke_client',
    }

    for i, line in enumerate(lines):
        ln = i + 1

        for m in RE_FIRE_TABLE.finditer(line):
            tbl, name, method = m.group(1), m.group(2), m.group(3)
            key = name.lower()
            args = extract_args(line, m.end() - 1)
            call = {'args': args.strip(), 'line': ln, 'file': str(filepath),
                    'table': tbl}
            ensure(key, name, 'RemoteEvent', ln, tbl)
            add_call(key, METHOD_MAP.get(method), call)

        for m in RE_FIRE.finditer(line):
            varname, method = m.group(1), m.group(2)
            key = varname.lower()
            args = extract_args(line, m.end() - 1)
            call = {'args': args.strip(), 'line': ln, 'file': str(filepath)}
            ensure(key, varname, 'RemoteEvent', ln)
            add_call(key, METHOD_MAP.get(method), call)

    # ── Pass 3: handlers & validation ──

    for i, line in enumerate(lines):
        ln = i + 1

        for m in RE_HANDLER.finditer(line):
            tbl = m.group(1)
            varname = m.group(2)
            handler_type = m.group(3)
            key = varname.lower()
            if key not in events:
                continue

            handler_arg = extract_args(line, m.end() - 1)
            handler_name = handler_arg.strip()
            is_anon = handler_name.startswith('function')
            if is_anon:
                handler_name = '<anonymous>'

            info = {'name': handler_name, 'line': ln, 'table': tbl}

            if handler_type == 'OnServerEvent':
                events[key]['server_handlers'].append(info)
                if not events[key]['validation']:
                    body = (get_inline_body(lines, i)
                            if is_anon
                            else find_function_body(lines, handler_name))
                    checks = check_validation(body)
                    if checks:
                        events[key]['validation'] = checks
                        events[key]['validation_level'] = classify_validation(checks)
            else:
                events[key]['client_handlers'].append(info)

        for m in RE_INVOKE_HANDLER.finditer(line):
            tbl = m.group(1)
            varname = m.group(2)
            handler_type = m.group(3)
            key = varname.lower()
            if key not in events:
                continue

            rest = line[m.end():].strip().rstrip(';')
            handler_name = rest
            is_anon = handler_name.startswith('function')
            if is_anon:
                handler_name = '<anonymous>'

            info = {'name': handler_name, 'line': ln, 'table': tbl}

            if handler_type == 'OnServerInvoke':
                events[key]['server_handlers'].append(info)
                if not events[key]['validation']:
                    body = (get_inline_body(lines, i)
                            if is_anon
                            else find_function_body(lines, handler_name))
                    checks = check_validation(body)
                    if checks:
                        events[key]['validation'] = checks
                        events[key]['validation_level'] = classify_validation(checks)
            else:
                events[key]['client_handlers'].append(info)

    return list(events.values())


# ═══════════════════════════════════════════════════════════════
#  Risk Scoring
# ═══════════════════════════════════════════════════════════════

def score_event(event):
    has_c2s = (len(event['fire_server']) > 0
               or len(event['invoke_server']) > 0)
    has_handler = len(event['server_handlers']) > 0

    if has_c2s:
        v = event['validation_level']
        if v == 'none':
            return 'high'
        elif v == 'basic':
            return 'medium'
        else:
            return 'low'

    if has_handler:
        v = event['validation_level']
        if v == 'none':
            return 'high'
        elif v == 'basic':
            return 'medium'
        else:
            return 'low'

    return 'info'


# ═══════════════════════════════════════════════════════════════
#  Report Generators
# ═══════════════════════════════════════════════════════════════

def report_markdown(events, scan_path):
    out = []
    types = defaultdict(int)
    risks = defaultdict(int)
    scored = [(e, score_event(e)) for e in events]

    for e in events:
        types[e['event_type']] += 1
    for _, r in scored:
        risks[r] += 1

    remotes = types.get('RemoteEvent', 0)
    functions = types.get('RemoteFunction', 0)
    unreliables = types.get('UnreliableRemoteEvent', 0)

    out.append('# Remote Event Attack Surface')
    out.append('')
    out.append('| Category                | Count |')
    out.append('|-------------------------|-------|')
    out.append(f'| RemoteEvents            | {remotes} |')
    out.append(f'| RemoteFunctions         | {functions} |')
    out.append(f'| UnreliableRemoteEvents  | {unreliables} |')
    out.append(f'| **Total**               | **{len(events)}** |')
    out.append('')

    for level, emoji, label in [
        ('high', 'HIGH RISK', 'HIGH RISK'),
        ('medium', 'MEDIUM', 'MEDIUM'),
        ('low', 'LOW', 'LOW'),
        ('info', 'INFO', 'INFO'),
    ]:
        items = [(e, s) for e, s in scored if s == level]
        if not items:
            continue

        out.append(f'## {emoji} ({len(items)})')
        out.append('')

        for event, _ in items:
            parent = event['parent'] or 'unknown'
            out.append(f'**{event["name"]}** '
                       f'({event["event_type"]}) '
                       f'— `{parent}`')
            out.append(f'  - File: `{event["file"]}:{event["line"]}`')

            if event['fire_server']:
                out.append(f'  - **FireServer**: '
                           f'{len(event["fire_server"])} call(s)')
                for c in event['fire_server'][:3]:
                    a = c['args'][:60] if c['args'] else '(none)'
                    out.append(f'    - Line {c["line"]}: `:{a}`')

            if event['invoke_server']:
                out.append(f'  - **InvokeServer**: '
                           f'{len(event["invoke_server"])} call(s)')
                for c in event['invoke_server'][:3]:
                    a = c['args'][:60] if c['args'] else '(none)'
                    out.append(f'    - Line {c["line"]}: `:{a}`')

            if event['fire_client']:
                out.append(f'  - FireClient: '
                           f'{len(event["fire_client"])} call(s)')
            if event['fire_all']:
                out.append(f'  - FireAllClients: '
                           f'{len(event["fire_all"])} call(s)')

            if event['server_handlers']:
                handlers = ', '.join(
                    h['name'] for h in event['server_handlers']
                )
                out.append(f'  - Server handler(s): {handlers}')

            if event['validation']:
                out.append(f'  - Validation checks: '
                           f'{", ".join(event["validation"])}')
            elif event['server_handlers']:
                out.append(f'  - Validation checks: **NONE**')

            if level == 'high':
                out.append(f'  - Potential: '
                           f'client supplies arbitrary data — exploit vector')
            elif level == 'medium':
                out.append(f'  - Note: basic validation present, '
                           f'consider strengthening')

            out.append('')

    out.append('---')
    out.append('')

    high = risks.get('high', 0)
    if high > 0:
        out.append(f'## SUMMARY: {high} high-risk entry point(s) detected')
    else:
        out.append('## SUMMARY: No high-risk entry points detected')

    out.append('')
    out.append(f'*Generated by remote-event-logger*')

    return '\n'.join(out)


def report_text(events, scan_path):
    out = []
    types = defaultdict(int)
    risks = defaultdict(int)
    scored = [(e, score_event(e)) for e in events]

    for e in events:
        types[e['event_type']] += 1
    for _, r in scored:
        risks[r] += 1

    remotes = types.get('RemoteEvent', 0)
    functions = types.get('RemoteFunction', 0)
    unreliables = types.get('UnreliableRemoteEvent', 0)

    out.append(f'Remote Event Attack Surface -- {scan_path}')
    out.append('=' * 60)
    out.append(f'  Found: {remotes} RemoteEvents, '
               f'{functions} RemoteFunctions, '
               f'{unreliables} UnreliableRemoteEvents')
    out.append('')

    for level in ('high', 'medium', 'low', 'info'):
        items = [(e, s) for e, s in scored if s == level]
        if not items:
            continue
        out.append(f'[{level.upper()}] ({len(items)})')
        out.append('-' * 40)
        for event, _ in items:
            parent = event['parent'] or '?'
            out.append(f'  {event["name"]} '
                       f'({event["event_type"]}) '
                       f'@ {parent}')
            out.append(f'    {event["file"]}:{event["line"]}')
            if event['fire_server']:
                out.append(f'    FireServer: '
                           f'{len(event["fire_server"])} call(s)')
            if event['validation']:
                out.append(f'    Validation: '
                           f'{", ".join(event["validation"])}')
            elif event['server_handlers']:
                out.append(f'    Validation: NONE')
        out.append('')

    out.append('=' * 60)
    out.append(f'SUMMARY: {risks.get("high", 0)} high-risk entry points')
    return '\n'.join(out)


def report_json(events, scan_path):
    result = {
        'scan_path': scan_path,
        'total': len(events),
        'events': [],
        'summary': {},
    }
    types = defaultdict(int)
    risks = defaultdict(int)

    for e in events:
        types[e['event_type']] += 1
        s = score_event(e)
        risks[s] += 1
        result['events'].append({
            'name': e['name'],
            'type': e['event_type'],
            'file': e['file'],
            'line': e['line'],
            'parent': e['parent'],
            'table': e['table'],
            'fire_server': e['fire_server'],
            'fire_client': e['fire_client'],
            'fire_all_clients': e['fire_all'],
            'invoke_server': e['invoke_server'],
            'invoke_client': e['invoke_client'],
            'server_handlers': e['server_handlers'],
            'client_handlers': e['client_handlers'],
            'validation_checks': e['validation'],
            'validation_level': e['validation_level'],
            'risk': s,
        })

    result['summary'] = {
        'event_types': dict(types),
        'by_risk': dict(risks),
        'high_risk': risks.get('high', 0),
        'medium_risk': risks.get('medium', 0),
        'low_risk': risks.get('low', 0),
    }
    return json.dumps(result, indent=2)


def merge_events(raw_events):
    """Merge events with the same normalized name across files."""
    merged = OrderedDict()

    for e in raw_events:
        key = e['name'].lower()
        if key not in merged:
            merged[key] = dict(e)
            continue

        m = merged[key]

        if m['event_type'] == 'RemoteEvent' and e['event_type'] != 'RemoteEvent':
            m['event_type'] = e['event_type']

        if e['parent'] and not m['parent']:
            m['parent'] = e['parent']

        if e['table'] and not m['table']:
            m['table'] = e['table']

        for field in ('fire_server', 'fire_client', 'fire_all',
                       'invoke_server', 'invoke_client'):
            for call in e[field]:
                if not any(c['line'] == call['line'] and c['args'] == call['args']
                           for c in m[field]):
                    m[field].append(call)

        for h in e['server_handlers']:
            if not any(h2['line'] == h['line'] for h2 in m['server_handlers']):
                m['server_handlers'].append(h)

        for h in e['client_handlers']:
            if not any(h2['line'] == h['line'] for h2 in m['client_handlers']):
                m['client_handlers'].append(h)

        if e['validation_level'] == 'full':
            m['validation_level'] = 'full'
            m['validation'] = list(set(m['validation'] + e['validation']))
        elif e['validation_level'] == 'basic' and m['validation_level'] != 'full':
            m['validation_level'] = 'basic'
            m['validation'] = list(set(m['validation'] + e['validation']))
        elif e['validation'] and not m['validation']:
            m['validation'] = e['validation']
            m['validation_level'] = e['validation_level']

    return list(merged.values())


# ═══════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Remote Event Logger — Roblox/Luau attack surface audit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  remote-event-logger.py --path ./src
  remote-event-logger.py --path ./src --format json -o report.json
  remote-event-logger.py --path ./src --verbose
        ''',
    )
    parser.add_argument(
        '--path', required=True,
        help='Directory to scan for .lua / .luau files',
    )
    parser.add_argument(
        '--output', '-o', default=None,
        help='Write report to file (default: stdout)',
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Shortcut for --format json',
    )
    parser.add_argument(
        '--format', choices=('markdown', 'json', 'text'),
        default='markdown',
        help='Output format (default: markdown)',
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Print scan progress to stderr',
    )

    args = parser.parse_args()
    fmt = 'json' if args.json else args.format

    root = Path(args.path)
    if not root.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    lua_files = sorted(set(root.rglob('*.lua')))
    luau_files = sorted(set(root.rglob('*.luau')))
    all_files = list(dict.fromkeys(lua_files + luau_files))

    if args.verbose:
        print(f'Found {len(all_files)} Lua/Luau file(s) in {args.path}',
              file=sys.stderr)

    if not all_files:
        print(f"No .lua or .luau files found in '{args.path}'",
              file=sys.stderr)
        sys.exit(1)

    all_events = []
    for fp in all_files:
        if args.verbose:
            print(f'  Scanning: {fp}', file=sys.stderr)
        all_events.extend(scan_file(fp))

    all_events = merge_events(all_events)

    if args.verbose:
        types = defaultdict(int)
        for e in all_events:
            types[e['event_type']] += 1
        print(f'Found {len(all_events)} unique remote event(s): '
              f'{dict(types)}',
              file=sys.stderr)

    if fmt == 'json':
        report = report_json(all_events, args.path)
    elif fmt == 'text':
        report = report_text(all_events, args.path)
    else:
        report = report_markdown(all_events, args.path)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f'Report written to {args.output}', file=sys.stderr)
    else:
        print(report)


if __name__ == '__main__':
    main()
