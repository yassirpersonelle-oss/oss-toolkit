# bib-clean

**Clean BibTeX in one command**

BibTeX files grow messy fast with collaborative writing. `bib-clean` normalizes your `.bib` files by merging duplicates, fixing inconsistencies, and removing unused entries.

## Why?

When multiple people edit a BibTeX database, you inevitably get:
- Duplicate entries with the same DOI
- Inconsistent field formatting (DOIs with/without `https://doi.org/` prefix)
- Missing required fields
- Entries that were added but never actually cited
- Year mismatches between arXiv URLs and entry metadata

`bib-clean` fixes all of these in one pass.

## Usage

```bash
# Clean in place (overwrites input)
python bib-clean.py -i references.bib

# Write to a new file
python bib-clean.py -i references.bib -o cleaned.bib

# Output to stdout
python bib-clean.py -i references.bib -o -

# Get JSON output
python bib-clean.py -i references.bib --json

# Remove unused entries (scans .tex files for citations)
python bib-clean.py -i references.bib --remove-unused

# Normalize DOI fields
python bib-clean.py -i references.bib --fix-doi

# Combine options
python bib-clean.py -i references.bib --fix-doi --remove-unused --verbose
```

## Checks Performed

| Check | Description |
|-------|-------------|
| **Duplicate DOIs** | Finds entries sharing a DOI, merges them (keeps the entry with more fields) |
| **Duplicate citekeys** | Flags entries with identical citation keys |
| **Missing required fields** | Validates fields based on entry type (`@article`, `@inproceedings`, `@book`, etc.) |
| **DOI normalization** | Strips `https://doi.org/` prefix, ensures clean DOI identifier format |
| **Year consistency** | Flags year mismatches between arXiv URLs and entry year |
| **Encoding issues** | Detects non-UTF8 characters in entries |
| **Unused entries** | Removes bib entries not referenced in any `.tex` file in the same directory |

## Required Fields by Entry Type

- `@article`: author, title, journal, year
- `@inproceedings`: author, title, booktitle, year
- `@book`: author, title, publisher, year
- `@misc`: title

## Integration with LaTeX Workflow

Add to your LaTeX build pipeline:

```bash
# Before compiling
bib-clean -i references.bib --fix-doi --remove-unused

# Or as a pre-commit hook
bib-clean -i references.bib --fix-doi -o references.bib
git add references.bib
```

## Options

| Flag | Description |
|------|-------------|
| `-i, --input` | Input .bib file (required) |
| `-o, --output` | Output file (default: overwrite input) |
| `--json` | Output results as JSON |
| `--verbose` | Show detailed processing info |
| `--remove-unused` | Strip entries not cited in .tex files |
| `--fix-doi` | Normalize DOI field formatting |

## Requirements

Python 3.6+ (stdlib only, no external dependencies).
