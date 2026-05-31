#!/usr/bin/env python3
import os
import sys
import re
import mimetypes

SPDX_HEADERS = {
    'MIT': 'SPDX-License-Identifier: MIT',
    'Apache-2.0': 'SPDX-License-Identifier: Apache-2.0',
    'GPL-3.0': 'SPDX-License-Identifier: GPL-3.0-only',
    'BSD-3-Clause': 'SPDX-License-Identifier: BSD-3-Clause',
}

COMMENT_STYLES = {
    'hash': ['.py', '.rb', '.sh', '.bash', '.zsh', '.yaml', '.yml', '.dockerfile', '.ini', '.cfg', '.toml'],
    'slash': ['.js', '.ts', '.jsx', '.tsx', '.rs', '.go', '.java', '.c', '.cpp', '.h', '.hpp', '.swift', '.kt', '.dart', '.zig'],
    'block': ['.css', '.scss', '.less'],
    'dash': ['.lua'],
    'double_dash': ['.sql'],
}

SKIP_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', '.gitignore', '.gitattributes',
}

SKIP_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.woff', '.woff2', '.eot', '.ttf', '.otf',
                   '.pdf', '.zip', '.tar', '.gz', '.bz2', '.xz', '.bin', '.exe', '.dll', '.so', '.dylib',
                   '.min.js', '.min.css', '.map'}

SPDX_RE = re.compile(r'SPDX-License-Identifier:\s*\S+')


def get_comment_style(filepath):
    _, ext = os.path.splitext(filepath)
    if filepath.endswith('.min.js') or filepath.endswith('.min.css'):
        return None
    if ext in COMMENT_STYLES['hash']:
        return ('# ', None)
    if ext in COMMENT_STYLES['slash']:
        return ('// ', None)
    if ext in COMMENT_STYLES['block']:
        return ('/* ', ' */')
    if ext in COMMENT_STYLES['dash']:
        return ('-- ', None)
    if ext in COMMENT_STYLES['double_dash']:
        return ('-- ', None)
    return None


def is_binary(filepath):
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
            return b'\0' in chunk
    except Exception:
        return True


def has_spdx_header(content):
    return bool(SPDX_RE.search(content))


def build_header(license_type, year, author, comment_start, comment_end):
    spdx = SPDX_HEADERS.get(license_type, SPDX_HEADERS['MIT'])
    lines = []
    if comment_end:
        lines.append(f'{comment_start}{spdx}{comment_end}')
        lines.append(f'{comment_start}Copyright (c) {year} {author}{comment_end}')
    else:
        lines.append(f'{comment_start}{spdx}')
        lines.append(f'{comment_start}Copyright (c) {year} {author}')
    return lines


def process_file(filepath, license_type, year, author):
    basename = os.path.basename(filepath)
    if basename in SKIP_FILES:
        return 'skip_unsupported'
    _, ext = os.path.splitext(filepath)
    if ext in SKIP_EXTENSIONS:
        return 'skip_unsupported'
    if filepath.endswith('.min.js') or filepath.endswith('.min.css'):
        return 'skip_unsupported'
    if is_binary(filepath):
        return 'skip_unsupported'

    style = get_comment_style(filepath)
    if style is None:
        return 'skip_unsupported'

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return 'skip_unsupported'

    if has_spdx_header(content):
        return 'skip_existing'

    comment_start, comment_end = style
    header_lines = build_header(license_type, year, author, comment_start, comment_end)

    new_content = '\n'.join(header_lines) + '\n\n' + content

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return 'added'


def find_new_files(base='.'):
    try:
        result = os.popen(f'git diff --name-only --diff-filter=A HEAD 2>/dev/null || git diff --name-only --cached 2>/dev/null || true').read()
        files = [f.strip() for f in result.split('\n') if f.strip()]
        if files:
            return files
    except Exception:
        pass

    all_files = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', 'venv', '.venv')]
        for f in files:
            filepath = os.path.join(root, f)
            all_files.append(os.path.relpath(filepath, base))
    return all_files


def main():
    if len(sys.argv) < 3:
        print("Usage: license_bot.py <license_type> <year> <author>", file=sys.stderr)
        sys.exit(1)

    license_type = sys.argv[1]
    year = sys.argv[2]
    author = sys.argv[3] if len(sys.argv) > 3 else ''

    if license_type not in SPDX_HEADERS:
        print(f"Unsupported license: {license_type}", file=sys.stderr)
        sys.exit(1)

    files = [line.strip() for line in sys.stdin if line.strip()] if not sys.stdin.isatty() else find_new_files()

    if not files:
        print("No files to process")
        return

    added = 0
    skipped_existing = 0
    skipped_unsupported = 0

    for f in files:
        if not os.path.isfile(f):
            continue
        result = process_file(f, license_type, year, author)
        if result == 'added':
            added += 1
        elif result == 'skip_existing':
            skipped_existing += 1
        elif result == 'skip_unsupported':
            skipped_unsupported += 1

    print(f"Added {added} headers, skipped {skipped_existing} (already had), skipped {skipped_unsupported} (unsupported)")


if __name__ == '__main__':
    main()
