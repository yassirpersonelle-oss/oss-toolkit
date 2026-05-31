#!/usr/bin/env python3
"""dep-drift: Detect when pinned dependencies have drifted behind latest versions."""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse

USER_AGENT = "dep-drift/1.0"
CRITICAL_THRESHOLD = 50


# ── helpers ──────────────────────────────────────────────────────────────────

def parse_version(v: str):
    """Parse a semver string into (major, minor, patch). Returns None on failure."""
    v = v.strip().lstrip("v=^~")
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", v)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or "0"))


def version_diff(pinned: tuple, latest: tuple):
    """Return (major_behind, minor_behind, patch_behind)."""
    pmj, pmn, pp = pinned
    lmj, lmn, lp = latest
    major = max(0, lmj - pmj)
    minor = max(0, lmn - pmn) if lmj == pmj else lmn
    patch = max(0, lp - pp) if lmj == pmj and lmn == pmn else lp
    return major, minor, patch


def drift_score(major, minor, patch, is_range=False, deprecated=False):
    score = major * 10 + minor * 3 + patch * 1
    if is_range:
        score += 20
    if deprecated:
        score += 50
    return score


def fetch_json(url: str, headers: dict = None):
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": str(e)}


# ── file parsers ─────────────────────────────────────────────────────────────

