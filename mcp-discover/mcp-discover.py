#!/usr/bin/env python3
"""MCP Discover - Turn any repo into an MCP server in one command.

Scans a codebase and auto-generates MCP (Model Context Protocol) server
configuration files from the project's functions and API endpoints.
Makes any OSS tool MCP-compatible without manual configuration.
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path


SKIP_DIRS = frozenset({
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    'dist', 'build', '.next', '.tox', '.egg-info', 'target',
    '.mypy_cache', '.pytest_cache', '.ruff_cache', '.vscode',
    '.idea', 'bower_components', 'vendor', '.gem', '.bundle',
    'site-packages', 'bin', 'lib', 'include', 'lib64',
})

PYTHON_TYPE_MAP = {
    'str': 'string', 'int': 'integer', 'float': 'number',
    'bool': 'boolean', 'list': 'array', 'dict': 'object',
    'tuple': 'array', 'set': 'array', 'bytes': 'string',
    'None': 'null', 'Any': 'string', 'Optional': 'string',
    'number': 'number', 'integer': 'integer', 'boolean': 'boolean',
    'string': 'string', 'object': 'object', 'array': 'array',
    'Union': 'string', 'Literal': 'string', 'Callable': 'string',
    'Iterable': 'array', 'Sequence': 'array', 'Mapping': 'object',
    'Path': 'string',
}


def should_skip(path: Path) -> bool:
    return any(part.startswith('.') or part in SKIP_DIRS for part in path.parts)


def _read_file(filepath: Path) -> str:
    try:
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ''


def count_source_files(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    ext_map = {
        '.py': 'python', '.js': 'javascript', '.mjs': 'javascript',
        '.cjs': 'javascript', '.ts': 'typescript', '.tsx': 'typescript',
        '.mts': 'typescript', '.cts': 'typescript', '.rs': 'rust', '.go': 'go',
    }
    for ext, lang in ext_map.items():
        files = [f for f in path.rglob(f'*{ext}') if not should_skip(f)]
        if files:
            counts[lang] = len(files)
    return counts


def detect_language(path: Path, force: str | None = None) -> str | None:
    if force:
        return force.lower()
    counts = count_source_files(path)
    if not counts:
        return None
    return max(counts, key=counts.get)


# ── AST helpers ──────────────────────────────────────────────────────────

def ast_type_to_str(annotation) -> str:
    if annotation is None:
        return 'any'
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Constant):
        return str(annotation.value)
    if isinstance(annotation, ast.Subscript):
        value = ast_type_to_str(annotation.value)
        slice_val = ast_type_to_str(annotation.slice)
        return f'{value}[{slice_val}]'
    if isinstance(annotation, ast.Attribute):
        return f'{ast_type_to_str(annotation.value)}.{annotation.attr}'
    if isinstance(annotation, ast.Tuple):
        return f'({", ".join(ast_type_to_str(e) for e in annotation.elts)})'
    if isinstance(annotation, ast.List):
        return f'[{", ".join(ast_type_to_str(e) for e in annotation.elts)}]'
    if isinstance(annotation, ast.BinOp):
        return f'{ast_type_to_str(annotation.left)} | {ast_type_to_str(annotation.right)}'
    return 'any'


def py_type_to_json_type(py_type: str) -> str:
    base = py_type.split('[')[0].split('(')[0].strip()
    return PYTHON_TYPE_MAP.get(base, 'string')


def get_decorator_name(decorator) -> str:
    if isinstance(decorator, ast.Call):
        return get_decorator_name(decorator.func)
    if isinstance(decorator, ast.Attribute):
        parent = get_decorator_name(decorator.value)
        return f'{parent}.{decorator.attr}' if parent else decorator.attr
    if isinstance(decorator, ast.Name):
        return decorator.id
    return ''


def is_route_or_command(decorator) -> bool:
    name = get_decorator_name(decorator)
    route_kw = {'route', 'get', 'post', 'put', 'delete', 'patch', 'head', 'options'}
    cmd_kw = {'command', 'group'}
    parts = name.split('.')
    last = parts[-1] if parts else ''
    return last in route_kw or last in cmd_kw


# ── Python discovery ────────────────────────────────────────────────────

def discover_python(filepath: Path) -> list[dict]:
    content = _read_file(filepath)
    if not content:
        return []
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError:
        return []

    functions = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func = {
            'name': node.name,
            'file': str(filepath),
            'line': node.lineno,
            'params': [],
            'docstring': (ast.get_docstring(node) or '').strip(),
            'is_route': False,
            'route_path': None,
            'route_method': None,
        }

        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and is_route_or_command(decorator):
                dname = get_decorator_name(decorator)
                func['is_route'] = True
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    func['route_path'] = str(decorator.args[0].value)
                parts = dname.split('.')
                method = parts[-1] if parts else ''
                if method in ('get', 'post', 'put', 'delete', 'patch', 'head', 'options'):
                    func['route_method'] = method.upper()
                elif method == 'route':
                    for kw in decorator.keywords:
                        if kw.arg == 'methods' and isinstance(kw.value, ast.List):
                            ms = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                            if ms:
                                func['route_method'] = ms[0]
                                break

        args = node.args
        defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults
        for i, arg in enumerate(args.args):
            if arg.arg in ('self', 'cls'):
                continue
            param = {'name': arg.arg, 'type': 'any', 'required': True, 'description': ''}
            if arg.annotation:
                param['type'] = py_type_to_json_type(ast_type_to_str(arg.annotation))
            if i < len(defaults) and defaults[i] is not None:
                param['required'] = False
            func['params'].append(param)

        functions.append(func)
    return functions


# ── JavaScript / TypeScript discovery ───────────────────────────────────

def _extract_jsdoc(content: str, pos: int) -> str:
    before = content[:pos].rstrip()
    match = re.search(r'/\*\*([^*]*(?:\*(?!/)[^*]*)*)\*/', before[::-1])
    if match:
        lines = match.group(1)[::-1].strip().split('\n')
        return ' '.join(l.strip().lstrip('*').strip() for l in lines)
    # line comment before
    line_match = re.search(r'(?:^|\n)\s*//\s*(.+)$', before, re.MULTILINE)
    if line_match:
        return line_match.group(1).strip()
    return ''


def _extract_js_params(sig: str) -> list[dict]:
    params = []
    depth = 0
    parts = []
    current = ''
    for ch in sig:
        if ch in '({[':
            depth += 1
            current += ch
        elif ch in ')}]':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip())
            current = ''
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    for p in parts:
        if not p or p == '...':
            continue
        is_rest = p.startswith('...')
        name = p.lstrip('.')
        ptype = 'any'
        if ':' in name:
            parts2 = name.split(':', 1)
            name = parts2[0].strip()
            raw_type = parts2[1].strip()
            ptype = 'array' if raw_type.startswith('[]') or raw_type.startswith('Array') else 'string'
        if '=' in name:
            name = name.split('=')[0].strip()
        params.append({'name': name.lstrip('.'), 'type': ptype, 'required': not is_rest and '?' not in name, 'description': ''})
    return params


def discover_javascript(filepath: Path) -> list[dict]:
    content = _read_file(filepath)
    if not content:
        return []
    functions = []

    patterns = [
        (r'export\s+(default\s+)?(async\s+)?function\s+(\w+)\s*\(([^)]*)\)', 3, 4),
        (r'exports\.(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)', 1, 2),
        (r'module\.exports\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)', None, 1),
        (r'export\s+const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', 1, 2),
        (r'(\w+)\s*:\s*(?:async\s+)?function\s*\(([^)]*)\)', 1, 2),
        (r'(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', 1, 2),
    ]

    # Route patterns (Express/Fastify)
    route_pattern = re.compile(r'(?:app|router|route)\.(get|post|put|delete|patch|all)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,')
    for m in route_pattern.finditer(content):
        method = m.group(1).upper()
        path_str = m.group(2)
        # Look ahead for handler function
        remainder = content[m.end():]
        handler_match = re.search(r'(?:async\s+)?(?:function\s+)?(\w+)\s*\(([^)]*)\)', remainder)
        if handler_match:
            name = f'{method}_{handler_match.group(1)}'
            sig = handler_match.group(2)
            func = {
                'name': name, 'file': str(filepath), 'line': content[:m.start()].count('\n') + 1,
                'params': _extract_js_params(sig), 'docstring': '', 'is_route': True,
                'route_path': path_str, 'route_method': method,
            }
            functions.append(func)

    for pattern, name_idx, sig_idx in patterns:
        for m in re.finditer(pattern, content, re.MULTILINE):
            name = m.group(name_idx) if name_idx else 'handler'
            sig = m.group(sig_idx) if sig_idx else ''
            line = content[:m.start()].count('\n') + 1
            doc = _extract_jsdoc(content, m.start())
            func = {
                'name': name, 'file': str(filepath), 'line': line,
                'params': _extract_js_params(sig), 'docstring': doc,
                'is_route': False, 'route_path': None, 'route_method': None,
            }
            functions.append(func)

    return functions


discover_typescript = discover_javascript


# ── Rust discovery ──────────────────────────────────────────────────────

def _parse_rust_type(ty: str) -> str:
    ty = ty.strip().rstrip(',').rstrip(')').strip()
    if ty in ('&str', 'String', '&String', '&mut str'):
        return 'string'
    if ty in ('i32', 'i64', 'u32', 'u64', 'usize', 'isize', 'f32', 'f64', 'i8', 'u8'):
        return 'number'
    if ty == 'bool':
        return 'boolean'
    if ty.startswith('Vec<') or ty.startswith('&[原地]') or ty.startswith('['):
        return 'array'
    if ty == '()' or ty == 'Result' or ty.startswith('Result<') or ty.startswith('Option<') or ty.startswith('Option<'):
        return 'string'
    if ty.startswith('HashMap<') or ty.startswith('BTreeMap<') or ty.startswith('Map<'):
        return 'object'
    return 'string'


def discover_rust(filepath: Path) -> list[dict]:
    content = _read_file(filepath)
    if not content:
        return []
    functions = []
    fn_pattern = re.compile(
        r'#?\[.*?\]\s*\n\s*)?'  # optional attribute
        r'pub\s+(unsafe\s+)?(async\s+)?fn\s+(\w+)\s*'
        r'(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?:->\s*([^{]+))?\s*\{',
        re.DOTALL,
    )
    # Simpler approach
    for m in re.finditer(r'pub\s+(unsafe\s+)?(async\s+)?fn\s+(\w+)\s*\(([^)]*)\)', content):
        name = m.group(3)
        sig = m.group(4)
        line = content[:m.start()].count('\n') + 1
        params = []
        for p in sig.split(','):
            p = p.strip()
            if not p or p == 'self':
                continue
            parts = p.rsplit(':', 1)
            pname = parts[0].strip()
            ptype = _parse_rust_type(parts[1]) if len(parts) > 1 else 'string'
            pname = pname.split()[-1]  # handle `mut name`
            params.append({'name': pname, 'type': ptype, 'required': True, 'description': ''})
        doc = ''
        doc_match = re.search(r'///\s*(.+)$', content[max(0, m.start() - 500):m.start()], re.MULTILINE)
        if doc_match:
            doc = doc_match.group(1).strip()
        functions.append({
            'name': name, 'file': str(filepath), 'line': line,
            'params': params, 'docstring': doc,
            'is_route': False, 'route_path': None, 'route_method': None,
        })
    return functions


# ── Go discovery ────────────────────────────────────────────────────────

def _parse_go_type(ty: str) -> str:
    ty = ty.strip()
    if ty.startswith('[]') or ty.startswith('['):
        return 'array'
    if ty.startswith('map[') or ty.startswith('*'):
        return 'object'
    if ty in ('string', 'error', 'rune', 'byte'):
        return 'string'
    if ty in ('int', 'int8', 'int16', 'int32', 'int64', 'uint', 'uint8', 'uint16', 'uint32', 'uint64', 'float32', 'float64', 'float'):
        return 'number'
    if ty == 'bool':
        return 'boolean'
    if ty.startswith('func('):
        return 'string'
    return 'string'


def discover_go(filepath: Path) -> list[dict]:
    content = _read_file(filepath)
    if not content:
        return []
    functions = []
    # Exported functions: func FunctionName(...) ...
    for m in re.finditer(r'func\s+(?:\([^)]*\)\s+)?([A-Z]\w*)\s*\(([^)]*)\)\s*(?:\(?\s*[^)]*\s*\)?)?\s*\{', content):
        name = m.group(1)
        sig = m.group(2)
        line = content[:m.start()].count('\n') + 1
        params = []
        for p in sig.split(','):
            p = p.strip()
            if not p:
                continue
            # Go params: name type or type (if no name)
            parts = p.rsplit(' ', 1)
            if len(parts) == 2:
                pname, ptype = parts
            else:
                pname, ptype = parts[0], 'string'
            if pname in ('ctx', 'context'):
                continue
            # Handle multiple names: a, b, c int
            for n in pname.split(','):
                n = n.strip()
                if n:
                    params.append({'name': n, 'type': _parse_go_type(ptype), 'required': True, 'description': ''})
        doc = ''
        doc_match = re.search(r'//\s*(.+)$', content[max(0, m.start() - 1000):m.start()], re.MULTILINE)
        if doc_match:
            doc = doc_match.group(1).strip()
        functions.append({
            'name': name, 'file': str(filepath), 'line': line,
            'params': params, 'docstring': doc,
            'is_route': False, 'route_path': None, 'route_method': None,
        })
    return functions


# ── Discovery router ────────────────────────────────────────────────────

DISCOVERY = {
    'python': discover_python,
    'javascript': discover_javascript,
    'typescript': discover_typescript,
    'rust': discover_rust,
    'go': discover_go,
}

FILE_EXT_MAP = {
    '.py': 'python', '.js': 'javascript', '.mjs': 'javascript',
    '.cjs': 'javascript', '.ts': 'typescript', '.tsx': 'typescript',
    '.mts': 'typescript', '.cts': 'typescript', '.rs': 'rust', '.go': 'go',
}

LANGUAGE_NAMES = {
    'python': 'Python', 'javascript': 'JavaScript', 'typescript': 'TypeScript',
    'rust': 'Rust', 'go': 'Go',
}


def discover(path: Path, lang: str) -> list[dict]:
    all_funcs = []
    seen_files = set()
    discover_fn = DISCOVERY.get(lang)
    if not discover_fn:
        return []

    exts = {ext for ext, l in FILE_EXT_MAP.items() if l == lang}
    for ext in exts:
        for filepath in path.rglob(f'*{ext}'):
            if should_skip(filepath):
                continue
            if filepath in seen_files:
                continue
            seen_files.add(filepath)
            try:
                funcs = discover_fn(filepath)
                all_funcs.extend(funcs)
            except Exception:
                continue
    return all_funcs


# ── Config generation ──────────────────────────────────────────────────

def make_command(lang: str, project_name: str, project_root: Path) -> tuple[str, list[str]]:
    if lang == 'python':
        main_py = project_root / 'main.py'
        init_py = project_root / '__init__.py'
        main_module = project_root / '__main__.py'
        if main_module.exists() or init_py.exists():
            return ('python', ['-m', project_name.replace('-', '_')])
        if main_py.exists():
            return ('python', [str(main_py)])
        py_files = [f for f in project_root.glob('*.py') if not should_skip(f)]
        if py_files:
            return ('python', [str(py_files[0])])
        return ('python', ['-m', project_name.replace('-', '_')])
    if lang in ('javascript', 'typescript'):
        entry = 'index.ts' if lang == 'typescript' and (project_root / 'index.ts').exists() else 'index.js'
        if (project_root / entry).exists():
            return ('npx' if lang == 'typescript' else 'node', [f'--loader tsx' if lang == 'typescript' else entry])
        if lang == 'javascript':
            js_files = [f for f in project_root.glob('*.js') if not should_skip(f)]
            if js_files:
                return ('node', [str(js_files[0])])
        return ('npx' if lang == 'typescript' else 'node', [f'-m {project_name}' if lang == 'typescript' else entry])
    if lang == 'rust':
        return ('cargo', ['run'])
    if lang == 'go':
        return ('go', ['run', '.'])
    return ('python', [])


def type_to_schema(param: dict, param_name: str) -> dict:
    schema = {'type': param['type'], 'description': param.get('description', '')}
    return schema


def generate_mcp_config(project_name: str, functions: list[dict], lang: str, project_root: Path) -> dict:
    command, args = make_command(lang, project_name, project_root)
    tools = []
    for func in functions:
        properties = {}
        required = []
        for param in func['params']:
            properties[param['name']] = type_to_schema(param, param['name'])
            if param['required']:
                required.append(param['name'])

        desc = func['docstring']
        if not desc and func.get('is_route'):
            desc = f"{func.get('route_method', 'GET')} {func.get('route_path', '/')}"
        if not desc:
            desc = f"Auto-discovered function from {Path(func['file']).name}"

        tools.append({
            'name': func['name'],
            'description': desc,
            'inputSchema': {
                'type': 'object',
                'properties': properties,
                'required': required,
            },
        })

    return {
        'mcpServers': {
            project_name: {
                'command': command,
                'args': args,
                'env': {},
                'disabled': False,
                'autoApprove': [],
                'tools': tools,
            },
        },
    }


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Scan a codebase and generate MCP server config from discovered functions/endpoints.',
    )
    parser.add_argument('--path', default='.', help='Project root directory (default: current dir)')
    parser.add_argument('--output', '-o', default='.mcp/', help='Output directory (default: .mcp/)')
    parser.add_argument('--name', help='MCP server name (default: project directory basename)')
    parser.add_argument('--lang', '--language', dest='language', help='Force language (python, javascript, typescript, rust, go)')
    parser.add_argument('--stdout', action='store_true', help='Print JSON to stdout instead of writing files')

    args = parser.parse_args()

    project_root = Path(args.path).resolve()
    if not project_root.is_dir():
        print(f'Error: {args.path} is not a valid directory', file=sys.stderr)
        sys.exit(1)

    project_name = args.name or project_root.name
    lang = detect_language(project_root, args.language)

    if not lang:
        print('No supported source files found.', file=sys.stderr)
        sys.exit(1)

    print(f'🔍 Discovering {LANGUAGE_NAMES.get(lang, lang)} functions in {project_root}...', file=sys.stderr)
    functions = discover(project_root, lang)

    if not functions:
        print('No discoverable functions found.', file=sys.stderr)
        sys.exit(0)

    files_used = len({f['file'] for f in functions})
    print(f'📦 Found {len(functions)} functions across {files_used} files.', file=sys.stderr)

    config = generate_mcp_config(project_name, functions, lang, project_root)
    tool_count = len(config['mcpServers'][project_name]['tools'])

    if args.stdout:
        print(json.dumps(config, indent=2))
    else:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = project_root / args.output
        output_dir = output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        mcp_path = output_dir / 'mcp.json'
        with open(mcp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f'✅  Wrote {mcp_path}', file=sys.stderr)

        tools_dir = output_dir / 'tools'
        tools_dir.mkdir(parents=True, exist_ok=True)
        for tool in config['mcpServers'][project_name]['tools']:
            tool_path = tools_dir / f"{tool['name']}.json"
            with open(tool_path, 'w', encoding='utf-8') as f:
                json.dump(tool, f, indent=2)

        print(f'✅  Wrote {tool_count} tool definitions to {tools_dir}/', file=sys.stderr)

    print(f'\n📊 Summary: Discovered {len(functions)} functions across {files_used} files. '
          f'Generated MCP config with {tool_count} tools.', file=sys.stderr)


if __name__ == '__main__':
    main()
