#!/usr/bin/env python3
"""MCP Discover - Turn any repo into an MCP server in one command.

Scans a codebase and auto-generates MCP (Model Context Protocol) server
configuration files from the project's functions and API endpoints.
Makes any OSS tool MCP-compatible without manual configuration.

Supports MCP, Claude Desktop, and Cursor output formats.
Can generate a working stdio MCP server wrapper.
"""

import argparse
import ast
import configparser
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
        with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
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


# ── Enhanced docstring parsing (UPGRADE 4) ──────────────────────────────

def _parse_python_docstring(docstring: str) -> dict:
    """Parse a Python docstring for :param:, :returns:, :raises:, @deprecated.

    Returns dict with keys: description, params, returns, raises, deprecated.
    """
    result = {
        'description': '',
        'params': {},
        'returns': '',
        'raises': [],
        'deprecated': False,
    }
    if not docstring:
        return result

    lines = docstring.strip().split('\n')
    desc_lines = []
    current_tag = None
    current_tag_name = None
    current_tag_lines = []

    for line in lines:
        stripped = line.strip()

        if '@deprecated' in stripped.lower() or 'deprecated' in stripped.lower() and '.. ' in stripped:
            result['deprecated'] = True

        param_m = re.match(r'^:(param|type|keyword|arg|ivar|cvar|var)\s+(\w+)\s*:\s*(.*)', stripped)
        if param_m:
            param_name = param_m.group(2)
            param_desc = param_m.group(3)
            if param_name not in result['params']:
                result['params'][param_name] = param_desc
            else:
                result['params'][param_name] += ' ' + param_desc
            continue

        return_m = re.match(r'^:returns?:\s*(.*)', stripped)
        if return_m:
            result['returns'] = return_m.group(1).strip()
            continue

        raise_m = re.match(r'^:raises?\s+(\w+)\s*:\s*(.*)', stripped)
        if raise_m:
            result['raises'].append({'type': raise_m.group(1), 'description': raise_m.group(2)})
            continue

        if re.match(r'^:deprecated\b', stripped, re.IGNORECASE):
            result['deprecated'] = True
            continue

        desc_lines.append(line)

    result['description'] = '\n'.join(desc_lines).strip()
    if not result['description']:
        result['description'] = docstring.strip().split('\n')[0].strip().rstrip('.')
    return result


