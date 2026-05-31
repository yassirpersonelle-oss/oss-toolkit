# dep-drift

> npm audit tells you about CVEs. dep-drift tells you about **tech debt**.

`dep-drift` is a Python CLI that detects when your pinned dependencies have drifted significantly behind latest versions, with a security-aware scoring system. Unlike `npm audit` (which only flags known CVEs), `dep-drift` tells you "you're 3 major versions behind" and calculates your tech debt as a single drift score.

## Usage

```bash
# Scan current directory
python dep-drift.py

# Scan a specific project
python dep-drift.py --path /path/to/project

# JSON output (for piping into jq, CI, etc.)
python dep-drift.py --json

# Verbose mode (shows which files were found/not found)
python dep-drift.py --verbose

# Set a custom drift threshold (exit code 1 if exceeded)
python dep-drift.py --threshold 30
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0`  | Total drift score < threshold (default: 50) |
| `1`  | Total drift score ≥ threshold |

## Supported Package Managers

| File | Registry | Notes |
|------|----------|-------|
| `package.json` | npm | `dependencies`, `devDependencies`, `peerDependencies` |
| `requirements.txt` | PyPI | Lines with `==`, `>=`, `~=`, etc. |
| `pyproject.toml` | PyPI | `[project] dependencies` and `[tool.poetry.dependencies]` |
| `Pipfile` | PyPI | `[packages]` and `[dev-packages]` |
| `Cargo.toml` | crates.io | `[dependencies]` section |

## Scoring Methodology

Each dependency gets a **drift score** based on how many versions behind it is:

- **Major version behind** × 10 points
- **Minor version behind** × 3 points
- **Patch version behind** × 1 point
- **Range pin** (`*`, `>=`, etc.): +20 points (implicitly drifting)
- **Deprecated package**: +50 points

### Severity Tiers

| Severity | Criteria |
|----------|----------|
| 🔴 **Critical** | Known CVEs OR >2 major versions behind |
| ⚠️ **Moderate** | Any positive drift score |
| ✅ **Up to date** | Same version as latest |

### Threshold

The default threshold is **50**. If the total drift score across all dependencies exceeds this, `dep-drift` exits with code 1 — suitable for CI pipelines to fail on accumulated dependency tech debt.

## Requirements

- Python 3.7+ (stdlib only; no pip dependencies)
- Internet access for registry API calls
