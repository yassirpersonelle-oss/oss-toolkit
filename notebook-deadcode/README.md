# notebook-deadcode

Clean up your Jupyter notebooks automatically.

Notebooks grow indefinitely. What starts as a clean exploration becomes 200+ cells of dead imports, unused variables, orphan computations, and duplicated code. `notebook-deadcode` identifies and optionally removes dead cells so you can keep your notebooks maintainable.

## Usage

```bash
# Analyze a single notebook
python notebook-deadcode.py --path notebook.ipynb

# Analyze all notebooks in a directory
python notebook-deadcode.py --path ./notebooks/

# JSON output
python notebook-deadcode.py --path notebook.ipynb --json

# Verbose details
python notebook-deadcode.py --path notebook.ipynb --verbose

# Auto-remove dead cells
python notebook-deadcode.py --path notebook.ipynb --fix
```

## How Detection Works

All analysis is **forward-looking** — a cell is only flagged if the variable, import, or definition is never referenced in any subsequent cell. This prevents false positives where early cells feed into later ones.

### Detection Categories

| Category | What it finds |
|---|---|
| **Unused imports** | `import` statements where the imported name never appears in any later cell |
| **Unreferenced variables** | Assignments like `x = ...` where `x` is never used downstream |
| **Unused functions** | `def` blocks where the function is never called later |
| **Comment-only cells** | Cells containing only `#` comments and blank lines |
| **Repeated cells** | Two or more cells with identical or nearly identical code (≥90% similarity) |
| **Orphan cells** | Cells that compute without assigning to a variable, importing, or producing display output |

### Scoring

```
📊 Summary: 42 code cells, 12 dead (28.6%)
```

## Important

- **Forward-only analysis** prevents false positives — variables imported in cell 1 and used in cell 5 won't be flagged
- **stdlib only** — no dependencies beyond Python 3.6+
- **Reads nbformat 4** `.ipynb` files
- **Non-destructive** by default — use `--fix` to actually remove cells (a backup is recommended)