def _parse_jsdoc_structured(docstring: str) -> dict:
    """Parse a JSDoc string for @param, @returns, @example, @deprecated.

    Returns dict with keys: description, params, returns, examples, deprecated.
    """
    result = {
        'description': '',
        'params': {},
        'returns': '',
        'examples': [],
        'deprecated': False,
    }
    if not docstring:
        return result

    desc_parts = []
    current_example_lines = []
    in_example = False

    lines = docstring.strip().split('\n')
    for line in lines:
        stripped = line.strip().lstrip('*').strip()

        if stripped.lower().startswith('@deprecated'):
            result['deprecated'] = True
            continue

        param_m = re.match(r'@param\s+(?:\{([^}]*)\}\s+)?(?:\[?(\w+)(?:=([^\]]*))?\]?)?\s*(?:-\s*)?(.*)', stripped)
        if param_m:
            ptype = param_m.group(1) or 'any'
            pname = param_m.group(2)
            pdesc = param_m.group(4) or ''
            if pname:
                result['params'][pname] = pdesc
            continue

        return_m = re.match(r'@returns?\s*(?:\{([^}]*)\}\s*)?(.*)', stripped)
        if return_m:
            result['returns'] = return_m.group(2) or ''
            continue

        example_m = re.match(r'@example\s*(.*)', stripped)
        if example_m:
            in_example = True
            example_text = example_m.group(1)
            if example_text:
                current_example_lines.append(example_text)
            continue

        if in_example:
            if stripped.startswith('@'):
                in_example = False
                if current_example_lines:
                    result['examples'].append('\n'.join(current_example_lines))
                    current_example_lines = []
            else:
                current_example_lines.append(stripped)
                continue

        if not stripped.startswith('@'):
            desc_parts.append(stripped)

    if in_example and current_example_lines:
        result['examples'].append('\n'.join(current_example_lines))

    result['description'] = ' '.join(desc_parts).strip()
    return result


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

        raw_doc = (ast.get_docstring(node) or '').strip()
        parsed_doc = _parse_python_docstring(raw_doc)

        func = {
            'name': node.name,
            'file': str(filepath),
            'line': node.lineno,
            'params': [],
            'docstring': parsed_doc['description'] or raw_doc,
            'is_route': False,
            'route_path': None,
            'route_method': None,
            'deprecated': parsed_doc['deprecated'],
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
            if arg.arg in parsed_doc['params']:
                param['description'] = parsed_doc['params'][arg.arg]
            func['params'].append(param)

        functions.append(func)
    return functions


# ── JavaScript / TypeScript discovery ───────────────────────────────────

def _extract_jsdoc(content: str, pos: int) -> str:
    """Extract JSDoc comment string preceding position pos. Returns raw text."""
    before = content[:pos].rstrip()
    match = re.search(r'/\*\*([^*]*(?:\*(?!/)[^*]*)*)\*/', before[::-1])
    if match:
        lines = match.group(1)[::-1].strip().split('\n')
        return ' '.join(l.strip().lstrip('*').strip() for l in lines)
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
        params.append({
            'name': name.lstrip('.'),
            'type': ptype,
            'required': not is_rest and '?' not in name,
            'description': '',
        })
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

    route_pattern = re.compile(
        r'(?:app|router|route)\.(get|post|put|delete|patch|all)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,',
    )
    for m in route_pattern.finditer(content):
        method = m.group(1).upper()
        path_str = m.group(2)
        remainder = content[m.end():]
        handler_match = re.search(r'(?:async\s+)?(?:function\s+)?(\w+)\s*\(([^)]*)\)', remainder)
        if handler_match:
            name = f'{method}_{handler_match.group(1)}'
            sig = handler_match.group(2)
            func = {
                'name': name,
                'file': str(filepath),
                'line': content[:m.start()].count('\n') + 1,
                'params': _extract_js_params(sig),
                'docstring': '',
                'is_route': True,
                'route_path': path_str,
                'route_method': method,
                'deprecated': False,
            }
            functions.append(func)

    for pattern, name_idx, sig_idx in patterns:
        for m in re.finditer(pattern, content, re.MULTILINE):
            name = m.group(name_idx) if name_idx else 'handler'
            sig = m.group(sig_idx) if sig_idx else ''
            line = content[:m.start()].count('\n') + 1
            raw_doc = _extract_jsdoc(content, m.start())
            parsed_doc = _parse_jsdoc_structured(raw_doc)
            params = _extract_js_params(sig)
            for param in params:
                if param['name'] in parsed_doc['params']:
                    param['description'] = parsed_doc['params'][param['name']]
            func = {
                'name': name,
                'file': str(filepath),
                'line': line,
                'params': params,
                'docstring': parsed_doc['description'] or raw_doc,
                'is_route': False,
                'route_path': None,
                'route_method': None,
                'deprecated': parsed_doc['deprecated'],
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
    if ty.startswith('Vec<') or ty.startswith('&[') or ty.startswith('['):
        return 'array'
    if ty == '()' or ty == 'Result' or ty.startswith('Result<') or ty.startswith('Option<'):
        return 'string'
    if ty.startswith('HashMap<') or ty.startswith('BTreeMap<') or ty.startswith('Map<'):
        return 'object'
    return 'string'


def _parse_rust_doc(docstring: str) -> dict:
    """Parse Rust doc comments for @deprecated."""
    result = {
        'description': docstring.strip(),
        'params': {},
        'returns': '',
        'deprecated': False,
    }
    if docstring:
        lower = docstring.lower()
        if 'deprecated' in lower:
            result['deprecated'] = True
    return result


def discover_rust(filepath: Path) -> list[dict]:
    content = _read_file(filepath)
    if not content:
        return []
    functions = []
    for m in re.finditer(
        r'pub\s+(unsafe\s+)?(async\s+)?fn\s+(\w+)\s*\(([^)]*)\)', content,
    ):
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
            pname = pname.split()[-1]
            params.append({
                'name': pname,
                'type': ptype,
                'required': True,
                'description': '',
            })
        doc = ''
        doc_match = re.search(
            r'///\s*(.+)$',
            content[max(0, m.start() - 500):m.start()],
            re.MULTILINE,
        )
        if doc_match:
            doc = doc_match.group(1).strip()
        parsed_doc = _parse_rust_doc(doc)
        functions.append({
            'name': name,
            'file': str(filepath),
            'line': line,
            'params': params,
            'docstring': parsed_doc['description'],
            'is_route': False,
            'route_path': None,
            'route_method': None,
            'deprecated': parsed_doc['deprecated'],
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
    if ty in (
        'int', 'int8', 'int16', 'int32', 'int64',
        'uint', 'uint8', 'uint16', 'uint32', 'uint64',
        'float32', 'float64', 'float',
    ):
        return 'number'
    if ty == 'bool':
        return 'boolean'
    if ty.startswith('func('):
        return 'string'
    return 'string'


def _parse_go_doc(docstring: str) -> dict:
    result = {
        'description': docstring.strip(),
        'params': {},
        'returns': '',
        'deprecated': False,
    }
    if docstring:
        lower = docstring.lower()
        if 'deprecated' in lower:
            result['deprecated'] = True
    return result


def discover_go(filepath: Path) -> list[dict]:
    content = _read_file(filepath)
    if not content:
        return []
    functions = []
    for m in re.finditer(
        r'func\s+(?:\([^)]*\)\s+)?([A-Z]\w*)\s*\(([^)]*)\)\s*(?:\(?\s*[^)]*\s*\)?)?\s*\{',
        content,
    ):
        name = m.group(1)
        sig = m.group(2)
        line = content[:m.start()].count('\n') + 1
        params = []
        for p in sig.split(','):
            p = p.strip()
            if not p:
                continue
            parts = p.rsplit(' ', 1)
            if len(parts) == 2:
                pname, ptype = parts
            else:
                pname, ptype = parts[0], 'string'
            if pname in ('ctx', 'context'):
                continue
            for n in pname.split(','):
                n = n.strip()
                if n:
                    params.append({
                        'name': n,
                        'type': _parse_go_type(ptype),
                        'required': True,
                        'description': '',
                    })
        doc = ''
        doc_match = re.search(
            r'//\s*(.+)$',
            content[max(0, m.start() - 1000):m.start()],
            re.MULTILINE,
        )
        if doc_match:
            doc = doc_match.group(1).strip()
        parsed_doc = _parse_go_doc(doc)
        functions.append({
            'name': name,
            'file': str(filepath),
            'line': line,
            'params': params,
            'docstring': parsed_doc['description'],
            'is_route': False,
            'route_path': None,
            'route_method': None,
            'deprecated': parsed_doc['deprecated'],
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
    'python': 'Python',
    'javascript': 'JavaScript',
    'typescript': 'TypeScript',
    'rust': 'Rust',
    'go': 'Go',
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


# ── UPGRADE 1: Auto-detect project entry points ─────────────────────────

def _parse_toml_simple(content: str) -> dict:
    """Minimal TOML parser for pyproject.toml / Cargo.toml sections."""
    result: dict = {}
    current_section: list[str] = []
    current_table: dict | None = None
    array_key: str | None = None
    array_vals: list = []

    for line in content.split('\n'):
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            continue

        section_match = re.match(r'^\[([^\]]+)\]', stripped)
        if section_match:
            if current_table is not None and array_key is not None:
                result.setdefault('.'.join(current_section), {}).setdefault(array_key, []).extend(array_vals)
                array_key = None
                array_vals = []
            if current_table is not None and current_table:
                result.setdefault('.'.join(current_section), {}).update(current_table)

            section_path = section_match.group(1).strip().strip('"').strip("'")
            current_section = section_path.split('.')
            current_table = {}
            array_key = None
            array_vals = []
            continue

        if stripped.startswith('[['):
            if current_table is not None and current_table:
                result.setdefault('.'.join(current_section), {}).update(current_table)

            array_match = re.match(r'^\[\[([^\]]+)\]\]', stripped)
            if array_match:
                section_path = array_match.group(1).strip().strip('"').strip("'")
                current_section = section_path.split('.')
                current_table = {}
                array_key = current_section[-1] if current_section else None
                current_section = current_section[:-1] if current_section else []
                array_vals = [{}]
                current_table = array_vals[-1]

            continue

        kv_match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*(.+)$', stripped)
        if kv_match and current_table is not None:
            key = kv_match.group(1).strip()
            val = kv_match.group(2).strip().strip('"').strip("'")
            current_table[key] = val
            continue

    if current_table is not None and current_table:
        if array_key is not None:
            result.setdefault('.'.join(current_section), {}).setdefault(array_key, []).extend(array_vals)
        else:
            section_data = result.setdefault('.'.join(current_section), {})
            if isinstance(section_data, list):
                section_data.append(current_table)
            else:
                section_data.update(current_table)

    return result


def detect_project_entry(project_root: Path, lang: str) -> dict:
    """Auto-detect project entry points from package/config files.

    Returns dict with keys: command, args, entry_file, description, module_path.
    """
    entry = {
        'command': None,
        'args': [],
        'entry_file': None,
        'description': '',
        'module_path': None,
    }

    if lang == 'python':
        pyproject_path = project_root / 'pyproject.toml'
        if pyproject_path.exists():
            content = _read_file(pyproject_path)
            parsed = _parse_toml_simple(content)

            scripts = parsed.get('project.scripts', {})
            console_scripts = parsed.get('project.entry-points.console_scripts', {})
            if isinstance(console_scripts, dict):
                scripts.update(console_scripts)

            if isinstance(scripts, dict) and scripts:
                first_name = next(iter(scripts))
                first_val = scripts[first_name]
                if isinstance(first_val, str) and ':' in first_val:
                    module_part = first_val.split(':')[0]
                    entry['command'] = 'python'
                    entry['args'] = ['-m', module_part]
                    entry['description'] = f'entry-point: {first_name}'
                    entry['module_path'] = module_part
                    return entry
                elif isinstance(first_val, str):
                    entry['command'] = 'python'
                    entry['args'] = [first_val]
                    entry['description'] = f'entry-point: {first_name}'
                    return entry

            project_scripts = parsed.get('project.scripts', {})
            if isinstance(project_scripts, dict) and project_scripts:
                first_name = next(iter(project_scripts))
                first_val = project_scripts[first_name]
                if isinstance(first_val, str) and ':' in first_val:
                    module_part = first_val.split(':')[0]
                    entry['command'] = 'python'
                    entry['args'] = ['-m', module_part]
                    entry['description'] = f'scripts: {first_name}'
                    entry['module_path'] = module_part
                    return entry

        setup_cfg = project_root / 'setup.cfg'
        if setup_cfg.exists():
            cfg_parser = configparser.ConfigParser()
            try:
                cfg_parser.read_string(_read_file(setup_cfg))
                if cfg_parser.has_section('options.entry_points'):
                    eps = dict(cfg_parser.items('options.entry_points'))
                    if 'console_scripts' in eps:
                        scripts_str = eps['console_scripts']
                        for script_line in scripts_str.strip().split('\n'):
                            script_line = script_line.strip()
                            if not script_line:
                                continue
                            eq_pos = script_line.find('=')
                            if eq_pos >= 0:
                                script_val = script_line[eq_pos + 1:].strip()
                                if ':' in script_val:
                                    module_part = script_val.split(':')[0]
                                    entry['command'] = 'python'
                                    entry['args'] = ['-m', module_part]
                                    entry['description'] = f'console_scripts: {script_line[:eq_pos].strip()}'
                                    entry['module_path'] = module_part
                                    return entry
            except Exception:
                pass

        for name in ('__main__.py', 'main.py', 'app.py', 'cli.py', 'run.py'):
            candidate = project_root / name
            if candidate.exists():
                entry['entry_file'] = str(candidate)
                entry['command'] = 'python'
                entry['args'] = [str(candidate)]
                entry['description'] = f'file: {name}'
                return entry

        py_files = sorted([
            f for f in project_root.glob('*.py')
            if not should_skip(f) and f.name != '__init__.py'
        ])
        if py_files:
            entry['entry_file'] = str(py_files[0])
            entry['command'] = 'python'
            entry['args'] = [str(py_files[0])]
            entry['description'] = f'file: {py_files[0].name}'
            return entry

        return entry

    elif lang in ('javascript', 'typescript'):
        package_json = project_root / 'package.json'
        if package_json.exists():
            try:
                pkg = json.loads(_read_file(package_json))
                if 'bin' in pkg:
                    bin_entry = pkg['bin']
                    if isinstance(bin_entry, dict):
                        first_bin = next(iter(bin_entry.values()))
                    else:
                        first_bin = bin_entry
                    if isinstance(first_bin, str):
                        entry['entry_file'] = str(project_root / first_bin)
                        if lang == 'typescript':
                            entry['command'] = 'npx'
                            entry['args'] = ['tsx', first_bin]
                        else:
                            entry['command'] = 'node'
                            entry['args'] = [first_bin]
                        entry['description'] = f'bin: {first_bin}'
                        return entry

                if 'main' in pkg:
                    main_file = pkg['main']
                    entry['entry_file'] = str(project_root / main_file)
                    if lang == 'typescript':
                        entry['command'] = 'npx'
                        entry['args'] = ['tsx', main_file]
                    else:
                        entry['command'] = 'node'
                        entry['args'] = [main_file]
                    entry['description'] = f'main: {main_file}'
                    return entry

                if 'exports' in pkg:
                    exports = pkg['exports']
                    export_val = None
                    if isinstance(exports, dict):
                        export_val = exports.get('.') or exports.get('./*') or next(iter(exports.values()), None)
                    elif isinstance(exports, str):
                        export_val = exports
                    if isinstance(export_val, dict):
                        export_val = export_val.get('import') or export_val.get('require')
                    if isinstance(export_val, str):
                        entry['entry_file'] = str(project_root / export_val)
                        if lang == 'typescript':
                            entry['command'] = 'npx'
                            entry['args'] = ['tsx', export_val]
                        else:
                            entry['command'] = 'node'
                            entry['args'] = [export_val]
                        entry['description'] = f'exports: {export_val}'
                        return entry
            except Exception:
                pass

        entry_name = 'index.ts' if lang == 'typescript' and (project_root / 'index.ts').exists() else 'index.js'
        if (project_root / entry_name).exists():
            entry['entry_file'] = str(project_root / entry_name)
            if lang == 'typescript':
                entry['command'] = 'npx'
                entry['args'] = ['tsx', entry_name]
            else:
                entry['command'] = 'node'
                entry['args'] = [entry_name]
            entry['description'] = f'file: {entry_name}'
            return entry

        return entry

    elif lang == 'rust':
        cargo_toml = project_root / 'Cargo.toml'
        if cargo_toml.exists():
            content = _read_file(cargo_toml)
            parsed = _parse_toml_simple(content)
            bins = parsed.get('bin', [])
            if isinstance(bins, list) and bins:
                first_bin = bins[0]
                if isinstance(first_bin, dict):
                    bin_name = first_bin.get('name', '')
                    bin_path = first_bin.get('path', '')
                    entry['description'] = f'bin: {bin_name}' if bin_name else 'binary'
                elif isinstance(first_bin, str):
                    entry['description'] = f'bin: {first_bin}'
            else:
                entry['description'] = 'cargo run'
            entry['command'] = 'cargo'
            entry['args'] = ['run']
            return entry
        entry['command'] = 'cargo'
        entry['args'] = ['run']
        return entry

    elif lang == 'go':
        go_mod = project_root / 'go.mod'
        if go_mod.exists():
            mod_content = _read_file(go_mod)
            mod_match = re.search(r'^module\s+(\S+)', mod_content, re.MULTILINE)
            if mod_match:
                entry['module_path'] = mod_match.group(1)
                entry['description'] = f'module: {entry["module_path"]}'

        cmd_dir = project_root / 'cmd'
        if cmd_dir.is_dir():
            subdirs = [d for d in cmd_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
            if subdirs:
                entry['entry_file'] = str(subdirs[0] / 'main.go')
                entry['description'] = f'cmd/{subdirs[0].name}'

        entry['command'] = 'go'
        entry['args'] = ['run', '.']
        return entry

    return entry


# ── Config generation ──────────────────────────────────────────────────

def make_command(lang: str, project_name: str, project_root: Path) -> tuple[str, list[str]]:
    """Build command/args using auto-detected entry points when available."""
    entry = detect_project_entry(project_root, lang)
    if entry['command']:
        return (entry['command'], entry['args'])

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
        entry_name = 'index.ts' if lang == 'typescript' and (project_root / 'index.ts').exists() else 'index.js'
        if (project_root / entry_name).exists():
            return ('npx' if lang == 'typescript' else 'node', [
                f'--loader tsx' if lang == 'typescript' else entry_name,
            ])
        if lang == 'javascript':
            js_files = [f for f in project_root.glob('*.js') if not should_skip(f)]
            if js_files:
                return ('node', [str(js_files[0])])
        return ('npx' if lang == 'typescript' else 'node', [
            f'-m {project_name}' if lang == 'typescript' else entry_name,
        ])
    if lang == 'rust':
        return ('cargo', ['run'])
    if lang == 'go':
        return ('go', ['run', '.'])
    return ('python', [])


def type_to_schema(param: dict, param_name: str) -> dict:
    schema = {'type': param['type'], 'description': param.get('description', '')}
    return schema


def generate_mcp_config(
    project_name: str,
    functions: list[dict],
    lang: str,
    project_root: Path,
    server_path: str | None = None,
) -> dict:
    """Generate MCP config dict.

    If server_path is provided, use it as the command (for claude/cursor formats).
    """
    if server_path:
        command = sys.executable or 'python'
        args = [server_path]
    else:
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

    server_config = {
        'command': command,
        'args': args,
        'env': {},
        'disabled': False,
        'autoApprove': [],
    }

    server_config['tools'] = tools

    return {
        'mcpServers': {
            project_name: server_config,
        },
    }


def generate_claude_config(
    project_name: str,
    functions: list[dict],
    lang: str,
    project_root: Path,
    server_path: str | None = None,
) -> dict:
    """Generate Claude Desktop compatible MCP config.

    Claude format: { mcpServers: { name: { command, args, env } } }
    No embedded tools array - Claude discovers tools via the MCP protocol.
    """
    if server_path:
        command = sys.executable or 'python'
        args = [server_path]
    else:
        command, args = make_command(lang, project_name, project_root)

    return {
        'mcpServers': {
            project_name: {
                'command': command,
                'args': args,
                'env': {},
            },
        },
    }


def generate_cursor_config(
    project_name: str,
    functions: list[dict],
    lang: str,
    project_root: Path,
    server_path: str | None = None,
) -> dict:
    """Generate Cursor MCP config format.

    Cursor uses a similar flat structure to Claude with command/args.
    """
    if server_path:
        command = sys.executable or 'python'
        args = [server_path]
    else:
        command, args = make_command(lang, project_name, project_root)

    return {
        'mcpServers': {
            project_name: {
                'command': command,
                'args': args,
            },
        },
    }


# ── UPGRADE 2: Generate MCP server wrapper ──────────────────────────────

def _module_file_to_import(filepath: str, project_root: Path) -> str | None:
    """Convert a source file path to a Python import string relative to project_root."""
    try:
        file_path = Path(filepath).resolve()
        root_path = project_root.resolve()
        rel = file_path.relative_to(root_path)
        parts = list(rel.parts)
        if parts[-1].endswith('.py'):
            parts[-1] = parts[-1][:-3]
        elif parts[-1] == '__init__.py':
            parts[-1] = ''
        else:
            return None
        parts = [p for p in parts if p]
        if not parts:
            return None
        return '.'.join(parts)
    except ValueError:
        return None


def generate_server_file(
    project_root: Path,
    project_name: str,
    functions: list[dict],
    lang: str,
    output_dir: Path,
) -> Path:
    """Generate a working MCP server wrapper script.

    For Python projects, generates proper import-based dispatching.
    For other languages, generates a template that can be manually wired.

    Returns the path to the generated server file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    server_path = output_dir / 'server.py'

    tools_list = []
    for func in functions:
        properties = {}
        required = []
        for param in func['params']:
            properties[param['name']] = {
                'type': param['type'],
                'description': param.get('description', ''),
            }
            if param['required']:
                required.append(param['name'])
        desc = func['docstring']
        if not desc and func.get('is_route'):
            desc = f"{func.get('route_method', 'GET')} {func.get('route_path', '/')}"
        if not desc:
            desc = f"Auto-discovered function from {Path(func['file']).name}"
        tools_list.append({
            'name': func['name'],
            'description': desc,
            'inputSchema': {
                'type': 'object',
                'properties': properties,
                'required': required,
            },
        })

    tools_json = json.dumps(tools_list, indent=2, ensure_ascii=False)

    dispatch_entries = []
    import_lines = []
    seen_imports = set()

    if lang == 'python':
        func_to_module = {}
        for func in functions:
            module_path = _module_file_to_import(func['file'], project_root)
            if module_path:
                func_to_module.setdefault(module_path, []).append(func['name'])

        for module_path, func_names in sorted(func_to_module.items()):
            func_names_sorted = sorted(set(func_names))
            import_key = f'from {module_path} import {", ".join(func_names_sorted)}'
            if import_key not in seen_imports:
                import_lines.append(import_key)
                seen_imports.add(import_key)
            for fn in func_names_sorted:
                dispatch_entries.append(
                    f"        if name == {fn!r}:\n"
                    f"            return {fn}(**args)"
                )

    dispatch_block = '\n'.join(dispatch_entries) if dispatch_entries else (
        "        raise ValueError(f'Unknown tool: {name}')"
    )
    if dispatch_entries:
        dispatch_block += "\n        raise ValueError(f'Unknown tool: {name}')"

    imports_block = '\n'.join(import_lines) if import_lines else (
        '# No Python imports auto-detected; wire manually'
    )

    server_code = f'''#!/usr/bin/env python3
"""Auto-generated MCP server for {project_name}"""
import sys
import json
import traceback

{imports_block}

TOOLS = {tools_json}


def handle_request(request):
    method = request.get("method")
    if method == "tools/list":
        return {{"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params", {{}})
        tool_name = params.get("name")
        tool_args = params.get("arguments", {{}})
        try:
            result = call_tool(tool_name, tool_args)
            return {{"content": [{{"type": "text", "text": str(result)}}]}}
        except Exception as e:
            return {{
                "content": [{{"type": "text", "text": f"Error: {{e}}"}}],
                "isError": True,
            }}
    return {{"error": f"Unknown method: {{method}}"}}


def call_tool(name, args):
{dispatch_block}


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        resp = handle_request(req)
        resp["id"] = req.get("id")
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
    except Exception:
        pass
'''

    with open(server_path, 'w', encoding='utf-8') as f:
        f.write(server_code)

    return server_path


# ── UPGRADE 5: Interactive mode helpers ─────────────────────────────────

def _function_is_excluded(func: dict, exclude_patterns: list[str]) -> bool:
    """Check if a function matches any exclude regex pattern."""
    for pattern in exclude_patterns:
        try:
            if re.search(pattern, func['name']):
                return True
        except re.error:
            print(f'Warning: invalid exclude pattern: {pattern}', file=sys.stderr)
            continue
    return False


def _function_is_hidden_default(func: dict) -> bool:
    """Check if function should be hidden by default in interactive mode."""
    name = func['name']
    lower_name = name.lower()
    if name.startswith('_') or '_internal' in lower_name or lower_name.startswith('test_'):
        return True
    if func.get('deprecated'):
        return True
    file_path = func.get('file', '')
    if '/test/' in file_path or '\\test\\' in file_path or '/tests/' in file_path or '\\tests\\' in file_path:
        return True
    return False


def interactive_select(
    functions: list[dict],
    show_all: bool = False,
    exclude_patterns: list[str] | None = None,
) -> list[dict]:
    """Interactive selection of functions with name/description editing.

    Returns the final list of functions after user selection and editing.
    """
    exclude_patterns = exclude_patterns or []

    filtered = []
    hidden = []
    for func in functions:
        if _function_is_excluded(func, exclude_patterns):
            continue
        if not show_all and _function_is_hidden_default(func):
            hidden.append(func)
            continue
        filtered.append(func)

    if not filtered:
        print('No functions to display (all hidden or excluded).', file=sys.stderr)
        return []

    print(f'\nDiscovered {len(filtered)} functions', end='')
    if hidden:
        print(f' ({len(hidden)} hidden)', end='')
    print(':\n')

    for i, func in enumerate(filtered, 1):
        flags = ''
        if func.get('is_route'):
            flags += f' [{func.get("route_method", "RTE")} {func.get("route_path", "/")}]'
        if func.get('deprecated'):
            flags += ' [DEPRECATED]'
        print(f'  {i:4d}. {func["name"]:<40s} {flags}')
        if func['params']:
            param_strs = []
            for p in func['params']:
                req = '' if p['required'] else '?'
                param_strs.append(f'{p["name"]}{req}: {p["type"]}')
            print(f'       params: {", ".join(param_strs)}')
        if func['docstring']:
            desc_preview = func['docstring'][:80]
            print(f'       {desc_preview}')
        print()

    if hidden and not show_all:
        print(f'{len(hidden)} functions hidden (use --show-all to reveal).')

    sel_raw = input('\nSelect functions to include (space-separated numbers, or "all"): ').strip()
    if sel_raw.lower() == 'all':
        selected = filtered[:]
    else:
        try:
            indices = [int(x) - 1 for x in sel_raw.split()]
            selected = [filtered[i] for i in indices if 0 <= i < len(filtered)]
        except (ValueError, IndexError):
            print('Invalid selection.', file=sys.stderr)
            return []

    if not selected:
        print('No functions selected.', file=sys.stderr)
        return []

    print(f'\nEditing {len(selected)} selected functions (press Enter to keep current value):\n')

    for func in selected:
        print(f'  Function: {func["name"]}')
        new_name = input(f'  Name [{func["name"]}]: ').strip()
        if new_name:
            func['name'] = new_name

        desc = func['docstring']
        if not desc and func.get('is_route'):
            desc = f"{func.get('route_method', 'GET')} {func.get('route_path', '/')}"
        if not desc:
            desc = ''
        new_desc = input(f'  Description [{desc}]: ').strip()
        if new_desc:
            func['docstring'] = new_desc
        print()

    return selected


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Scan a codebase and generate MCP server config from discovered functions/endpoints.',
    )
    parser.add_argument(
        '--path', default='.',
        help='Project root directory (default: current dir)',
    )
    parser.add_argument(
        '--output', '-o', default='.mcp/',
        help='Output directory (default: .mcp/)',
    )
    parser.add_argument(
        '--name',
        help='MCP server name (default: project directory basename)',
    )
    parser.add_argument(
        '--lang', '--language', dest='language',
        help='Force language (python, javascript, typescript, rust, go)',
    )
    parser.add_argument(
        '--stdout', action='store_true',
        help='Print JSON to stdout instead of writing files',
    )
    parser.add_argument(
        '--generate-server', action='store_true',
        help='Generate a working MCP server wrapper (server.py) using stdio transport',
    )
    parser.add_argument(
        '--format', dest='output_format', default='mcp',
        choices=('mcp', 'claude', 'cursor'),
        help='Output format: mcp (default .mcp/ dir), claude (Claude Desktop JSON), cursor (Cursor MCP JSON)',
    )
    parser.add_argument(
        '--interactive', '-i', action='store_true',
        help='Interactive mode: select and edit functions before generating config',
    )
    parser.add_argument(
        '--show-all', action='store_true',
        help='Show all functions in interactive mode including hidden ones',
    )
    parser.add_argument(
        '--exclude', action='append', default=[],
        help='Exclude functions matching regex pattern (can be repeated)',
    )

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

    print(
        f'Discovering {LANGUAGE_NAMES.get(lang, lang)} functions in {project_root}...',
        file=sys.stderr,
    )
    functions = discover(project_root, lang)

    if not functions:
        print('No discoverable functions found.', file=sys.stderr)
        sys.exit(0)

    if args.exclude:
        functions = [f for f in functions if not _function_is_excluded(f, args.exclude)]

    files_used = len({f['file'] for f in functions})
    print(
        f'Found {len(functions)} functions across {files_used} files.',
        file=sys.stderr,
    )

    if args.interactive:
        functions = interactive_select(functions, show_all=args.show_all, exclude_patterns=args.exclude)
        if not functions:
            print('No functions selected. Exiting.', file=sys.stderr)
            sys.exit(0)
        files_used = len({f['file'] for f in functions})

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / args.output

    server_path = None
    if args.generate_server:
        server_dir = output_path
        server_file = generate_server_file(project_root, project_name, functions, lang, server_dir)
        server_path = str(server_file.resolve())
        print(f'Wrote MCP server wrapper to {server_path}', file=sys.stderr)

    if args.output_format == 'claude':
        config = generate_claude_config(project_name, functions, lang, project_root, server_path)
    elif args.output_format == 'cursor':
        config = generate_cursor_config(project_name, functions, lang, project_root, server_path)
    else:
        config = generate_mcp_config(project_name, functions, lang, project_root, server_path)

    tool_count = len(functions)

    if args.stdout or args.output_format in ('claude', 'cursor'):
        print(json.dumps(config, indent=2))
    else:
        output_dir = output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        mcp_path = output_dir / 'mcp.json'
        with open(mcp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f'Wrote {mcp_path}', file=sys.stderr)

        tools_dir = output_dir / 'tools'
        tools_dir.mkdir(parents=True, exist_ok=True)
        for tool in config['mcpServers'][project_name].get('tools', []):
            tool_path = tools_dir / f"{tool['name']}.json"
            with open(tool_path, 'w', encoding='utf-8') as f:
                json.dump(tool, f, indent=2)

        print(f'Wrote {tool_count} tool definitions to {tools_dir}/', file=sys.stderr)

    summary = (
        f'\nSummary: Discovered {len(functions)} functions across {files_used} files. '
        f'Generated MCP config with {tool_count} tools.'
    )
    print(summary, file=sys.stderr)


if __name__ == '__main__':
    main()
