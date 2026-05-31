# changelog-md

Zero-config Python CLI that reads conventional commit messages since the last git tag and generates a CHANGELOG.md.

## Requirements

- Git
- Python 3.6+

## Usage

```
python changelog-md.py
python changelog-md.py --stdout
python changelog-md.py --tag v1.0.0
python changelog-md.py -o CHANGES.md
```

## Options

| Option | Description |
|--------|-------------|
| `--tag` | Tag to start from (default: last tag from `git describe --tags --abbrev=0`) |
| `-o, --output` | Output file path (default: CHANGELOG.md) |
| `--repo-path` | Path to git repository (default: current directory) |
| `--stdout` | Print changelog to stdout instead of writing to file |
| `-v, --verbose` | Print summary information |

## Example output

```markdown
# Changelog

## [v1.2.0]

### Features
- **auth:** add OAuth2 login ([abc1234](https://github.com/yassir/oss-toolkit/commit/abc1234))
- **api:** implement rate limiting ([def5678](https://github.com/yassir/oss-toolkit/commit/def5678))

### Bug Fixes
- **ui:** fix button alignment ([ghi9012](https://github.com/yassir/oss-toolkit/commit/ghi9012))

### Chores
- bump dependencies ([jkl3456](https://github.com/yassir/oss-toolkit/commit/jkl3456))
```
