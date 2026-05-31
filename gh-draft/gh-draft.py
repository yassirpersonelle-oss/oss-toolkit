#!/usr/bin/env python3
import argparse
import os
import shlex
import subprocess
import sys
import urllib.parse

GREEN = '\033[92m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def run(cmd, capture=True):
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, check=False)
        return r.returncode, r.stdout.strip() if capture else '', r.stderr.strip() if capture else ''
    except FileNotFoundError:
        print(f"{RED}Error: git not found{RESET}", file=sys.stderr)
        sys.exit(1)


def get_remote_url():
    code, out, _ = run(['git', 'remote', 'get-url', 'origin'])
    if code != 0 or not out:
        return None
    return out


def get_repo_slug(remote_url):
    url = remote_url
    if url.startswith('git@'):
        url = url.replace(':', '/').replace('git@', '')
    if url.endswith('.git'):
        url = url[:-4]
    parts = url.split('/')
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return None


def build_pr_url(base, remote_url):
    slug = get_repo_slug(remote_url)
    if not slug:
        return None
    return f"https://github.com/{slug}/compare/{base}...$(git rev-parse --abbrev-ref HEAD)?expand=1"


def show_diff(base, max_lines=200):
    code, out, _ = run(['git', 'diff', f'HEAD...{base}', '--stat'])
    if code != 0:
        print(f"{RED}No commits yet on this branch compared to {base}{RESET}")
        return False

    if not out:
        code, out, _ = run(['git', 'diff', 'HEAD', '--stat'])
        if not out:
            print(f"{RED}No changes detected{RESET}")
            return False

    print(f"\n{BOLD}Changes summary:{RESET}")
    print(out)

    code, diff_out, _ = run(['git', 'diff', f'HEAD...{base}'])
    if code != 0:
        code, diff_out, _ = run(['git', 'diff', 'HEAD'])

    if diff_out:
        lines = diff_out.split('\n')
        display = lines[:max_lines]
        truncated = len(lines) > max_lines

        print(f"\n{BOLD}Diff preview:{RESET}")
        for line in display:
            if line.startswith('+') and not line.startswith('+++'):
                print(f"{GREEN}{line}{RESET}")
            elif line.startswith('-') and not line.startswith('---'):
                print(f"{RED}{line}{RESET}")
            elif line.startswith('@@'):
                print(f"{CYAN}{line}{RESET}")
            else:
                print(line)

        if truncated:
            more = len(lines) - max_lines
            print(f"\n{CYAN}... and {more} more lines. Use --more to see full diff.{RESET}")
    else:
        print(f"{RED}No diff available{RESET}")

    return True


def check_dirty():
    code, out, _ = run(['git', 'status', '--porcelain'])
    if out:
        print(f"{RED}Warning: Working tree is dirty. Uncommitted changes won't be in the PR.{RESET}")
        return True
    return False


def push():
    code, _, err = run(['git', 'push', 'origin', 'HEAD'])
    if code != 0:
        print(f"{RED}Push failed:{RESET} {err}", file=sys.stderr)
        return False
    print(f"{GREEN}Push successful!{RESET}")
    return True


def create_pr_gh(title, body, base):
    cmd = ['gh', 'pr', 'create', '--base', base, '--title', title]
    if body:
        cmd.extend(['--body', body])
    code, out, err = run(cmd)
    if code == 0:
        print(f"{GREEN}PR created: {out}{RESET}")
    else:
        print(f"{RED}Failed to create PR via gh CLI:{RESET} {err}", file=sys.stderr)
    return code == 0


def open_browser(url):
    import webbrowser
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description='Preview PR diff, then push and create PR in one command.')
    parser.add_argument('--base', '-b', default='main', help='Target branch (default: main)')
    parser.add_argument('--title', '-t', default='', help='PR title')
    parser.add_argument('--body', '-B', default='', help='PR body')
    parser.add_argument('--dry-run', action='store_true', help='Only show diff without pushing')
    parser.add_argument('--push', action='store_true', help='Skip preview, go straight to push+PR')
    parser.add_argument('--more', action='store_true', help='Show full diff without truncation')
    args = parser.parse_args()

    if not os.path.isdir('.git'):
        print(f"{RED}Error: not a git repository{RESET}", file=sys.stderr)
        sys.exit(1)

    remote_url = get_remote_url()
    if not remote_url:
        print(f"{RED}Error: no remote 'origin' configured{RESET}", file=sys.stderr)
        sys.exit(1)

    is_dirty = check_dirty()

    if not args.push:
        max_lines = 0 if args.more else 200
        has_diff = show_diff(args.base, max_lines)
        if not has_diff:
            sys.exit(0)

        if not sys.stdin.isatty():
            print(f"{RED}No TTY available. Use --push to skip interactive mode.{RESET}", file=sys.stderr)
            sys.exit(1)

        response = input(f"\nPush to remote? [Y/n] ").strip().lower()
        if response not in ('', 'y', 'yes'):
            print("Aborted.")
            sys.exit(0)

    if args.dry_run:
        print(f"\n{CYAN}Dry-run: skipping push and PR creation{RESET}")
        return

    if not push():
        sys.exit(1)

    title = args.title or input("PR title (optional): ").strip()
    body = args.body or input("PR body (optional): ").strip()

    gh_available = run(['which', 'gh'])[0] == 0 if sys.platform != 'win32' else os.path.exists(os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'GitHub CLI', 'gh.exe'))

    if gh_available:
        create_pr_gh(title, body, args.base)
    else:
        pr_url = build_pr_url(args.base, remote_url)
        if pr_url:
            print(f"\n{CYAN}Open this URL to create your PR:{RESET}")
            print(pr_url)
            try:
                open_browser(pr_url)
            except Exception:
                pass
        else:
            print(f"{RED}Could not build PR URL. Create it manually on GitHub.{RESET}")


if __name__ == '__main__':
    main()
