# Contributing to mcp-discover

Thanks for considering contributing! mcp-discover is a stdlib-only Python CLI — the bar for contributing is low.

## Setup

```bash
git clone https://github.com/yassirpersonelle-oss/oss-toolkit
cd oss-toolkit/mcp-discover
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

## How to add a new language

1. Add discovery logic in a `discover_LANG` function
2. Register in `DISCOVERY` and `FILE_EXT_MAP` dicts
3. Add type mapping in `_parse_LANG_type`
4. Add test fixtures under `tests/fixtures/LANG/`
5. Update README language support table

## Running tests

```bash
python -m pytest tests/
```

## Code style

- Stdlib only — no pip dependencies
- Functions should handle errors gracefully (continue scanning on failure)
- Type hints encouraged but not required
- 4-space indentation
