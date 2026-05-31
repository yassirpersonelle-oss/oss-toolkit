#!/usr/bin/env python3
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

SKIP_DIRS = {'__pycache__', '.git', 'node_modules', '.cache', 'Cache', 'cache'}
SKIP_EXTS = {'.pyc', '.pyo', '.cache', '.swp', '.lock'}


def hash_file(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def relative_target_path(source_path, watch_root, repo_root):
    rel = os.path.relpath(source_path, watch_root)
    return os.path.join(repo_root, rel)


def should_skip(name):
    if name in SKIP_DIRS:
        return True
    _, ext = os.path.splitext(name)
    return ext in SKIP_EXTS


def copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def git_operation(repo_root, files):
    try:
        subprocess.run(['git', 'add', '--'] + files, cwd=repo_root, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        return False
    return True


def git_commit(repo_root, filename):
    timestamp = datetime.now().isoformat(timespec='seconds')
    msg = f"sync: {filename} - {timestamp}"
    try:
        subprocess.run(['git', 'commit', '-m', msg], cwd=repo_root, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        if 'nothing to commit' in e.stderr:
            return True
        return False


def git_push(repo_root):
    try:
        subprocess.run(['git', 'push'], cwd=repo_root, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def ensure_repo(repo_root):
    git_dir = os.path.join(repo_root, '.git')
    if not os.path.isdir(git_dir):
        resp = input(f"No git repo at {repo_root}. Initialize one? [Y/n] ").strip().lower()
        if resp not in ('', 'y', 'yes'):
            print("Aborted.", file=sys.stderr)
            sys.exit(1)
        try:
            subprocess.run(['git', 'init'], cwd=repo_root, check=True, capture_output=True)
            print(f"Initialized git repo at {repo_root}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to init repo: {e}", file=sys.stderr)
            sys.exit(1)


def sync_watch(watch_root, repo_root, auto_push):
    file_hashes = {}

    for dirpath, dirnames, filenames in os.walk(watch_root):
        dirnames[:] = [d for d in dirnames if not should_skip(d)]
        for f in filenames:
            if should_skip(f):
                continue
            src = os.path.join(dirpath, f)
            if os.path.isfile(src):
                h = hash_file(src)
                if h:
                    file_hashes[src] = h

    changed = []
    for src, h in file_hashes.items():
        dst = relative_target_path(src, watch_root, repo_root)
        dst_h = hash_file(dst) if os.path.exists(dst) else None
        if h != dst_h:
            copy_file(src, dst)
            changed.append(src)

    if changed:
        staged = []
        for src in changed:
            dst = relative_target_path(src, watch_root, repo_root)
            rel_dst = os.path.relpath(dst, repo_root)
            staged.append(rel_dst)
            copy_file(src, dst)

        if staged:
            git_operation(repo_root, staged)
            for s in staged:
                git_commit(repo_root, s)

            if auto_push:
                git_push(repo_root)

    return len(changed)


def main():
    parser = argparse.ArgumentParser(description='Watch dotfiles and sync changes to a git repo.')
    parser.add_argument('--watch', '-w', default=os.path.expanduser('~/.config'),
                        help='Path to watch (default: ~/.config)')
    parser.add_argument('--repo', '-r', default=os.path.expanduser('~/dotfiles'),
                        help='Path to dotfiles git repo (default: ~/dotfiles)')
    parser.add_argument('--interval', '-i', type=int, default=300,
                        help='Poll interval in seconds (default: 300)')
    parser.add_argument('--auto-push', action='store_true', help='Auto push to remote after commit')
    parser.add_argument('--once', action='store_true', help='Single sync and exit (for cron)')
    args = parser.parse_args()

    watch_root = os.path.abspath(os.path.expanduser(args.watch))
    repo_root = os.path.abspath(os.path.expanduser(args.repo))

    if not os.path.isdir(watch_root):
        print(f"Watch path does not exist: {watch_root}", file=sys.stderr)
        sys.exit(1)

    ensure_repo(repo_root)

    if args.once:
        count = sync_watch(watch_root, repo_root, args.auto_push)
        print(f"Synced {count} file(s)")
        return

    print(f"Watching {watch_root} -> {repo_root}. Next sync in {args.interval}s.")

    while True:
        count = sync_watch(watch_root, repo_root, args.auto_push)
        if count:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] Synced {count} file(s)")
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
