#!/usr/bin/env python3

import sys
import os
import re
import argparse


LANGUAGES = [
    {
        'name': 'Python',
        'aliases': ['python', 'py', 'python3'],
        'extensions': ['.py'],
        'single': ['#'],
        'multi': [('"""', '"""'), ("'''", "'''")],
        'debug': [
            re.compile(r'^print\s*\('),
            re.compile(r'^pprint\s*\('),
            re.compile(r'^breakpoint\s*\('),
            re.compile(r'^pdb\.set_trace\s*\('),
        ],
    },
    {
        'name': 'JavaScript/TypeScript',
        'aliases': ['javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx', 'node'],
        'extensions': ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'],
        'single': ['//'],
        'multi': [('/*', '*/')],
        'debug': [
            re.compile(r'^console\.(log|debug|warn|error|info|trace|assert|dir|table|time|timeEnd|count|group|groupEnd)\s*\('),
            re.compile(r'^debugger\s*;?\s*$'),
            re.compile(r'^alert\s*\('),
        ],
    },
    {
        'name': 'Rust',
        'aliases': ['rust', 'rs'],
        'extensions': ['.rs'],
        'single': ['//'],
        'multi': [('/*', '*/')],
        'debug': [
            re.compile(r'^(println|print|eprintln|eprint|dbg)\s*!?\s*\('),
        ],
    },
    {
        'name': 'Go',
        'aliases': ['go', 'golang'],
        'extensions': ['.go'],
        'single': ['//'],
        'multi': [('/*', '*/')],
        'debug': [
            re.compile(r'^(fmt\.)?(Println|Print|Printf|Sprintf|Fprintln|Fprint|Fprintf)\s*\('),
        ],
    },
    {
        'name': 'Java',
        'aliases': ['java'],
        'extensions': ['.java', '.class', '.jar'],
        'single': ['//'],
        'multi': [('/*', '*/')],
        'debug': [
            re.compile(r'^System\.(out|err)\.(println|print|printf)\s*\('),
        ],
    },
    {
        'name': 'C/C++',
        'aliases': ['c', 'cpp', 'cc', 'cxx', 'h', 'hpp', 'c++'],
        'extensions': ['.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx'],
        'single': ['//'],
        'multi': [('/*', '*/')],
        'debug': [
            re.compile(r'^(printf|puts|fprintf|sprintf|snprintf|println|std::cout|std::cerr|std::clog)(\s*|\s*<<|\s*\()'),
        ],
    },
    {
        'name': 'HTML',
        'aliases': ['html', 'htm', 'xhtml'],
        'extensions': ['.html', '.htm', '.xhtml'],
        'single': [],
        'multi': [('<!--', '-->')],
        'debug': [],
    },
    {
        'name': 'CSS',
        'aliases': ['css'],
        'extensions': ['.css', '.scss', '.less', '.sass'],
        'single': [],
        'multi': [('/*', '*/')],
        'debug': [],
    },
    {
        'name': 'Shell/Bash',
        'aliases': ['sh', 'bash', 'shell', 'zsh', 'ksh', 'fish', 'posix'],
        'extensions': ['.sh', '.bash', '.zsh', '.ksh', '.fish'],
        'single': ['#'],
        'multi': [],
        'debug': [
            re.compile(r'^\s*echo\s'),
            re.compile(r'^\s*printf\s'),
            re.compile(r'^\s*print\s'),
        ],
    },
    {
        'name': 'YAML',
        'aliases': ['yaml', 'yml'],
        'extensions': ['.yaml', '.yml'],
        'single': ['#'],
        'multi': [],
        'debug': [],
    },
    {
        'name': 'Ruby',
        'aliases': ['ruby', 'rb'],
        'extensions': ['.rb', '.ruby'],
        'single': ['#'],
        'multi': [('=begin', '=end')],
        'debug': [
            re.compile(r'^puts\s'),
            re.compile(r'^print\s'),
            re.compile(r'^p\s'),
            re.compile(r'^pp\s'),
            re.compile(r'^byebug\s*$'),
            re.compile(r'^binding\.pry\s*$'),
        ],
    },
    {
        'name': 'PHP',
        'aliases': ['php', 'phtml', 'php3', 'php4', 'php5', 'php7', 'php8'],
        'extensions': ['.php', '.phtml', '.php3', '.php4', '.php5', '.php7', '.php8'],
        'single': ['//', '#'],
        'multi': [('/*', '*/')],
        'debug': [
            re.compile(r'^\s*(echo|print)\s'),
            re.compile(r'^var_dump\s*\('),
            re.compile(r'^print_r\s*\('),
            re.compile(r'^var_export\s*\('),
        ],
    },
]


