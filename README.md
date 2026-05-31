# OSS Toolkit

A collection of fast, useful open-source CLI tools for developers.

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

## Usage

Each tool lives in its own directory with a standalone script and README.

```bash
python pristine/pristine.py file.py
python changelog-md/changelog-md.py
python gitshit/gitshit.py
```
