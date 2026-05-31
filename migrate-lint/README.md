# migrate-lint

> Catch bad migrations before they catch you.

One bad migration = hours of downtime. `migrate-lint` scans your Django migration files for common patterns that cause production incidents — missing defaults, destructive SQL, dangerous renames, and more — and reports them before you run `migrate`.

## Usage

```bash
# Lint current directory (looks for **/migrations/*.py)
python migrate-lint.py

# Lint a specific directory
python migrate-lint.py --path /path/to/django/project

# Lint a specific migrations folder
python migrate-lint.py --migrations /path/to/app/migrations

# JSON output
python migrate-lint.py --json

# Verbose mode
python migrate-lint.py --verbose

# Strict mode (exit 1 on warnings too)
python migrate-lint.py --strict
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0    | No issues (or warnings only in non-strict mode) |
| 1    | Errors found, or warnings found in strict mode |
| 2    | Invalid arguments or directory not found |

## Rules

### Errors (will break production)

#### `destructive-sql` (ERROR)
**What**: `RunSQL` with `DROP`, `DELETE`, or `TRUNCATE` without `-- elidable` marker.

**Why it matters**: Non-elidable destructive SQL runs every time the migration is applied. If a migration is replayed (e.g. on a fresh database or after a reset), it silently destroys data.

**How to fix**:
- Add `-- elidable` as a SQL comment if the operation is safe to skip on replay
- Or use `RunSQL` with `reverse_sql` to make it reversible
- Or move destructive operations to a `RunPython` migration with proper guards

#### `missing-reverse-sql` (ERROR)
**What**: `RunSQL` without `reverse_sql` parameter.

**Why it matters**: Without reverse SQL, `migrate --reverse` or `migrate app_name zero` will fail. Rollbacks become impossible without manual intervention.

**How to fix**:
```python
migrations.RunSQL(
    sql="ALTER TABLE app_model ADD COLUMN new_col TEXT",
    reverse_sql="ALTER TABLE app_model DROP COLUMN new_col",
)
```

#### `not-null-no-default` (ERROR)
**What**: `AddField` with `null=False` and no `default=` or `preserve_default=False`.

**Why it matters**: Adding a NOT NULL column to a table with existing rows fails immediately because PostgreSQL (and most databases) cannot add a non-nullable column without a default.

**How to fix**:
```python
# Option 1: Add with a default
migrations.AddField(
    model_name="user",
    name="email",
    field=models.EmailField(default=""),
)

# Option 2: Add as nullable first, backfill, then alter
migrations.AddField(
    model_name="user",
    name="email",
    field=models.EmailField(null=True),
)
# ... RunPython to backfill ...
migrations.AlterField(
    model_name="user",
    name="email",
    field=models.EmailField(null=False),
)
```

### Warnings (likely problematic)

#### `dangerous-rename` (WARNING)
**What**: `RenameField` without a prior `AlterField` in the same migration.

**Why it matters**: During a deploy, old code is still running against the database. A `RenameField` immediately renames the column, causing the old code to crash with "column does not exist" errors.

**How to fix**:
```python
# Step 1: Add the new field (same migration)
migrations.AddField(
    model_name="user",
    name="new_name",
    field=models.CharField(max_length=100),
)

# Step 2: Copy data (RunPython)
# ...

# Step 3: Drop old field (next migration, after deploy)
```

Or use a multi-step deploy: add new field -> deploy -> copy data -> remove old field.

#### `remove-still-referenced` (WARNING)
**What**: `RemoveField` where the field name still appears in other migrations' `AddField` or `AlterField`.

**Why it matters**: Other migrations reference this field. Removing it may break the migration graph or cause failures when replaying migrations.

**How to fix**: Ensure the field is fully unused before removing it. Remove or update dependent migrations first.

#### `index-huge-table` (WARNING)
**What**: `AddIndex` without a `table_size` hint.

**Why it matters**: Creating an index on a large table (millions of rows) without `CONCURRENTLY` can lock the table for minutes or hours.

**How to fix**:
- Use `AddIndexConcurrently` with `atomic=False` (requires `--atomic=off` in migration)
- Or schedule index creation during a maintenance window
- Consider adding a `table_size` keyword as documentation

#### `duplicate-number` (WARNING)
**What**: Multiple migrations with the same numeric prefix in the same app.

**Why it matters**: Django applies migrations in order. Duplicate numbers create ambiguity and can cause incorrect execution order.

**How to fix**: Rename one of the conflicting migrations with a unique number, or use `squashmigrations`.

### Info (style issues)

#### `runpython-no-reverse` (INFO)
**What**: `RunPython` without `reverse_code=migrations.RunPython.noop`.

**Why it matters**: The migration becomes non-reversible. `migrate --reverse` will skip it or fail depending on the Django version.

**How to fix**:
```python
migrations.RunPython(
    my_forward_function,
    reverse_code=migrations.RunPython.noop,
)
```

#### `empty-migration` (INFO)
**What**: Migration file with an empty `operations` list.

**Why it matters**: Usually created by mistake. Adds noise to the migration graph.

**How to fix**: Delete the file if it serves no purpose, or add the intended operations.

#### `missing-dependencies` (INFO)
**What**: Migration without a `dependencies` list.

**Why it matters**: Django requires `dependencies` to determine migration order. Missing dependencies can cause incorrect execution.

**How to fix**: Add the `dependencies` list:
```python
dependencies = [
    ("myapp", "0001_initial"),
]
```

## JSON Output

With `--json`, output is a structured JSON object:

```json
{
  "scan_path": "/path/to/project",
  "migrations_scanned": 12,
  "errors": 1,
  "warnings": 2,
  "info": 0,
  "issues": [
    {
      "file": "users/migrations/0012_add_email.py",
      "line": 4,
      "rule": "not-null-no-default",
      "severity": "error",
      "message": "AddField 'email' with null=False, no default — will fail on existing rows"
    }
  ]
}
```

## CI Integration

```yaml
# GitHub Actions example
- name: Lint migrations
  run: python migrate-lint.py --path . --strict --json > migration-report.json
```

```bash
# Pre-commit hook
python migrate-lint.py --path . --strict
```

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