_EXT_MAP = {}
_ALIAS_MAP = {}
for lang in LANGUAGES:
    for ext in lang['extensions']:
        _EXT_MAP[ext] = lang
    for alias in lang['aliases']:
        _ALIAS_MAP[alias] = lang


def detect_language(filepath, lang_arg=None):
    if lang_arg:
        key = lang_arg.lower()
        if key in _ALIAS_MAP:
            return _ALIAS_MAP[key]
        print(f'Error: unsupported language "{lang_arg}"', file=sys.stderr)
        print('Supported languages:', ', '.join(sorted(set(l['name'] for l in LANGUAGES))), file=sys.stderr)
        sys.exit(1)
    if filepath:
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()
        if ext in _EXT_MAP:
            return _EXT_MAP[ext]
        print(f'Error: unsupported file extension "{ext}"', file=sys.stderr)
        print('Use --lang to force language detection.', file=sys.stderr)
        sys.exit(1)
    print('Error: must specify --lang when reading from stdin', file=sys.stderr)
    sys.exit(1)


def _strip_multi_line(text, markers):
    for start, end in markers:
        pattern = re.escape(start) + r'[\s\S]*?' + re.escape(end)
        text = re.sub(pattern, '', text)
    return text


def _clean(text):
    lines = text.split('\n')
    lines = [line.rstrip() for line in lines]
    result = []
    blank = False
    for line in lines:
        if line == '':
            if not blank:
                result.append('')
                blank = True
        else:
            result.append(line)
            blank = False
    return '\n'.join(result)


def process_source(source, config, verbose=False):
    original_len = len(source)

    source = _strip_multi_line(source, config['multi'])

    lines = source.split('\n')
    output = []
    for line in lines:
        stripped = line.strip()
        if config['debug']:
            is_debug = any(p.match(stripped) for p in config['debug'])
            if is_debug:
                continue
        for marker in config['single']:
            idx = line.find(marker)
            if idx >= 0:
                line = line[:idx]
        output.append(line)

    source = '\n'.join(output)
    source = _clean(source)

    if verbose:
        new_len = len(source)
        removed = original_len - new_len
        tokens = int(removed * 0.75)
        pct = (1 - new_len / original_len) * 100 if original_len > 0 else 0
        print(f'Language: {config["name"]}', file=sys.stderr)
        print(f'Original: {original_len} chars', file=sys.stderr)
        print(f'Pristine: {new_len} chars', file=sys.stderr)
        print(f'Removed:  {removed} chars', file=sys.stderr)
        print(f'Saved:    ~{tokens} tokens', file=sys.stderr)
        print(f'Reduction: {pct:.1f}%', file=sys.stderr)

    return source


def main():
    parser = argparse.ArgumentParser(
        description='Strip comments, debug logs, and noise from source code.',
        epilog='Examples:\n'
               '  pristine.py file.py\n'
               '  cat file.js | pristine.py --lang javascript\n'
               '  pristine.py --verbose --lang rust < main.rs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('file', nargs='?', metavar='FILE',
                        help='Source file to process (reads from stdin if omitted)')
    parser.add_argument('--lang', '--language', dest='lang', metavar='LANG',
                        help='Force language (auto-detected from file extension)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show token savings statistics')
    args = parser.parse_args()

    config = detect_language(args.file, args.lang)

    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8', errors='replace') as f:
                source = f.read()
        except FileNotFoundError:
            print(f'Error: file not found: {args.file}', file=sys.stderr)
            sys.exit(1)
        except IsADirectoryError:
            print(f'Error: is a directory: {args.file}', file=sys.stderr)
            sys.exit(1)
        except PermissionError:
            print(f'Error: permission denied: {args.file}', file=sys.stderr)
            sys.exit(1)
    else:
        source = sys.stdin.read()

    result = process_source(source, config, args.verbose)
    sys.stdout.write(result)


if __name__ == '__main__':
    main()
