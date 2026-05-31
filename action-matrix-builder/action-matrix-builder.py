#!/usr/bin/env python3
import argparse
import os
import sys
import yaml

LANGUAGE_CONFIGS = {
    'python': {
        'setup': 'actions/setup-python@v5',
        'version_param': 'python-version',
        'cache_key': 'pip',
        'cache_path': '~/.cache/pip',
        'install': 'pip install -e ".[dev]"',
        'test': 'pytest',
        'cache_match': '**/requirements*.txt, **/pyproject.toml, **/setup.py, **/setup.cfg',
    },
    'node': {
        'setup': 'actions/setup-node@v4',
        'version_param': 'node-version',
        'cache_key': 'npm',
        'cache_path': '~/.npm',
        'install': 'npm ci',
        'test': 'npm test',
        'cache_match': '**/package-lock.json',
    },
    'go': {
        'setup': 'actions/setup-go@v5',
        'version_param': 'go-version',
        'cache_key': 'go',
        'cache_path': '~/.cache/go',
        'install': 'go mod download',
        'test': 'go test ./...',
        'cache_match': '**/go.sum',
    },
    'rust': {
        'setup': 'actions-rs/toolchain@v1',
        'version_param': 'toolchain',
        'cache_key': 'cargo',
        'cache_path': '~/.cargo/registry',
        'install': 'cargo build --release',
        'test': 'cargo test',
        'cache_match': '**/Cargo.lock',
    },
}

DEFAULT_CONFIG = {
    'language': 'python',
    'versions': ['3.11', '3.12', '3.13'],
    'os': ['ubuntu-latest', 'windows-latest', 'macos-latest'],
    'test_command': None,
    'install_command': None,
    'cache': None,
    'artifact': True,
}


def load_config(config_path):
    if not os.path.isfile(config_path):
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error parsing config: {e}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(data, dict):
        print("Error: config must be a YAML mapping", file=sys.stderr)
        sys.exit(1)

    config = DEFAULT_CONFIG.copy()
    config.update({k: v for k, v in data.items() if v is not None})

    if config['language'] not in LANGUAGE_CONFIGS:
        print(f"Error: unsupported language '{config['language']}'. Supported: {', '.join(LANGUAGE_CONFIGS.keys())}", file=sys.stderr)
        sys.exit(1)

    if not config['versions']:
        print("Error: 'versions' list cannot be empty", file=sys.stderr)
        sys.exit(1)

    if not config['os']:
        print("Error: 'os' list cannot be empty", file=sys.stderr)
        sys.exit(1)

    return config


def validate_config(config_path):
    config = load_config(config_path)
    lang_cfg = LANGUAGE_CONFIGS[config['language']]

    print(f"Config valid: {config_path}")
    print(f"  Language: {config['language']}")
    print(f"  Versions: {', '.join(config['versions'])}")
    print(f"  OS: {', '.join(config['os'])}")
    print(f"  Cache: {config['cache'] or lang_cfg['cache_key']}")
    print(f"  Artifact upload: {config['artifact']}")
    return True


def generate_workflow(config):
    lang_cfg = LANGUAGE_CONFIGS[config['language']]
    cache_key = config['cache'] or lang_cfg['cache_key']
    test_cmd = config['test_command'] or lang_cfg['test']
    install_cmd = config['install_command'] or lang_cfg['install']

    lines = []
    lines.append(f'name: {config["language"].title()} CI Matrix')
    lines.append('')
    lines.append('on:')
    lines.append('  push:')
    lines.append('    branches: [ main ]')
    lines.append('  pull_request:')
    lines.append('    branches: [ main ]')
    lines.append('')
    lines.append('jobs:')
    lines.append('  build:')
    lines.append('    runs-on: ${{ matrix.os }}')
    lines.append('    strategy:')
    lines.append('      fail-fast: false')
    lines.append('      matrix:')

    versions_str = ', '.join(f'"{v}"' for v in config['versions'])
    lines.append(f'        version: [{versions_str}]')

    os_str = ', '.join(f'"{o}"' for o in config['os'])
    lines.append(f'        os: [{os_str}]')

    lines.append('')
    lines.append('    steps:')
    lines.append('      - uses: actions/checkout@v4')
    lines.append('')

    lines.append(f'      - uses: {lang_cfg["setup"]}')
    lines.append(f'        with:')
    lines.append(f'          {lang_cfg["version_param"]}: ${{{{ matrix.version }}}}')
    lines.append('')

    lines.append(f'      - name: Cache {cache_key}')
    lines.append(f'        uses: actions/cache@v4')
    lines.append(f'        with:')
    lines.append(f'          path: {lang_cfg["cache_path"]}')
    lines.append(f'          key: ${{{{ runner.os }}}}-{cache_key}-${{{{ hashFiles(\'{lang_cfg["cache_match"]}\') }}}}')
    lines.append(f'          restore-keys: |')
    lines.append(f'            ${{{{ runner.os }}}}-{cache_key}-')
    lines.append('')

    lines.append('      - name: Install dependencies')
    lines.append(f'        run: {install_cmd}')
    lines.append('')

    lines.append('      - name: Run tests')
    lines.append(f'        run: {test_cmd}')
    lines.append('')

    if config['artifact']:
        lines.append('      - name: Upload test artifacts')
        lines.append('        if: always()')
        lines.append('        uses: actions/upload-artifact@v4')
        lines.append('        with:')
        lines.append('          name: test-results-${{ matrix.os }}-${{ matrix.version }}')
        lines.append('          path: |')
        lines.append('            test-results/')
        lines.append('            __pycache__/')
        lines.append('          retention-days: 7')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Generate GitHub Actions matrix workflows from a simplified YAML config.')
    parser.add_argument('--config', default='matrix.yml', help='Path to config file (default: matrix.yml)')
    parser.add_argument('--output', '-o', default='.github/workflows/generated-matrix.yml',
                        help='Output path (default: .github/workflows/generated-matrix.yml)')
    parser.add_argument('--validate', action='store_true', help='Validate config without generating')
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)

    if args.validate:
        validate_config(config_path)
        return

    config = load_config(config_path)
    workflow = generate_workflow(config)

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(workflow)

    print(f"Generated workflow: {output_path}")
    print(f"Matrix: {len(config['versions'])} versions x {len(config['os'])} OS = {len(config['versions']) * len(config['os'])} jobs")


if __name__ == '__main__':
    main()
