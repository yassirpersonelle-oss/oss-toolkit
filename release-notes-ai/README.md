# release-notes-ai

**Stop writing release notes by hand.**

`release-notes-ai` is a Python CLI (stdlib only) that reads your git log between two tags and generates human-readable release notes with categorized changes, migration notices, and contributor shout-outs. Not just a commit list — actual release notes.

## Requirements

- Python 3.x
- Git repository using **Conventional Commits** format:

```
type(scope): description

type:       feat | fix | docs | perf | refactor | style | test | build | ci | chore | deps
breaking:   add ! before :  e.g. feat(api)!:
            or include BREAKING CHANGE: in commit body
migration:  include MIGRATION:, UPGRADE:, or DEPRECATED: in commit body
```

## Usage

```bash
# Basic — from last tag to HEAD
python release-notes-ai.py

# Custom range
python release-notes-ai.py --from v1.0.0 --to v2.0.0

# Output to file
python release-notes-ai.py -o CHANGELOG.md

# Different repo
python release-notes-ai.py --repo ../my-project

# Detailed template (includes dates and short hashes)
python release-notes-ai.py --template detailed

# Specify version header
python release-notes-ai.py --version "1.2.3"
```

### All options

| Argument         | Description                                        | Default                        |
|------------------|----------------------------------------------------|--------------------------------|
| `--from`         | Starting tag or commit                             | Last tag (or first commit)     |
| `--to`           | Ending tag or commit                               | HEAD                           |
| `--output` / `-o`| Output file                                        | stdout                         |
| `--repo`         | Path to git repository                             | Current directory              |
| `--version`      | Version header text                                | Tag name or "Unreleased"       |
| `--project-name` | Project name                                       | Repo directory basename        |
| `--template`     | `simple` or `detailed`                             | `simple`                       |

## Sample output

```markdown
# my-project

## v2.0.0

42 commits, 15 files changed, 1204+, 89-

## ⚠️ Breaking Changes

> [!ALERT]
> This release contains breaking changes. Please review before upgrading.

- **api**: remove deprecated v1 endpoints ([alice](https://github.com/alice))

## 🚀 Features

- **auth**: add OAuth2 PKCE flow ([bob](https://github.com/bob))
- **core**: support concurrent workers ([alice](https://github.com/alice))

## 🐛 Bug Fixes

- **parser**: handle empty input gracefully ([carol](https://github.com/carol))

## 👥 Contributors

- [alice](https://github.com/alice)
- [bob](https://github.com/bob)
- [carol](https://github.com/carol)
```

## How it works

1. Runs `git log --pretty=format:... --no-merges <from>..<to>`
2. Parses conventional commit messages
3. Categorizes into sections (breaking changes first, then features, fixes, etc.)
4. Detects breaking changes (`!` before `:` or `BREAKING CHANGE:` in body)
5. Extracts migration notices (`MIGRATION:`, `UPGRADE:`, `DEPRECATED:`)
6. Deduplicates contributors
7. Adds stats from `git diff --stat`
8. Outputs formatted Markdown

## License

MIT
