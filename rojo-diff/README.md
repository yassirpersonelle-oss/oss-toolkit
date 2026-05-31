# rojo-diff

Validate a Rojo `default.project.json` structure against the filesystem. Catch missing directories, missing Lua files, and class name typos before syncing.

## Why

Rojo sync failures are cryptic and painful — a single missing `init.luau`, a folder that doesn't exist on disk, or a typo like `ServerScripService` can break your entire Studio workflow. **rojo-diff** catches these issues early so you don't waste time debugging sync errors.

## Usage

```bash
# Auto-detect default.project.json in current directory
python rojo-diff.py

# Specify a project file
python rojo-diff.py -p mygame/default.project.json

# Verbose mode — prints the full tree structure
python rojo-diff.py --verbose

# JSON output (for CI / tooling)
python rojo-diff.py --json
```

## What it checks

| Check | Description |
|---|---|
| **Missing directories/files** | Every `$path` in the tree must exist on disk |
| **Missing `init.luau`** | Directories that map to scripts/services must contain `init.lua`/`init.luau` |
| **Class name typos** | Detects common mistakes like `ServerScripService` → `ServerScriptService`, `RepliicatedStorage` → `ReplicatedStorage`, `StarterPlay` → `StarterPlayer` |
| **Circular references** | Detects and handles circular references in the tree structure |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No errors found (warnings are OK) |
| `1` | Errors found — missing files, invalid JSON, or project file not found |

Use exit code `1` to block CI pipelines when the project is inconsistent.

## Requirements

Python 3.6+. No external dependencies — uses only the standard library (`json`, `os`, `argparse`, `sys`).
