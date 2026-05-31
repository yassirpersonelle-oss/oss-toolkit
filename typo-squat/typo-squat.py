#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys

from typo_db import KNOWN_TYPOS, POPULAR_PACKAGES, ALL_TYPOS, POPULAR_LOWER


def levenshtein(a, b):
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp
    return dp[n]


def has_suspicious_patterns(name):
    checks = []
    if re.search(r'(.)\1{2,}', name):
        checks.append("repeated characters")
    if re.search(r'[0-9]{3,}', name):
        checks.append("excessive digits")
    uncommon = re.findall(r'[^a-z0-9_\-.~\[\]]', name.lower())
    if uncommon:
        checks.append(f"uncommon characters: {set(uncommon)}")
    return checks


def find_closest_match(name, candidates, threshold=2):
    best_dist = threshold + 1
    best_match = None
    for candidate in candidates:
        dist = levenshtein(name.lower(), candidate.lower())
        if dist < best_dist:
            best_dist = dist
            best_match = candidate
    return best_match, best_dist


def parse_package_json(path):
    deps = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for dep in data.get(section, {}):
                deps.append(dep)
    except (json.JSONDecodeError, OSError):
        pass
    return deps, "package.json"


def parse_requirements_txt(path):
    deps = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                parts = re.split(r'[=<>!~;]', line, maxsplit=1)
                name = parts[0].strip()
                if name:
                    name = re.sub(r'\s*\[.*?\]\s*', '', name)
                    name = name.strip()
                    if name:
                        deps.append(name)
    except OSError:
        pass
    return deps, "requirements.txt"


def parse_cargo_toml(path):
    deps = []
    section_re = re.compile(r'^\[(dependencies|dev-dependencies|build-dependencies)\]')
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        in_deps = False
        for line in lines:
            stripped = line.strip()
            if section_re.match(stripped):
                in_deps = True
                continue
            if in_deps:
                if stripped.startswith("["):
                    in_deps = False
                    continue
                if not stripped or stripped.startswith("#"):
                    continue
                m = re.match(r'^(\w[-\w]*)', stripped)
                if m:
                    deps.append(m.group(1))
    except OSError:
        pass
    return deps, "Cargo.toml"


def parse_pipfile(path):
    deps = []
    section_re = re.compile(r'^\[(packages|dev-packages)\]')
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        in_deps = False
        for line in lines:
            stripped = line.strip()
            if section_re.match(stripped):
                in_deps = True
                continue
            if in_deps:
                if stripped.startswith("["):
                    in_deps = False
                    continue
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    name = stripped.split("=", 1)[0].strip().strip('"').strip("'")
                    if name:
                        deps.append(name)
    except OSError:
        pass
    return deps, "Pipfile"


def parse_pyproject_toml(path):
    deps = []
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return deps, "pyproject.toml"

    patterns = [
        r'^dependencies\s*=\s*\[(.*?)\]',
        r'^\[tool\.poetry\.dependencies\]\s*\n(.*?)(?:\n\[|$)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, content, re.DOTALL | re.MULTILINE):
            block = m.group(1)
            for line in block.split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("["):
                    continue
                quote_match = re.match(r'["\'](\w[-\w]*)["\']', line)
                if quote_match:
                    deps.append(quote_match.group(1))
                    continue
                eq_match = re.match(r'^(\w[-\w]*)\s*[=~]', line)
                if eq_match:
                    deps.append(eq_match.group(1))
    return deps, "pyproject.toml"


DETECTORS = [
    ("package.json", parse_package_json),
    ("requirements.txt", parse_requirements_txt),
    ("Cargo.toml", parse_cargo_toml),
    ("Pipfile", parse_pipfile),
    ("pyproject.toml", parse_pyproject_toml),
]


def scan_project(root):
    findings = []
    total_deps = 0
    files_found = 0

    for fname, parser in DETECTORS:
        fpath = os.path.join(root, fname)
        if os.path.isfile(fpath):
            deps, label = parser(fpath)
            if deps:
                files_found += 1
            for dep in deps:
                total_deps += 1
                result = analyze_dependency(dep, label)
                if result:
                    findings.extend(result)
    return total_deps, files_found, findings


def analyze_dependency(name, source):
    findings = []
    lower = name.lower()

    if lower in POPULAR_LOWER:
        return findings

    if lower in ALL_TYPOS:
        for legit, typos in KNOWN_TYPOS.items():
            if lower in [t.lower() for t in typos]:
                findings.append({
                    "package": name,
                    "file": source,
                    "risk_level": "HIGH",
                    "type": "known typo-squat",
                    "suggestion": legit,
                })
                return findings

    suspicious = has_suspicious_patterns(name)
    if suspicious:
        match, dist = find_closest_match(name, POPULAR_PACKAGES, threshold=2)
        if match:
            findings.append({
                "package": name,
                "file": source,
                "risk_level": "MEDIUM" if dist <= 1 else "LOW",
                "type": f"suspicious pattern; {', '.join(suspicious)}",
                "suggestion": match,
            })
        else:
            findings.append({
                "package": name,
                "file": source,
                "risk_level": "LOW",
                "type": f"suspicious pattern; {', '.join(suspicious)}",
                "suggestion": None,
            })
        return findings

    match, dist = find_closest_match(name, POPULAR_PACKAGES, threshold=2)
    if match:
        findings.append({
            "package": name,
            "file": source,
            "risk_level": "MEDIUM" if dist <= 1 else "LOW",
            "type": f"close match to '{match}' (Levenshtein distance: {dist})",
            "suggestion": match,
        })
        return findings

    return findings


def print_report(total_deps, files_found, findings, verbose, json_output):
    if json_output:
        report = {
            "summary": {
                "total_dependencies": total_deps,
                "files_scanned": files_found,
                "potential_typosquats": len(findings),
            },
            "findings": findings,
        }
        print(json.dumps(report, indent=2))
        return

    print(f"Scanned {total_deps} dependencies across {files_found} files."
          f" Found {len(findings)} potential typo-squats.\n")
    if not findings:
        return

    for f in findings:
        risk = f["risk_level"]
        pkg = f["package"]
        src = f["file"]
        stype = f["type"]
        sug = f["suggestion"]

        if risk == "HIGH":
            tag = "\033[91mHIGH\033[0m"
        elif risk == "MEDIUM":
            tag = "\033[93mMEDIUM\033[0m"
        else:
            tag = "\033[90mLOW\033[0m"

        sug_text = f"  -> Did you mean '{sug}'?" if sug else ""
        print(f"  {tag}  {pkg}  ({src})")
        print(f"       Type: {stype}{sug_text}")
        if verbose:
            print()

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Scan project dependencies for potential typo-squatting packages."
    )
    parser.add_argument(
        "--path", default=".",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed information for each finding"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    total_deps, files_found, findings = scan_project(root)
    print_report(total_deps, files_found, findings, args.verbose, args.json_output)
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
