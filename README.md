# OSS Toolkit

A collection of fast, useful open-source CLI tools for developers.

## General-Purpose Developer Tools

| Tool | Description |
|------|-------------|
| **pristine** | Strip comments, debug logs, and noise from code before pasting into LLMs |
| **keepalive-action** | GitHub Action to prevent cron-based workflows from being disabled after 60 days |
| **changelog-md** | Zero-config changelog generator from conventional commits |
| **typo-squat** | Dependency typo-squatting scanner |
| **gitshit** | Interactive repo shame scanner (large files, secrets, TODOs) |
| **license-bot** | GitHub Action to auto-add SPDX license headers to new files |
| **gh-draft** | Preview PR diffs before pushing |
| **dotfiles-sync** | Auto-watch and commit config changes |
| **env-doc** | Auto-generate .env.example from your codebase |
| **action-matrix-builder** | Smart build matrix generator for GitHub Actions |
| **repo-health** | Calculate a health score (0-100) for any public GitHub repo |
| **mcp-discover** | Auto-generate MCP server configs from any codebase |
| **dep-drift** | Detect dependency version drift and tech debt |
| **contributor-welcome** | Auto-label "good first issues" and generate CONTRIBUTING.md |
| **release-notes-ai** | Human-readable release notes from git diffs |
| **license-compatibility** | Scan transitive dependencies for license conflicts |
| **benchmark-diff** | Catch performance regressions in pull requests |
| **stack-trace-decoder** | Explain stack traces in plain English |
| **oss-metrics** | Generate a static HTML dashboard from GitHub API data |
| **gh-backup** | One-command backup of repos, issues, PRs, and releases |

## Niche-Specific Tools

| Tool | Niche | Description |
|------|-------|-------------|
| **gdext-stub** | Godot | Generate GDScript type stubs from .gdextension files |
| **image-dim** | Astro/static sites | Backfill width/height attributes to prevent CLS |
| **notebook-deadcode** | Jupyter/scientific Python | Find dead code cells in .ipynb notebooks |
| **migrate-lint** | Django | Lint migrations for production-breaking issues |
| **formula-fresh** | Homebrew | Auto-update Homebrew formulae when upstream releases |
| **bib-clean** | LaTeX/academia | Normalize, dedupe, and clean BibTeX entries |
| **image-slim** | Docker | Find wasted space in Docker images |
| **osm-diff** | OpenStreetMap | Human-readable changelog between OSM exports |
| **ansible-drift** | DevOps | Generate markdown drift reports from Ansible --check |
| **vim-doc-gen** | Vim/neovim | Auto-generate :help docs from plugin source code |

## Usage

Each tool lives in its own directory with a standalone script and README.

```bash
# General tools
python pristine/pristine.py file.py
python changelog-md/changelog-md.py
python gitshit/gitshit.py

# Niche tools
python gdext-stub/gdext-stub.py --input my_extension.gdextension
python migrate-lint/migrate-lint.py --path apps/
python bib-clean/bib-clean.py --input references.bib
```
