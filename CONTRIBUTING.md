# Contributing to OSS Toolkit

Thanks for stopping by! This monorepo has 30+ standalone CLI tools — pick one and improve it.

## Quick Setup

```bash
git clone https://github.com/yassirpersonelle-oss/oss-toolkit
cd oss-toolkit

# Each tool is a standalone directory — pick one
cd pristine/
python pristine.py --help
```

## How to Contribute

1. **Find something to do** — browse [open issues](https://github.com/yassirpersonelle-oss/oss-toolkit/issues) filtered by `good first issue`
2. **Fork and branch** — `git checkout -b fix/pristine-encoding`
3. **Write code** — all tools are stdlib-only, no new dependencies allowed
4. **Test locally** — `python tool-name/tool-name.py` with sample input
5. **Open a PR** — use the PR template, link the issue

## Adding a New Tool

1. Create a directory: `mkdir my-tool/`
2. Add `my-tool.py` (stdlib only, `#!/usr/bin/env python3`)
3. Add `README.md` with usage examples
4. Add entry in the root `README.md` tool table
5. Open a PR

## Code Guidelines

- **stdlib only** — no pip/npm dependencies. If you need something, implement it.
- `#!/usr/bin/env python3` at the top of every script
- Handle errors gracefully — don't crash, print useful messages
- Add `--help` output via `argparse`
- Keep it single-file for portability

## Questions?

Open a [discussion](https://github.com/yassirpersonelle-oss/oss-toolkit/discussions) or comment on an issue.
