# formula-fresh

**Your Homebrew tap, always up to date.**

## Why

Manually bumping formula versions in a Homebrew tap is tedious and easy to miss.
When upstream releases a new version, you have to:

1. Notice the release
2. Update the URL and version in your formula
3. Download the new tarball and compute the sha256
4. Commit and push

`formula-fresh` automates all of this. Point it at your tap and it will check every formula against its upstream source (GitHub Releases, PyPI, or crates.io), and open a PR whenever a new version is available.

## Usage

```bash
# Check all formulas in the current directory
python formula-fresh.py

# Check a specific tap
python formula-fresh.py --tap /path/to/homebrew-myformulas

# Preview what would change without pushing anything
python formula-fresh.py --dry-run --verbose

# JSON output for CI pipelines
python formula-fresh.py --json
```

### Options

| Flag | Description |
|------|-------------|
| `--tap PATH` | Path to your Homebrew tap repo (default: current directory) |
| `--dry-run` | Show what would change without creating branches or pushing |
| `--json` | Output results as JSON |
| `--verbose` | Print detailed progress for each API call and git operation |
| `--upstream NAME` | Check only a single formula (by partial name match) |

## How It Works

1. Finds all `.rb` files in the tap's `Formula/` directory
2. Parses each formula using regex to extract `url`, `version`, `sha256`, and `homepage`
3. Determines the upstream source from the URL:
   - **GitHub Releases** — `github.com/{owner}/{repo}/releases/download/…`
   - **PyPI** — `pypi.org/…`
   - **crates.io** — `crates.io/…`
4. Fetches the latest version from the upstream API
5. If a newer version exists, downloads the new source tarball to compute its sha256
6. Creates a branch, updates the formula, commits, and pushes

## Setting Up as a Cron Job

```bash
# Check daily at 8am UTC
0 8 * * * cd /path/to/your-tap && python /path/to/formula-fresh.py --verbose >> /var/log/formula-fresh.log 2>&1
```

## GitHub Actions

```yaml
name: Check for upstream updates
on:
  schedule:
    - cron: "0 8 * * *"
  workflow_dispatch:

jobs:
  check-updates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Run formula-fresh
        run: python formula-fresh.py --verbose --json

      - name: Create PRs for updates
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # formula-fresh pushes branches; this step opens PRs from them
          for branch in $(git branch -r --list 'origin/bump/*'); do
            gh pr create --fill --base main --head "$branch" || true
          done
```

## Supported Package Ecosystems

| Ecosystem | URL Pattern | API Used |
|-----------|------------|----------|
| GitHub Releases | `github.com/{owner}/{repo}/releases/download/…` | `api.github.com/repos/…/releases/latest` |
| Python (PyPI) | `pypi.org/…` | `pypi.org/pypi/{package}/json` |
| Rust (crates.io) | `crates.io/…` | `crates.io/api/v1/crates/{crate}` |

## Requirements

- Python 3.7+ (stdlib only, no dependencies)
- `git` on your PATH (for branch/commit/push operations)
- Network access to reach GitHub, PyPI, or crates.io APIs

## License

MIT