def parse_package_json(path: str):
    """Parse npm-style dependencies from package.json."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    deps = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name, ver in data.get(section, {}).items():
            deps[name] = ver
    return deps


def parse_requirements_txt(path: str):
    """Parse requirements.txt lines."""
    deps = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            parts = re.split(r"[=<>!~]+", line, maxsplit=1)
            name = parts[0].strip()
            ver = parts[1].strip() if len(parts) > 1 else "*"
            deps[name.lower()] = ver
    return deps


def parse_cargo_toml(path: str):
    """Parse [dependencies] from Cargo.toml (basic TOML-free extraction)."""
    deps = {}
    in_section = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("[dependencies"):
                in_section = True
                continue
            if in_section and stripped.startswith("["):
                break
            if in_section and "=" in stripped and not stripped.startswith("#"):
                parts = stripped.split("=", 1)
                name = parts[0].strip()
                ver = parts[1].strip().strip('", ')
                deps[name] = ver
    return deps


def parse_pyproject_toml(path: str):
    """Parse dependencies from pyproject.toml (lightweight, no toml lib)."""
    deps = {}
    content = open(path, encoding="utf-8").read()

    # [project] dependencies as list of strings
    m = re.search(r"\[project\]", content)
    if m:
        after = content[m.end():]
        in_block = None
        for line in after.splitlines():
            if line.strip().startswith("[") and "dependencies" not in line:
                break
            if "dependencies" in line and "=" in line:
                in_block = "inline" if "[" in line else None
                continue
            if in_block == "inline":
                break
            line = line.strip()
            if line.startswith("[") and not line.startswith("[tool"):
                break
            if line.startswith('"') or line.startswith("'"):
                val = line.strip('", ')
                parts = re.split(r"([><=!~]+)", val, maxsplit=1)
                name = parts[0].strip()
                ver = parts[1] + parts[2].strip() if len(parts) > 2 else "*"
                deps[name.lower()] = ver

    # [tool.poetry.dependencies]
    m = re.search(r"\[tool\.poetry\.dependencies\]", content)
    if m:
        after = content[m.end():]
        for line in after.splitlines():
            if line.strip().startswith("[") and "tool.poetry" not in line:
                break
            if "=" in line and not line.strip().startswith("#") and not line.strip().startswith("python"):
                parts = line.split("=", 1)
                name = parts[0].strip()
                raw = parts[1].strip()
                if raw.startswith("^") or raw.startswith("~"):
                    ver = raw
                elif raw.startswith('"') or raw.startswith("'"):
                    ver = raw.strip('"\'')
                else:
                    ver = raw
                deps[name.lower()] = ver

    return deps


def parse_pipfile(path: str):
    """Parse [packages] and [dev-packages] from Pipfile."""
    deps = {}
    in_section = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("["):
                in_section = stripped.lower()
                continue
            if in_section in ("[packages]", "[dev-packages]") and "=" in stripped:
                parts = stripped.split("=", 1)
                name = parts[0].strip()
                ver = parts[1].strip().strip('"\'')
                deps[name.lower()] = ver
    return deps


# ── registry lookups ─────────────────────────────────────────────────────────

def lookup_npm(name: str):
    url = f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='')}/latest"
    data = fetch_json(url)
    if "_error" in data:
        return None, data["_error"]
    version = data.get("version", "")
    deprecated = data.get("deprecated") is not None
    return version, deprecated


def lookup_pypi(name: str):
    url = f"https://pypi.org/pypi/{urllib.parse.quote(name, safe='')}/json"
    data = fetch_json(url)
    if "_error" in data:
        return None, None, data["_error"]
    info = data.get("info", {})
    version = info.get("version", "")
    deprecated = info.get("deprecated") is not None
    # CVE count from pypi (no native API; use info message as placeholder)
    cves = data.get("vulnerabilities", [])
    return version, deprecated, cves


def lookup_crates(name: str):
    url = f"https://crates.io/api/v1/crates/{urllib.parse.quote(name, safe='')}"
    data = fetch_json(url, headers={"Accept": "application/json"})
    if "_error" in data:
        return None, data["_error"]
    crate = data.get("crate", {})
    version = crate.get("max_stable_version", "")
    return version, False


# ── main logic ───────────────────────────────────────────────────────────────

DEP_FILE_HANDLERS = {
    "package.json": ("npm", parse_package_json),
    "requirements.txt": ("pypi", parse_requirements_txt),
    "Cargo.toml": ("cargo", parse_cargo_toml),
    "pyproject.toml": ("pypi", parse_pyproject_toml),
    "Pipfile": ("pypi", parse_pipfile),
}


def resolve_latest(name, registry):
    if registry == "npm":
        ver, dep = lookup_npm(name)
        return ver, dep, []
    elif registry == "pypi":
        ver, dep, cves = lookup_pypi(name)
        return ver, dep, cves or []
    elif registry == "cargo":
        ver, dep = lookup_crates(name)
        return ver, dep, []
    return None, False, []


def scan_project(path: str, verbose: bool):
    results = []
    total_imports = 0
    for filename, (registry, parser) in DEP_FILE_HANDLERS.items():
        filepath = os.path.join(path, filename)
        if not os.path.isfile(filepath):
            if verbose:
                print(f"  [ ] {filename} — not found", file=sys.stderr)
            continue
        if verbose:
            print(f"  [x] {filename} — found", file=sys.stderr)
        deps = parser(filepath)
        if not deps:
            continue
        for dep_name, pinned_raw in deps.items():
            total_imports += 1
            # check if it's a range
            is_range = pinned_raw.strip() in ("*", "") or pinned_raw.strip().startswith(">=")

            pinned_ver = parse_version(pinned_raw)
            latest_ver, deprecated, cves = resolve_latest(dep_name, registry)

            major = minor = patch = 0
            if pinned_ver and latest_ver:
                latest_parsed = parse_version(latest_ver)
                if latest_parsed:
                    major, minor, patch = version_diff(pinned_ver, latest_parsed)
            elif pinned_ver is None:
                major = 99

            score = drift_score(major, minor, patch, is_range, deprecated)
            cve_count = len(cves) if isinstance(cves, list) else 0

            is_critical = cve_count > 0 or major > 2

            results.append({
                "file": filename,
                "name": dep_name,
                "pinned": pinned_raw,
                "pinned_parsed": f"{pinned_ver[0]}.{pinned_ver[1]}.{pinned_ver[2]}" if pinned_ver else pinned_raw,
                "latest": latest_ver or "unknown",
                "major_behind": major,
                "minor_behind": minor,
                "patch_behind": patch,
                "drift": score,
                "deprecated": deprecated,
                "is_range": is_range,
                "cves": cve_count,
                "critical": is_critical,
            })
    return results, total_imports


# ── output ───────────────────────────────────────────────────────────────────

def format_output(results, total_deps, total_files, json_output: bool):
    if json_output:
        return json.dumps({
            "deps": results,
            "totalDeps": total_deps,
            "totalFiles": total_files,
        }, indent=2)
    return _pretty_output(results, total_deps, total_files)


def _pretty_output(results, total_deps, total_files):
    lines = []
    lines.append(f"\U0001f4e6 dep-drift report: {os.getcwd()}")
    lines.append("\u2501" * 47)

    critical = [r for r in results if r["critical"]]
    moderate = [r for r in results if not r["critical"] and r["drift"] > 0]
    up_to_date = [r for r in results if r["drift"] == 0]

    if critical:
        lines.append("")
        lines.append("\U0001f534 CRITICAL DRIFT")
        for r in critical:
            cve_str = f" | {r['cves']} CVEs" if r["cves"] else ""
            parts = []
            if r["major_behind"]:
                parts.append(f"{r['major_behind']} major")
            if r["minor_behind"]:
                parts.append(f"{r['minor_behind']} minor")
            if r["patch_behind"]:
                parts.append(f"{r['patch_behind']} patch")
            behind = ", ".join(parts) + " behind" if parts else "range lock"
            lines.append(f"  {r['name']} ({r['file']}) {r['pinned_parsed']} \u2192 {r['latest']}")
            lines.append(f"    {behind} | drift: {r['drift']}{cve_str}")
            if r["deprecated"]:
                lines.append(f"    \u26a0\ufe0f DEPRECATED")
        lines.append("")

    if moderate:
        lines.append("\u26a0\ufe0f  MODERATE DRIFT")
        for r in moderate:
            parts = []
            if r["major_behind"]:
                parts.append(f"{r['major_behind']} major")
            if r["minor_behind"]:
                parts.append(f"{r['minor_behind']} minor")
            if r["patch_behind"]:
                parts.append(f"{r['patch_behind']} patch")
            behind = ", ".join(parts) + " behind"
            lines.append(f"  {r['name']} ({r['file']}) {r['pinned_parsed']} \u2192 {r['latest']}")
            lines.append(f"    {behind} | drift: {r['drift']}")
        lines.append("")

    if up_to_date:
        lines.append("\u2705 UP TO DATE")
        for r in up_to_date:
            if r["patch_behind"]:
                lines.append(f"  {r['name']} {r['pinned_parsed']} \u2192 {r['latest']} (patch behind)")
            else:
                lines.append(f"  {r['name']} {r['pinned_parsed']} \u2192 {r['latest']} (current)")
        lines.append("")

    total_score = sum(r["drift"] for r in results)
    lines.append(f"\U0001f4ca Total Drift Score: {total_score}/100")
    if critical:
        tip = next((r for r in critical if r["cves"]), None)
        if tip:
            lines.append(f"\U0001f4a1 Tip: Update {tip['name']} to {tip['latest']} (CVE-... fixed)")
        else:
            lines.append(f"\U0001f4a1 Tip: Update critical packages to latest versions")
    lines.append("")

    c_count = len(critical)
    m_count = len(moderate)
    u_count = len(up_to_date)
    lines.append(f"Scanned {total_deps} deps across {total_files} files. "
                 f"{c_count} have critical drift, {m_count} moderate, {u_count} current.")

    return "\n".join(lines)


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Detect when pinned dependencies drift behind latest versions.",
    )
    parser.add_argument("--path", default=".", help="Project root directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--threshold", type=int, default=CRITICAL_THRESHOLD,
                        help=f"Drift score threshold (default: {CRITICAL_THRESHOLD})")
    args = parser.parse_args()

    project_path = os.path.abspath(args.path) if args.path != "." else os.getcwd()

    if args.verbose:
        print(f"Scanning {project_path} ...\n", file=sys.stderr)

    results, total_deps = scan_project(project_path, args.verbose)

    files_found = 0
    for fn in DEP_FILE_HANDLERS:
        if os.path.isfile(os.path.join(project_path, fn)):
            files_found += 1

    output = format_output(results, total_deps, files_found, args.json)
    print(output)

    total_score = sum(r["drift"] for r in results)
    sys.exit(0 if total_score < args.threshold else 1)


if __name__ == "__main__":
    main()
