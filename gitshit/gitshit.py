#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import shutil

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

SECRET_PATTERNS = [
    (r"password\s*=", "password assignment"),
    (r"secret\s*=", "secret assignment"),
    (r"api[_ ]?key\s*=", "API key assignment"),
    (r"token\s*=", "token assignment"),
    (r"-----BEGIN", "PEM key block"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"gho_[A-Za-z0-9]{36}", "GitHub OAuth access token"),
    (r"ghu_[A-Za-z0-9]{36}", "GitHub user token"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI API key"),
]

TODO_PATTERNS = [r"TODO", r"FIXME", r"HACK", r"BUG", r"XXX"]

BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pkl",
    ".zip", ".tar.gz", ".7z", ".iso", ".tar", ".gz",
    ".rar", ".jar", ".war", ".class", ".pyc", ".o", ".a",
    ".lib", ".dmg", ".pkg", ".deb", ".rpm", ".msi",
    ".psd", ".ai", ".eps", ".ttf", ".otf", ".woff",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flv",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".min.js", ".min.css", ".map",
    ".whl", ".egg", ".nar", ".snap", ".flatpak",
    ".dcm", ".nii", ".h5", ".hdf5", ".pb", ".onnx",
    ".tfrecord", ".caffemodel", ".npy", ".npz",
    ".pak", ".unity3d", ".blend", ".fbx", ".obj",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".pl", ".pm", ".lua", ".r", ".m", ".mm", ".sh", ".bash", ".zsh",
    ".fish", ".ps1", ".bat", ".cmd", ".txt", ".md", ".rst", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".json", ".xml", ".html", ".htm",
    ".css", ".scss", ".sass", ".less", ".sql", ".env", ".env.*", ".gitignore",
    ".gitattributes", ".gitmodules", ".dockerfile", ".tf", ".gradle",
    ".makefile", ".cmake",
}

LARGE_FILE_THRESHOLD = 1 * 1024 * 1024
CRITICAL_LARGE_FILE_THRESHOLD = 10 * 1024 * 1024

EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv",
                "env", ".env", "dist", "build", "target", ".next",
                ".nuxt", "vendor", "bower_components", ".tox",
                ".eggs", "eggs", "lib", "Lib", "site-packages"}

import re as _re


def _prompt_yes_no(question, default_no=True):
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        return False
    try:
        prompt = f"{YELLOW}  ?{RESET} {question} "
        if default_no:
            prompt += "[y/N] "
        else:
            prompt += "[Y/n] "
        response = input(prompt).strip().lower()
        if default_no:
            return response == "y"
        else:
            return response != "n"
    except (EOFError, KeyboardInterrupt):
        return False


def _run_git(cmd, cwd):
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=60,
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "git not found", -1
    except subprocess.TimeoutExpired:
        return "", "git command timed out", -1


def _is_text_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if ext in BINARY_EXTENSIONS:
        return False
    name = os.path.basename(filepath).lower()
    if name in {"makefile", "dockerfile", "gemfile", "rakefile"} or name.startswith(".env"):
        return True
    return None


def _format_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


def _should_exclude(path):
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def _has_binary_ext(filepath):
    _, ext = os.path.splitext(filepath)
    return ext.lower() in BINARY_EXTENSIONS


