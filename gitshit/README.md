# 🔍 GitShit

**Before you publish that repo... run this.**

GitShit is a zero-dependency Python CLI that scans your git repository for everything embarrassing, dangerous, or just plain sloppy before you push it to the world. It finds committed secrets, giant binaries, TODO spaghetti, merge conflict oopsie-doodles, and more.

```
$ gitshit --path ~/projects/my-repo

  🔍 GitShit - Repo Shame Scanner
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📁 Scanning: /home/you/projects/my-repo (418 files, 142 commits)

  🚨 CRITICAL (score: 10): Potential secrets/credentials found (1 matches)
  ⚠️  HIGH (score: 15): Binary files committed (5 found, 187MB total)
  📌 MEDIUM (score: 12): TODO/FIXME/HACK/BUG/XXX comments (12 found)
  📌 MEDIUM (score: 2): No .gitignore file found in repository root

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📊 Total Shame Score: 48/100 - 😬 Yikes - Better clean this up
```

## Installation

Drop `gitshit.py` anywhere on your `$PATH`. Requires **Python 3.6+** and **git**. That's it — no pip install, no dependencies, no nonsense.

```bash
# Clone or download gitshit.py (~500 lines, stdlib only)
chmod +x gitshit.py
./gitshit.py
```

## Usage

```bash
# Scan the current directory
gitshit.py

# Scan a specific repo
gitshit.py --path /path/to/repo

# Get JSON output (for CI, scripts, or tooling)
gitshit.py --json | jq '.total_score'

# Verbose mode — see every finding inline
gitshit.py --verbose

# Disable interactive prompts (useful in CI)
gitshit.py --no-interactive
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--path` | `.` (cwd) | Path to the git repository |
| `--json` | off | Output results as JSON |
| `--verbose`, `-v` | off | Show detailed output for each check |
| `--interactive` | auto (TTY) | Ask before showing details (auto-detected) |
| `--no-interactive` | off | Skip all prompts |

## What It Checks

### 🚨 CRITICAL (fix these now)

| Check | Score | What it looks for |
|-------|-------|-------------------|
| **Secrets** | 10 pts each | `password =`, `secret =`, `api_key =`, `token =`, `-----BEGIN`, AWS keys (`AKIA...`), GitHub tokens (`ghp_`, `gho_`, `ghu_`), OpenAI keys (`sk-...`) in any tracked file |
| **Merge conflicts** | 8 pts each | `<<<<<<<`, `=======`, `>>>>>>>` left in any tracked file |
| **.env files** | 8 pts | Committed `.env` or `.env.*` files in git tracking |

### ⚠️ HIGH (should fix)

| Check | Score | What it looks for |
|-------|-------|-------------------|
| **Large files** | 5 pts each | Tracked files over **10 MB** |
| **Binary files** | 3 pts each | Committed `.exe`, `.dll`, `.so`, `.zip`, `.psd`, `.iso`, `.jar`, `.mp4`, etc. |

### 📌 MEDIUM (nice to fix)

| Check | Score | What it looks for |
|-------|-------|-------------------|
| **TODO/FIXME/HACK/BUG/XXX** | 1 pt each | Leftover markers in source code |
| **No .gitignore** | 2 pts | Missing `.gitignore` in repo root |
| **No LICENSE** | 1 pt | Missing license file |

### ℹ️ INFO (for your awareness)

| Check | Score | What it shows |
|-------|-------|---------------|
| **Large dirs** | 1 pt | Top 10 directories by total tracked file size |
| **WIP commits** | 1 pt each | Empty, "wip", "Initial commit", or meaningless commit messages |
| **Large files (1-10 MB)** | 0 pts | Tracked files over 1 MB (informational) |

## Scoring Guide

```
Score      | Grade       | Verdict
-----------+-------------+-------------------------------
0–10       | 🧼 Clean    | Ship it. You're an adult.
11–30      | 🧹 Needs work | Tidy up before pushing.
31–50      | 😬 Yikes    | Your repo needs an intervention.
50+        | 🔥 BURN IT  | Do not push. Do not pass Go.
```

JSON output includes `total_score` for easy CI integration:

```bash
# Fail CI on shame
if [ $(gitshit.py --json | jq '.total_score') -gt 30 ]; then
  echo "🔥 Shame score too high!"
  exit 1
fi
```

## Why "GitShit"?

Because every repo has some. This tool just helps you find it before your coworkers, the internet, or (worst of all) a security auditor does.

## License

MIT. Or don't. I'm a README, not a cop.
