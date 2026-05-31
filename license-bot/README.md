# License Bot

A GitHub Action that auto-adds SPDX license headers to new source files in pull requests.

## Usage

Create `.github/workflows/license-bot.yml`:

```yaml
name: License Bot
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  license-bot:
    runs-on: ubuntu-latest
    steps:
      - uses: your-org/license-bot@v1
        with:
          license-type: MIT
          year: '2026'
          author: 'Your Name'
```

## Supported License Types

- `MIT`
- `Apache-2.0`
- `GPL-3.0`
- `BSD-3-Clause`

## Supported File Types

| Comment Style   | Extensions                                                        |
|-----------------|-------------------------------------------------------------------|
| `# `            | .py, .rb, .sh, .bash, .zsh, .yaml, .yml, .dockerfile, .ini, .cfg, .toml |
| `// `           | .js, .ts, .jsx, .tsx, .rs, .go, .java, .c, .cpp, .h, .hpp, .swift, .kt, .dart, .zig |
| `/* */`         | .css, .scss, .less                                                |
| `-- `           | .lua, .sql                                                        |

## Skipped Files

- Binary files, minified files, lock files, .gitignore
- Files that already contain an SPDX header

## Inputs

| Input         | Required | Default | Description             |
|---------------|----------|---------|-------------------------|
| license-type  | No       | MIT     | SPDX license identifier |
| year          | No       | 2026    | Copyright year          |
| author        | Yes      | —       | Copyright holder        |