class GitShitScanner:
    def __init__(self, repo_path, verbose=False, json_output=False, interactive=None):
        self.repo_path = os.path.abspath(repo_path)
        self.verbose = verbose
        self.json_output = json_output
        if interactive is None:
            self.interactive = sys.stdout.isatty()
        else:
            self.interactive = interactive
        self.results = []
        self.total_score = 0
        self.file_count = 0
        self.commit_count = 0
        self.tracked_files = []
        self._errors = []

    def out(self, *args, **kwargs):
        if not self.json_output:
            print(*args, **kwargs)

    def vout(self, *args, **kwargs):
        if self.verbose and not self.json_output:
            print(*args, **kwargs)

    def _prompt(self, title, lines):
        if not self.interactive:
            return
        if _prompt_yes_no(f"View details for \"{title}\"?"):
            if self.json_output:
                return
            for line in lines[:20]:
                print(f"    {DIM}{line}{RESET}")
            if len(lines) > 20:
                print(f"    {DIM}... and {len(lines) - 20} more{RESET}")

    def add_result(self, severity, category, score, message, details=None):
        entry = {
            "severity": severity,
            "category": category,
            "score": score,
            "message": message,
            "details": details or [],
        }
        self.results.append(entry)
        self.total_score += score

        if self.json_output:
            return

        color_map = {
            SEVERITY_CRITICAL: RED,
            SEVERITY_HIGH: YELLOW,
            SEVERITY_MEDIUM: BLUE,
            SEVERITY_LOW: DIM,
        }
        emoji_map = {
            SEVERITY_CRITICAL: "[!]",

            SEVERITY_HIGH: "[~]",

            SEVERITY_MEDIUM: "[*]",

            SEVERITY_LOW: "[i]",
        }
        color = color_map.get(severity, RESET)
        emoji = emoji_map.get(severity, "*")
        badge = f"{emoji} {BOLD}{severity}{RESET}"
        score_str = f"({YELLOW}score: {score}{RESET})" if score else ""
        print(f"  {badge} {color}{score_str}{RESET} {message}")
        if self.verbose and details:
            for detail in details[:15]:
                print(f"    {DIM}{detail}{RESET}")
            if len(details) > 15:
                print(f"    {DIM}... and {len(details) - 15} more{RESET}")

    def check_git_repo(self):
        stdout, stderr, rc = _run_git(["rev-parse", "--git-dir"], self.repo_path)
        if rc != 0 or not stdout.strip():
            self._errors.append("Not a git repository")
            return False
        return True

    def gather_repo_info(self):
        stdout, _, rc = _run_git(["ls-files"], self.repo_path)
        if rc == 0:
            self.tracked_files = [f for f in stdout.splitlines() if f.strip()]
            self.file_count = len(self.tracked_files)

        stdout, _, rc = _run_git(["log", "--oneline"], self.repo_path)
        if rc == 0:
            self.commit_count = len([l for l in stdout.splitlines() if l.strip()])

    def get_file_size(self, filepath):
        stdout, _, rc = _run_git(
            ["ls-files", "--stage", filepath], self.repo_path
        )
        if rc == 0 and stdout.strip():
            parts = stdout.strip().split()
            if len(parts) >= 2:
                try:
                    blob_hash = parts[1]
                    size_out, _, size_rc = _run_git(
                        ["cat-file", "-s", blob_hash], self.repo_path
                    )
                    if size_rc == 0 and size_out.strip():
                        return int(size_out.strip())
                except (ValueError, IndexError):
                    pass

        full_path = os.path.join(self.repo_path, filepath)
        try:
            return os.path.getsize(full_path)
        except OSError:
            return 0

    def check_large_files(self):
        large = []
        critical = []
        for fp in self.tracked_files:
            size = self.get_file_size(fp)
            if size > CRITICAL_LARGE_FILE_THRESHOLD:
                critical.append((fp, size))
            elif size > LARGE_FILE_THRESHOLD:
                large.append((fp, size))

        if critical:
            details = [f"{fp} ({_format_size(size)})" for fp, size in critical]
            self.add_result(
                SEVERITY_HIGH, "Large files", len(critical) * 5,
                f"Large files >10MB ({len(critical)} found, {_format_size(sum(s for _, s in critical))} total)",
                details,
            )
            self._prompt("Large files >10MB", details)

        if large:
            details = [f"{fp} ({_format_size(size)})" for fp, size in large]
            self.add_result(
                SEVERITY_LOW, "Large files", 0,
                f"Large files >1MB ({len(large)} found, {_format_size(sum(s for _, s in large))} total)",
                details,
            )
            self._prompt("Large files >1MB", details)

    def check_secrets(self):
        findings = []
        seen = set()
        for fp in self.tracked_files:
            if _should_exclude(fp):
                continue
            full_path = os.path.join(self.repo_path, fp)
            if not os.path.isfile(full_path):
                stdout, _, _ = _run_git(["show", f"HEAD:{fp}"], self.repo_path)
                content = stdout
            else:
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except (OSError, IOError):
                    continue

            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                for pattern, label in SECRET_PATTERNS:
                    if _re.search(pattern, line, _re.IGNORECASE):
                        key = (fp, i, label)
                        if key not in seen:
                            seen.add(key)
                            truncated = line.strip()[:80]
                            findings.append(
                                f"{fp}:{i} - {label}: {truncated}"
                            )
                        break

        if findings:
            self.add_result(
                SEVERITY_CRITICAL, "Secrets", len(findings) * 10,
                f"Potential secrets/credentials found ({len(findings)} matches)",
                findings,
            )
            self._prompt("Secrets", findings)

    def check_todos(self):
        findings = []
        seen = set()
        for fp in self.tracked_files:
            if _should_exclude(fp):
                continue
            ext_check = _is_text_file(fp)
            if ext_check is False:
                continue
            full_path = os.path.join(self.repo_path, fp)
            if not os.path.isfile(full_path):
                try:
                    stdout, _, _ = _run_git(["show", f"HEAD:{fp}"], self.repo_path)
                    content = stdout
                except Exception:
                    continue
            else:
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except (OSError, IOError):
                    continue

            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                for pattern in TODO_PATTERNS:
                    if _re.search(rf"\b{pattern}\b", line):
                        key = (fp, i, pattern)
                        if key not in seen:
                            seen.add(key)
                            stripped = line.strip()[:80]
                            findings.append(f"{fp}:{i} - {pattern}: {stripped}")
                        break

        if findings:
            self.add_result(
                SEVERITY_MEDIUM, "TODOs/FIXMEs", len(findings) * 1,
                f"TODO/FIXME/HACK/BUG/XXX comments ({len(findings)} found)",
                findings,
            )
            self._prompt("TODO/FIXME comments", findings)

    def check_env_files(self):
        findings = []
        for fp in self.tracked_files:
            name = os.path.basename(fp)
            if name == ".env" or name.startswith(".env."):
                size = self.get_file_size(fp)
                findings.append(f"{fp} ({_format_size(size)})")

        if findings:
            self.add_result(
                SEVERITY_CRITICAL, "Env files", 8,
                f".env files committed to git ({len(findings)} found)",
                findings,
            )
            self._prompt("Committed .env files", findings)

    def check_binary_files(self):
        findings = []
        total_size = 0
        for fp in self.tracked_files:
            if _has_binary_ext(fp):
                size = self.get_file_size(fp)
                total_size += size
                findings.append(f"{fp} ({_format_size(size)})")

        if findings:
            score = len(findings) * 3
            total_formatted = _format_size(total_size)
            self.add_result(
                SEVERITY_HIGH, "Binary files", score,
                f"Binary files committed ({len(findings)} found, {total_formatted} total)",
                findings[:30],
            )
            self._prompt("Binary files", findings)

    def check_merge_conflicts(self):
        findings = []
        seen = set()
        for fp in self.tracked_files:
            if _should_exclude(fp):
                continue
            ext_check = _is_text_file(fp)
            if ext_check is False:
                continue
            full_path = os.path.join(self.repo_path, fp)
            if not os.path.isfile(full_path):
                try:
                    stdout, _, _ = _run_git(["show", f"HEAD:{fp}"], self.repo_path)
                    content = stdout
                except Exception:
                    continue
            else:
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except (OSError, IOError):
                    continue

            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("<<<<<<<") or stripped.startswith("=======") or stripped.startswith(">>>>>>>"):
                    key = (fp, i)
                    if key not in seen:
                        seen.add(key)
                        findings.append(f"{fp}:{i} - {stripped[:60]}")

        if findings:
            self.add_result(
                SEVERITY_CRITICAL, "Merge conflicts", len(findings) * 8,
                f"Merge conflict markers found ({len(findings)} instances)",
                findings,
            )
            self._prompt("Merge conflicts", findings)

    def check_empty_commits(self):
        findings = []
        stdout, _, rc = _run_git(
            ["log", "--format=%H|%s", "--all"],
            self.repo_path,
        )
        if rc == 0:
            for line in stdout.splitlines():
                if "|" not in line:
                    continue
                sha, msg = line.split("|", 1)
                msg = msg.strip()
                if not msg or msg.lower() in ("initial commit", "wip", "wip.",
                                               "wip:", "fix", "update",
                                               "oops", "asdf", "test",
                                               "commit", "init"):
                    findings.append(f"{sha[:8]} - \"{msg}\"")

        if findings:
            self.add_result(
                SEVERITY_LOW, "Empty/WIP commits", len(findings) * 1,
                f"Empty/WIP/meaningless commits ({len(findings)} found)",
                findings,
            )
            self._prompt("Empty/WIP commits", findings)

    def check_large_dirs(self):
        dir_sizes = {}
        for fp in self.tracked_files:
            size = self.get_file_size(fp)
            parts = fp.replace("\\", "/").split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                dir_sizes[parent] = dir_sizes.get(parent, 0) + size

        sorted_dirs = sorted(dir_sizes.items(), key=lambda x: -x[1])
        top10 = sorted_dirs[:10]
        if top10:
            details = [
                f"{d} - {_format_size(s)} ({s} bytes)"
                for d, s in top10
            ]
            self.add_result(
                SEVERITY_LOW, "Large directories", 1,
                "Top 10 largest directories by tracked size",
                details,
            )
            self._prompt("Large directories", details)

    def check_gitignore(self):
        gitignore_path = os.path.join(self.repo_path, ".gitignore")
        if not os.path.isfile(gitignore_path):
            self.add_result(
                SEVERITY_MEDIUM, "No .gitignore", 2,
                "No .gitignore file found in repository root",
                [],
            )

    def check_license(self):
        license_paths = ["LICENSE", "LICENSE.txt", "LICENSE.md",
                         "LICENSE.rst", "COPYING", "COPYING.txt",
                         "COPYING.md"]
        found = any(os.path.isfile(os.path.join(self.repo_path, lp))
                    for lp in license_paths)
        if not found:
            self.add_result(
                SEVERITY_MEDIUM, "No LICENSE", 1,
                "No LICENSE file found in repository root",
                [],
            )

    def run_all(self):
        if not self.check_git_repo():
            if self.json_output:
                print(json.dumps({"error": "Not a git repository", "repo_path": self.repo_path}))
            else:
                print(f"\n  {RED}Error: Not a git repository or git not installed{RESET}")
                print(f"  {self.repo_path} is not a valid git repository.\n")
            return

        self.gather_repo_info()

        if not self.json_output:
            print(f"\n  {BOLD}{CYAN}[*] GitShit - Repo Shame Scanner{RESET}")
            print(f"  {DIM}{'-' * 40}{RESET}")
            repo_display = self.repo_path
            if len(repo_display) > 70:
                repo_display = "..." + repo_display[-67:]
            print(f"  {BOLD}[+] Scanning:{RESET} {repo_display}")
            print(f"     {self.file_count} files, {self.commit_count} commits\n")

        checks = [
            ("Large files", self.check_large_files),
            ("Secrets", self.check_secrets),
            ("TODOs/FIXMEs", self.check_todos),
            (".env files", self.check_env_files),
            ("Binary files", self.check_binary_files),
            ("Merge conflicts", self.check_merge_conflicts),
            ("Empty/WIP commits", self.check_empty_commits),
            ("Large dirs", self.check_large_dirs),
            (".gitignore", self.check_gitignore),
            ("LICENSE", self.check_license),
        ]

        for name, check_func in checks:
            try:
                check_func()
            except Exception as e:
                self.vout(f"  {DIM}[{name}] check error: {e}{RESET}")

        if self.json_output:
            print(json.dumps({
                "repo_path": self.repo_path,
                "file_count": self.file_count,
                "commit_count": self.commit_count,
                "total_score": self.total_score,
                "results": self.results,
            }, indent=2))
            return

        self.print_summary()

    def print_summary(self):
        print(f"\n  {BOLD}{'-' * 40}{RESET}")
        print(f"  {BOLD}{CYAN}[~] Total Shame Score:{RESET} {BOLD}{self.total_score}/100{RESET}")

        grade = self.get_grade()
        if grade == "clean":
            print(f"     {GREEN}{BOLD}[~] Clean - Ship it!{RESET}")
        elif grade == "needs-work":
            print(f"     {YELLOW}{BOLD}[~] Needs work{RESET}")
        elif grade == "yikes":
            print(f"     {MAGENTA}{BOLD}[~] Yikes - Better clean this up{RESET}")
        else:
            print(f"     {RED}{BOLD}[~] BURN IT - Do not push this!{RESET}")
        print()

    def get_grade(self):
        if self.total_score <= 10:
            return "clean"
        elif self.total_score <= 30:
            return "needs-work"
        elif self.total_score <= 50:
            return "yikes"
        else:
            return "burn-it"


def main():
    parser = argparse.ArgumentParser(
        description="GitShit - Scan a git repo for embarrassing things before you publish it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gitshit.py
  gitshit.py --path /path/to/repo
  gitshit.py --json
  gitshit.py --verbose
  gitshit.py --no-interactive
        """,
    )
    parser.add_argument(
        "--path", default=".",
        help="Path to git repository (default: current directory)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--interactive", action="store_true", default=None,
        help="Enable interactive mode (default: auto based on TTY)",
    )
    parser.add_argument(
        "--no-interactive", action="store_false", dest="interactive",
        help="Disable interactive mode",
    )

    args = parser.parse_args()

    scanner = GitShitScanner(
        repo_path=args.path,
        verbose=args.verbose,
        json_output=args.json_output,
        interactive=args.interactive,
    )
    scanner.run_all()
    sys.exit(0 if scanner.total_score <= 10 else 1)


if __name__ == "__main__":
    main()
