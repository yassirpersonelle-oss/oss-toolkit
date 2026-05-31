#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys
from collections import OrderedDict

CONVENTIONAL_TYPES = OrderedDict([
    ('feat', 'Features'),
    ('fix', 'Bug Fixes'),
    ('docs', 'Documentation'),
    ('style', 'Style'),
    ('refactor', 'Refactoring'),
    ('perf', 'Performance'),
    ('test', 'Tests'),
    ('build', 'Build System'),
    ('ci', 'CI'),
    ('chore', 'Chores'),
    ('revert', 'Reverts'),
])

OTHER_HEADING = 'Other'

GITHUB_REPO = 'https://github.com/yassir/oss-toolkit/commit/'


def run_git(args, repo_path):
    cmd = ['git'] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_path,
            check=False,
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return result.stdout.strip(), None
    except FileNotFoundError:
        return None, 'git not found. Is git installed?'


def get_latest_tag(repo_path):
    stdout, err = run_git(['describe', '--tags', '--abbrev=0'], repo_path)
    if err:
        return None
    return stdout


def get_commits_since(tag, repo_path):
    if tag:
        rev_range = f'{tag}..HEAD'
    else:
        rev_range = 'HEAD'
    stdout, err = run_git(
        ['log', rev_range, '--pretty=format:%s|||%b|||%H|||%an'],
        repo_path,
    )
    if err:
        return []
    if not stdout:
        return []
    commits = []
    for line in stdout.splitlines():
        parts = line.split('|||', 3)
        if len(parts) == 4:
            subject, body, hash_, author = parts
            commits.append({
                'subject': subject,
                'body': body,
                'hash': hash_,
                'author': author,
            })
    return commits


COMMIT_PATTERN = re.compile(
    r'^(?P<type>[a-zA-Z]+)'
    r'(?:\((?P<scope>[^)]*)\))?'
    r':\s*(?P<description>.*)$'
)


def parse_conventional_commit(subject):
    match = COMMIT_PATTERN.match(subject)
    if not match:
        return None, None, subject
    return match.group('type'), match.group('scope'), match.group('description')


def short_hash(h):
    return h[:7] if len(h) >= 7 else h


def generate_changelog(commits, tag, verbose):
    if tag:
        version_header = f'## [{tag}]'
    else:
        version_header = '## [Unreleased]'

    if not commits:
        lines = [
            '# Changelog',
            '',
            version_header,
            '',
            '_No changes._',
            '',
        ]
        if verbose:
            print('No commits found.')
        return '\n'.join(lines)

    groups = {}
    uncategorized = []

    for commit in commits:
        ctype, cscope, desc = parse_conventional_commit(commit['subject'])
        if ctype is None:
            uncategorized.append((cscope, desc, commit['hash']))
            continue
        groups.setdefault(ctype, []).append((cscope, desc, commit['hash']))

    lines = ['# Changelog', '', version_header, '']

    for _type, heading in CONVENTIONAL_TYPES.items():
        items = groups.pop(_type, [])
        if not items:
            continue
        lines.append(f'### {heading}')
        items.sort(key=lambda x: (x[0] or '', x[1] or ''))
        for scope, desc, hash_ in items:
            link = f'[{short_hash(hash_)}]({GITHUB_REPO}{hash_})'
            if scope:
                lines.append(f'- **{scope}:** {desc} ({link})')
            else:
                lines.append(f'- {desc} ({link})')
        lines.append('')

    if groups:
        remaining = []
        for _type, items in groups.items():
            for scope, desc, hash_ in items:
                remaining.append((_type, scope, desc, hash_))
        remaining.sort(key=lambda x: (x[0], x[1] or '', x[2] or ''))
        lines.append(f'### {OTHER_HEADING}')
        for _type, scope, desc, hash_ in remaining:
            link = f'[{short_hash(hash_)}]({GITHUB_REPO}{hash_})'
            if scope:
                lines.append(f'- **{_type}({scope}):** {desc} ({link})')
            else:
                lines.append(f'- **{_type}:** {desc} ({link})')
        lines.append('')

    if uncategorized:
        lines.append('### Uncategorized')
        for _, desc, hash_ in uncategorized:
            link = f'[{short_hash(hash_)}]({GITHUB_REPO}{hash_})'
            lines.append(f'- {desc} ({link})')
        lines.append('')

    if verbose:
        print(f'Found {len(commits)} commit(s) since {tag or "the beginning"}.')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate a CHANGELOG.md from conventional commits.'
    )
    parser.add_argument(
        '--tag',
        help='Tag to start from (default: last tag from git describe)',
    )
    parser.add_argument(
        '-o', '--output',
        default='CHANGELOG.md',
        help='Output file (default: CHANGELOG.md)',
    )
    parser.add_argument(
        '--repo-path',
        default='.',
        help='Path to git repository (default: current directory)',
    )
    parser.add_argument(
        '--stdout',
        action='store_true',
        help='Print changelog to stdout instead of writing to file',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print summary information',
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(os.path.join(repo_path, '.git')):
        print(f'Error: {repo_path} is not a git repository.', file=sys.stderr)
        sys.exit(1)

    tag = args.tag
    if tag is None:
        tag = get_latest_tag(repo_path)

    commits = get_commits_since(tag, repo_path)

    changelog = generate_changelog(commits, tag, args.verbose)

    if args.stdout:
        print(changelog)
    else:
        output_path = os.path.abspath(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(changelog)
        if args.verbose:
            print(f'Written to {output_path}')


if __name__ == '__main__':
    main()
