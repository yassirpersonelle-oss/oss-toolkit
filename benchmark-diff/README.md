# ⚡ Benchmark Diff

**Never merge a performance regression again.**

Benchmark Diff is a GitHub Action + CLI tool that automatically benchmarks PR code against the base branch and posts results as a PR comment.

---

## Quick Start

1. Place benchmark files in `benchmarks/`:

```python
# benchmarks/example.py
import time

def bench_sleep_10ms():
    time.sleep(0.01)

def bench_sleep_50ms():
    time.sleep(0.05)
```

2. Add the action to your workflow:

```yaml
name: Benchmarks
on: [pull_request]
jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/benchmark-diff@v1
```

3. Merge only when you see 🟢 IMPROVEMENT or ⚪ NO CHANGE.

---

## Writing Your Own Benchmarks

- Files must match `bench_*.py` or `*_benchmark.py`.
- Functions must start with `bench_` or end with `_benchmark`.
- Each function takes no arguments and returns nothing — execution time is measured automatically.
- Use `time.sleep()` to simulate work, or call actual code from your project.

### Example

```python
# benchmarks/query_benchmark.py
from myapp import db

def bench_query_find():
    results = db.query("SELECT * FROM users WHERE active = 1")
    assert len(results) > 0
```

---

## CLI Usage

```bash
python benchmark-diff.py --benchmark-dir benchmarks/ --runs 20 --warmup 5
```

| Flag | Default | Description |
|------|---------|-------------|
| `--base-branch`, `-b` | `main` | Branch to compare against |
| `--benchmark-dir`, `-d` | `benchmarks/` | Directory with benchmark files |
| `--output`, `-o` | `benchmark-results.json` | Output file for JSON results |
| `--warmup` | `3` | Warmup iterations (discarded) |
| `--runs` | `10` | Timed iterations |
| `--format` | `markdown` | Output format: `text`, `json`, or `markdown` |

---

## Action Usage

```yaml
jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: your-org/benchmark-diff@v1
        with:
          benchmark-dir: 'benchmarks/'
          runs: '10'
          warmup: '3'
```

The action automatically comments on the PR with the benchmark diff report.

---

## Interpreting Results

### Verdicts

| Change | Icon | Verdict |
|--------|------|---------|
| > +5% slower | 🔴 | **REGRESSION** — Don't merge |
| -5% to +5% | ⚪ | **NO CHANGE** — Safe to merge |
| < -5% faster | 🟢 | **IMPROVEMENT** — Merge with confidence |

### Example Report

```
## ⚡ Benchmark Diff Report

| Benchmark | Base (ms) | PR (ms) | Change | Verdict |
|---|---|---|---|---|
| query.find | 12.4 | 15.3 | +23.4% | 🔴 REGRESSION |
| auth.login | 3.2 | 3.1 | -3.1% | ⚪ NO CHANGE |
| data.parse | 45.6 | 38.2 | -16.2% | 🟢 IMPROVEMENT |

⏱  Benchmarks run with 10 iterations, 3 warmup runs.
```

---

## Requirements

- Python 3.7+
- Git
- No external dependencies (stdlib only)
