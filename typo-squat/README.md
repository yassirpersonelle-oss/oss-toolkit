# typo-squat

A CLI tool that scans your project's dependencies and flags potential
typo-squatting packages.

## What is typo-squatting?

Typo-squatting is a supply-chain attack where malicious packages are published
with names that are easy to mistype (e.g. `requets` instead of `requests`).
Unsuspecting developers who make a typo when installing a dependency can
inadvertently pull in malware instead of the intended library.

## Usage

```bash
# Scan the current directory
python typo-squat.py

# Scan a specific project
python typo-squat.py --path /path/to/project

# JSON output for programmatic use
python typo-squat.py --json

# Verbose output with extra details
python typo-squat.py --verbose
```

## Expected output

```
Scanned 42 dependencies across 3 files. Found 2 potential typo-squats.

  HIGH  requestz  (requirements.txt)
       Type: known typo-squat  → Did you mean 'requests'?

  MEDIUM  numppy  (pyproject.toml)
       Type: suspicious pattern; repeated characters  → Did you mean 'numpy'?
```

## Supported file types

| File               | Ecosystem |
|--------------------|-----------|
| `package.json`     | npm       |
| `requirements.txt` | pip       |
| `Cargo.toml`       | cargo     |
| `Pipfile`          | pipenv    |
| `pyproject.toml`   | poetry    |

## How it works

1. Auto-detects dependency files in your project root.
2. Extracts each dependency name.
3. Checks each name against the built-in database of known typo-squats
   (`typo_db.py`).
4. Applies Levenshtein-distance fuzzy matching against popular packages.
5. Flags suspicious patterns (repeated characters, uncommon symbols, etc.).
6. Assigns a risk level: **HIGH** (confirmed typo-squat), **MEDIUM** (close
   match), **LOW** (suspicious pattern).

## Contributing to the database

Edit `typo_db.py` and add entries to the `KNOWN_TYPOS` dictionary:

```python
KNOWN_TYPOS = {
    "legitimatepackage": ["typo1", "typo2"],
    # ...
}
```

Then submit a pull request.
