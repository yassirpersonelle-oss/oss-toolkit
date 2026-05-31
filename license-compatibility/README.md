# License Compatibility Checker

> Before you ship, check your licenses.

A Python CLI that scans your project's dependencies and checks if their licenses are compatible with your project's license. Many open-source projects accidentally inherit incompatible licenses (especially GPL/AGPL into MIT or Apache projects), exposing themselves to legal risk.

## Why license compatibility matters

When you depend on a library, its license becomes part of your project's legal obligations. Some licenses are **copyleft** — they require your project to adopt the same license if you distribute the combined work. Using a GPL-licensed dependency in an MIT project means you may be forced to release your entire project under GPL. This tool helps you catch these issues before you ship.

## Supported package managers

| File | Source | Resolution |
|---|---|---|
| `package.json` | npm | Fetches license from npm registry |
| `requirements.txt` | PyPI | Fetches license from PyPI JSON API |
| `Cargo.toml` | Cargo | Scans `[dependencies]` |
| `pyproject.toml` | Python | Scans `[project.dependencies]` and `[tool.poetry.dependencies]` |

## Usage

```bash
# Basic scan (auto-detects project license from LICENSE file or config)
python license-compatibility.py

# Specify project root
python license-compatibility.py --path /path/to/project

# Override project license
python license-compatibility.py --project-license MIT

# JSON output
python license-compatibility.py --json

# Verbose (show all deps including compatible)
python license-compatibility.py --verbose

# Only fail on warnings too (not just incompatible)
python license-compatibility.py --fail-on warning

# Never fail (show all results, exit 0)
python license-compatibility.py --fail-on all
```

## Exit codes

| `--fail-on` | Description |
|---|---|
| `incompatible` (default) | Exit 1 if any incompatible dependencies found |
| `warning` | Exit 1 if incompatible or warning dependencies found |
| `all` | Always exit 0 (informational only) |

## Compatibility matrix preview

| Project License | Compatible | Incompatible | Warning |
|---|---|---|---|
| MIT | MIT, Apache-2.0, BSD, ISC, Unlicense, CC0-1.0, Zlib | GPL-2.0, GPL-3.0, AGPL-3.0, EUPL-1.2, SSPL-1.0 | LGPL-2.1, LGPL-3.0, MPL-2.0, BSL-1.0 |
| Apache-2.0 | Apache-2.0, MIT, BSD, ISC, Unlicense, CC0-1.0 | GPL-2.0, AGPL-3.0, SSPL-1.0 | GPL-3.0, LGPL-2.1, LGPL-3.0, MPL-2.0 |
| GPL-3.0 | GPL-3.0, GPL-2.0, MIT, Apache-2.0, BSD | AGPL-3.0, SSPL-1.0 | LGPL-3.0, MPL-2.0 |
| GPL-2.0 | GPL-2.0, MIT, BSD | GPL-3.0, AGPL-3.0, Apache-2.0, SSPL-1.0 | LGPL-2.1, LGPL-3.0, MPL-2.0 |
| AGPL-3.0 | AGPL-3.0, GPL-3.0, GPL-2.0, MIT, Apache-2.0, BSD | SSPL-1.0, CC-BY-NC-4.0 | LGPL, MPL-2.0, EUPL-1.2, BSL-1.0 |
| LGPL-3.0 | LGPL-3.0, LGPL-2.1, GPL-2.0, GPL-3.0, MIT, Apache-2.0, BSD | AGPL-3.0, SSPL-1.0 | MPL-2.0, EUPL-1.2, BSL-1.0 |
| MPL-2.0 | MPL-2.0, MIT, Apache-2.0, BSD, LGPL, GPL-2.0, GPL-3.0 | AGPL-3.0, SSPL-1.0, CC-BY-NC-4.0 | EUPL-1.2, BSL-1.0 |
| BSD-3-Clause | MIT, Apache-2.0, BSD, ISC, Unlicense, CC0-1.0, Zlib | GPL-2.0, GPL-3.0, AGPL-3.0, SSPL-1.0, EUPL-1.2 | LGPL-2.1, LGPL-3.0, MPL-2.0, BSL-1.0 |
| Unlicense | MIT, Apache-2.0, BSD, Unlicense, CC0-1.0 | GPL-2.0, GPL-3.0, AGPL-3.0, SSPL-1.0, EUPL-1.2 | LGPL, MPL-2.0, BSL-1.0 |

## License auto-detection

The tool auto-detects your project license by checking (in order):

1. `LICENSE` file in the project root
2. `package.json` → `license` field
3. `pyproject.toml` → `[project] license` or `license = {text = "..."}`
4. `Cargo.toml` → `license` field

Override with `--project-license`.

## Adding custom compatibility rules

Edit the `COMPATIBILITY` dictionary at the top of `license-compatibility.py`:

```python
COMPATIBILITY["MyLicense"] = {
    "compatible": ["MIT", "Apache-2.0"],
    "incompatible": ["GPL-3.0-only"],
    "warning": ["LGPL-3.0-only"],
}
```

Then map your license text to the key in `CLEAN_LICENSE_MAP`.
