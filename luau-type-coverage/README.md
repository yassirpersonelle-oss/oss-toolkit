# luau-type-coverage

Track your Luau type adoption progress — like `nyc` (istanbul) but for Luau types.

## Why gradual typing needs visibility

Luau supports **gradual typing**: you can annotate a few functions with types today, add more tomorrow, and slowly migrate a codebase without breaking anything. The problem is **you can't see your progress**. Without a tool like this, teams have no way to know:

- How much of the codebase is actually typed
- Which files are lagging behind
- Whether the team is moving _toward_ or _away from_ full typing
- Whether a PR introduces untyped code that regresses coverage

luau-type-coverage gives you a single number — and a detailed breakdown — so you can set targets and track them over time.

## Installation

```bash
# Just download the script — no dependencies beyond Python 3.7+
curl -O https://raw.githubusercontent.com/.../luau-type-coverage.py
chmod +x luau-type-coverage.py
```

Or clone and run directly:

```bash
git clone https://github.com/.../luau-type-coverage.git
python luau-type-coverage.py --path ./src
```

## Usage

```bash
# Basic scan
python luau-type-coverage.py --path ./src

# JSON output (for dashboards / CI)
python luau-type-coverage.py --path ./src --json

# Enforce a minimum threshold (exit code 1 if below)
python luau-type-coverage.py --path ./src --threshold 70

# Per-file breakdown
python luau-type-coverage.py --path ./src --verbose
```

## What counts as "typed"

The tool classifies every function into one of three buckets:

| Category   | Criteria |
|------------|----------|
| **Typed**  | All parameters have type annotations AND the function has a return type, OR the function/line is marked `@checked`, OR the file has `--!strict` and every param is typed. Functions with no parameters but a return type also count as typed. |
| **Partial** | Some but not all parameters are typed, OR the file uses `--!strict` but parameters are mixed. |
| **Untyped** | No type annotations anywhere on the function. |

Additional signals that boost coverage:

- **`--!strict`** at the top of a file means the _file_ opts into strict type checking. Strict files are tracked separately and contribute to the overall strict-mode adoption rate.
- **`export type` / `type`** definitions count as type coverage — defining types is part of the migration.
- **`-- @checked`** comments on the line above a function mark it as fully typed (a Luau convention for external validation).

## Example output

```
📊 Luau Type Coverage Report — src/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  📁 Scanned: 47 files, 234 functions, 18 types defined

  ✅ Fully typed:    112 (47.9%)
  ⚠️  Partial:        68 (29.1%)
  ❌ Untyped:         54 (23.1%)

  📈 Strict mode:    18/47 files (38.3%)

  🎯 Overall coverage: 47.9%

  ⚠️  Below threshold of 50%
```

## How to improve your score

1. **Add `--!strict`** to files that are already mostly typed — this prevents new untyped code from sneaking in and counts toward strict-mode adoption.
2. **Tackle "partial" functions first** — they're the lowest-hanging fruit. Usually one or two missing annotations.
3. **Define exported types** with `export type` for your public API shapes.
4. **Set a CI threshold** (see below) and ratchet it up over time. Start at 30%, move to 50%, then 70%.
5. **Use `--verbose`** to find the worst files and assign them as cleanup tasks.

## CI integration

### GitHub Actions

```yaml
- name: Check Luau type coverage
  run: |
    python luau-type-coverage.py --path ./src --threshold 60 --json > coverage.json
- name: Upload coverage artifact
  uses: actions/upload-artifact@v4
  with:
    name: luau-type-coverage
    path: coverage.json
```

### Failing below threshold

The tool exits with code `1` when coverage is below `--threshold`, so it works as a gating check:

```bash
python luau-type-coverage.py --path ./src --threshold 70 || echo "Coverage too low!"
```

### Tracking over time

Save the JSON output to a file each CI run and compare:

```bash
python luau-type-coverage.py --path ./src --json > coverage-$(date +%Y-%m-%d).json
```

## License

MIT
