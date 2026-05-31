#!/usr/bin/env python3
"""Benchmark diff: compare PR performance against a base branch."""

import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import textwrap
import time


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark PR performance vs base branch"
    )
    parser.add_argument(
        "--base-branch", "-b",
        default="main",
        help="Base branch to compare against (default: main)",
    )
    parser.add_argument(
        "--benchmark-dir", "-d",
        default="benchmarks/",
        help="Directory containing benchmark files (default: benchmarks/)",
    )
    parser.add_argument(
        "--output", "-o",
        default="benchmark-results.json",
        help="Output JSON file (default: benchmark-results.json)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Number of warmup iterations (default: 3)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of timed iterations (default: 10)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    return parser.parse_args(argv)


def discover_benchmarks(benchmark_dir):
    """Find all benchmark functions in Python files under benchmark_dir."""
    pattern = os.path.join(benchmark_dir, "**", "bench_*.py")
    bench_files = glob.glob(pattern, recursive=True)
    pattern2 = os.path.join(benchmark_dir, "**", "*_benchmark.py")
    bench_files.extend(glob.glob(pattern2, recursive=True))

    if not bench_files:
        return {}

    benchmarks = {}
    for filepath in sorted(bench_files):
        spec = importlib.util.spec_from_file_location(
            "bench_module", filepath
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            continue

        for attr_name in dir(module):
            func = getattr(module, attr_name)
            if not callable(func):
                continue
            if attr_name.startswith("bench_") or attr_name.endswith("_benchmark"):
                # Use a qualified name including the file stem for disambiguation
                stem = os.path.splitext(os.path.basename(filepath))[0]
                key = f"{stem}.{attr_name}"
                benchmarks[key] = func

    return benchmarks


def time_benchmark(func, warmup, runs):
    """Time a benchmark function with warmup and timed runs."""
    for _ in range(warmup):
        func()

    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        timings.append((end - start) * 1000)  # Convert to ms

    return timings


def compute_stats(timings):
    """Compute min, max, avg, median, stddev from a list of timings (ms)."""
    if not timings:
        return {"min": 0, "max": 0, "avg": 0, "median": 0, "stddev": 0}
    avg = statistics.mean(timings)
    median = statistics.median(timings)
    stddev = statistics.stdev(timings) if len(timings) > 1 else 0.0
    return {
        "min": round(min(timings), 4),
        "max": round(max(timings), 4),
        "avg": round(avg, 4),
        "median": round(median, 4),
        "stddev": round(stddev, 4),
        "timings": timings,
    }


def run_all_benchmarks(benchmarks, warmup, runs):
    """Run a dict of benchmark functions and return results."""
    results = {}
    for name, func in benchmarks.items():
        try:
            timings = time_benchmark(func, warmup, runs)
            results[name] = compute_stats(timings)
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def compute_change(base_val, pr_val):
    """Compute percentage change from base to PR. ((pr - base) / base) * 100."""
    if base_val == 0:
        return 0.0
    return ((pr_val - base_val) / abs(base_val)) * 100


def compare_results(base_results, pr_results, metric="avg"):
    """Compare PR results against base and return comparison dicts."""
    comparisons = []
    all_keys = sorted(set(base_results.keys()) | set(pr_results.keys()))
    for key in all_keys:
        base = base_results.get(key, {})
        pr = pr_results.get(key, {})

        if "error" in base or "error" in pr:
            comparisons.append({
                "benchmark": key,
                "base_error": base.get("error"),
                "pr_error": pr.get("error"),
                "verdict": "ERROR",
            })
            continue

        if not base or not pr:
            comparisons.append({
                "benchmark": key,
                "base": base,
                "pr": pr,
                "change_pct": None,
                "verdict": "MISSING",
            })
            continue

        base_val = base.get(metric, 0)
        pr_val = pr.get(metric, 0)
        change_pct = compute_change(base_val, pr_val)

        if change_pct > 5:
            verdict = "REGRESSION"
        elif change_pct < -5:
            verdict = "IMPROVEMENT"
        else:
            verdict = "NO CHANGE"

        comparisons.append({
            "benchmark": key,
            "base": base_val,
            "pr": pr_val,
            "change_pct": round(change_pct, 2),
            "base_stats": base,
            "pr_stats": pr,
            "verdict": verdict,
        })

    return comparisons


def format_markdown(comparisons, runs, warmup):
    """Render comparison results as a markdown table."""
    lines = ["## ⚡ Benchmark Diff Report", "", "| Benchmark | Base (ms) | PR (ms) | Change | Verdict |", "|---|---|---|---|---|"]
    for c in comparisons:
        if c.get("verdict") == "ERROR":
            lines.append(f"| {c['benchmark']} | ERROR | ERROR | — | ❌ ERROR |")
            continue
        if c.get("verdict") == "MISSING":
            lines.append(f"| {c['benchmark']} | — | — | — | ⚪ MISSING |")
            continue

        base_str = f"{c['base']:.2f}"
        pr_str = f"{c['pr']:.2f}"
        change_str = f"{c['change_pct']:+.2f}%"

        if c["verdict"] == "REGRESSION":
            verdict_str = "🔴 REGRESSION"
        elif c["verdict"] == "IMPROVEMENT":
            verdict_str = "🟢 IMPROVEMENT"
        else:
            verdict_str = "⚪ NO CHANGE"

        lines.append(f"| {c['benchmark']} | {base_str} | {pr_str} | {change_str} | {verdict_str} |")

    lines.append("")
    lines.append(f"⏱  Benchmarks run with {runs} iterations, {warmup} warmup runs.")
    return "\n".join(lines)


def format_text(comparisons, runs, warmup):
    """Render comparison results as plain text."""
    lines = ["Benchmark Diff Report", "=" * 40, ""]
    for c in comparisons:
        if c.get("verdict") == "ERROR":
            lines.append(f"[ERROR] {c['benchmark']}: error running benchmark")
            continue
        if c.get("verdict") == "MISSING":
            lines.append(f"[MISSING] {c['benchmark']}: only present in one branch")
            continue

        lines.append(f"{c['benchmark']}: Base={c['base']:.2f}ms PR={c['pr']:.2f}ms Change={c['change_pct']:+.2f}% ({c['verdict']})")
    lines.append("")
    lines.append(f"Benchmarks run with {runs} iterations, {warmup} warmup runs.")
    return "\n".join(lines)


def save_json(results, output_path):
    """Save results dict to a JSON file."""
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)


def git(command, check=True):
    """Run a git command and return stdout."""
    import subprocess
    result = subprocess.run(
        ["git"] + command.split(),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(command)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main(argv=None):
    args = parse_args(argv)

    # --- Git operations ---
    has_stash = False
    original_branch = None

    try:
        # Check if we're in a git repo
        try:
            original_branch = git("rev-parse --abbrev-ref HEAD")
        except RuntimeError:
            print("Error: not a git repository", file=sys.stderr)
            sys.exit(1)

        # Stash dirty working tree
        status = git("status --porcelain")
        if status:
            git("stash push --include-untracked --message benchmark-diff-stash")
            has_stash = True

        # Checkout base branch and run benchmarks
        git(f"checkout {args.base_branch}")
        base_benchmarks = discover_benchmarks(args.benchmark_dir)
        if not base_benchmarks:
            print(f"No benchmark files found in '{args.benchmark_dir}' on branch '{args.base_branch}'", file=sys.stderr)
            git(f"checkout {original_branch}")
            if has_stash:
                git("stash pop")
            sys.exit(1)

        base_results = run_all_benchmarks(base_benchmarks, args.warmup, args.runs)
        save_json(base_results, "base-results.json")

        # Checkout original branch and run benchmarks
        git(f"checkout {original_branch}")
        pr_benchmarks = discover_benchmarks(args.benchmark_dir)
        if not pr_benchmarks:
            print(f"No benchmark files found in '{args.benchmark_dir}' on current branch", file=sys.stderr)
            git(f"checkout {original_branch}")
            if has_stash:
                git("stash pop")
            sys.exit(1)

        pr_results = run_all_benchmarks(pr_benchmarks, args.warmup, args.runs)
        save_json(pr_results, args.output)

    except RuntimeError as e:
        print(f"Git error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Restore original state
        if has_stash:
            try:
                git("stash pop")
            except RuntimeError:
                pass

    # --- Compare ---
    comparisons = compare_results(base_results, pr_results)

    if args.format == "json":
        output_data = {
            "comparisons": comparisons,
            "runs": args.runs,
            "warmup": args.warmup,
        }
        print(json.dumps(output_data, indent=2))
    elif args.format == "text":
        print(format_text(comparisons, args.runs, args.warmup))
    else:
        print(format_markdown(comparisons, args.runs, args.warmup))


if __name__ == "__main__":
    main()
