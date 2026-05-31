#!/usr/bin/env python3
"""license-compatibility.py — Scan dependencies for license compatibility."""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

COMPATIBILITY = {
    "MIT": {
        "compatible": [
            "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
            "Unlicense", "CC0-1.0", "0BSD", "Python-2.0", "Zlib", "PostgreSQL",
        ],
        "incompatible": [
            "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
            "AGPL-3.0-only", "AGPL-3.0-or-later", "EUPL-1.2", "SSPL-1.0",
            "CC-BY-NC-4.0",
        ],
        "warning": [
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
            "LGPL-3.0-or-later", "MPL-2.0", "BSL-1.0",
        ],
    },
    "Apache-2.0": {
        "compatible": [
            "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC",
            "Unlicense", "CC0-1.0", "0BSD",
        ],
        "incompatible": [
            "GPL-2.0-only", "GPL-2.0-or-later", "AGPL-3.0-only",
            "AGPL-3.0-or-later", "SSPL-1.0",
        ],
        "warning": [
            "GPL-3.0-only", "GPL-3.0-or-later", "LGPL-2.1-only",
            "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
            "MPL-2.0",
        ],
    },
    "GPL-3.0-only": {
        "compatible": [
            "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-only",
            "GPL-2.0-or-later", "MIT", "Apache-2.0", "BSD-2-Clause",
            "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0", "0BSD",
            "Python-2.0", "Zlib", "PostgreSQL",
        ],
        "incompatible": [
            "AGPL-3.0-only", "AGPL-3.0-or-later", "SSPL-1.0",
            "CC-BY-NC-4.0",
        ],
        "warning": [
            "LGPL-3.0-only", "LGPL-3.0-or-later", "MPL-2.0",
        ],
    },
    "GPL-2.0-only": {
        "compatible": [
            "GPL-2.0-only", "GPL-2.0-or-later", "MIT", "BSD-2-Clause",
            "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0", "0BSD",
        ],
        "incompatible": [
            "GPL-3.0-only", "GPL-3.0-or-later", "AGPL-3.0-only",
            "AGPL-3.0-or-later", "Apache-2.0", "SSPL-1.0",
        ],
        "warning": [
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
            "LGPL-3.0-or-later", "MPL-2.0",
        ],
    },
    "AGPL-3.0-only": {
        "compatible": [
            "AGPL-3.0-only", "AGPL-3.0-or-later", "GPL-3.0-only",
            "GPL-3.0-or-later", "GPL-2.0-only", "GPL-2.0-or-later",
            "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
            "Unlicense", "CC0-1.0", "0BSD", "Python-2.0", "Zlib",
            "PostgreSQL",
        ],
        "incompatible": [
            "SSPL-1.0", "CC-BY-NC-4.0",
        ],
        "warning": [
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
            "LGPL-3.0-or-later", "MPL-2.0", "EUPL-1.2", "BSL-1.0",
        ],
    },
    "LGPL-3.0-only": {
        "compatible": [
            "LGPL-3.0-only", "LGPL-3.0-or-later", "LGPL-2.1-only",
            "LGPL-2.1-or-later", "GPL-2.0-only", "GPL-2.0-or-later",
            "GPL-3.0-only", "GPL-3.0-or-later", "MIT", "Apache-2.0",
            "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "CC0-1.0",
            "0BSD", "Python-2.0", "Zlib", "PostgreSQL",
        ],
        "incompatible": [
            "AGPL-3.0-only", "AGPL-3.0-or-later", "SSPL-1.0",
            "CC-BY-NC-4.0",
        ],
        "warning": [
            "MPL-2.0", "EUPL-1.2", "BSL-1.0",
        ],
    },
    "MPL-2.0": {
        "compatible": [
            "MPL-2.0", "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
            "ISC", "Unlicense", "CC0-1.0", "0BSD", "Python-2.0", "Zlib",
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
            "LGPL-3.0-or-later", "GPL-2.0-only", "GPL-2.0-or-later",
            "GPL-3.0-only", "GPL-3.0-or-later", "PostgreSQL",
        ],
        "incompatible": [
            "AGPL-3.0-only", "AGPL-3.0-or-later", "SSPL-1.0",
            "CC-BY-NC-4.0",
        ],
        "warning": [
            "EUPL-1.2", "BSL-1.0",
        ],
    },
    "BSD-3-Clause": {
        "compatible": [
            "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
            "Unlicense", "CC0-1.0", "0BSD", "Python-2.0", "Zlib",
            "PostgreSQL",
        ],
        "incompatible": [
            "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only",
            "GPL-3.0-or-later", "AGPL-3.0-only", "AGPL-3.0-or-later",
            "SSPL-1.0", "EUPL-1.2", "CC-BY-NC-4.0",
        ],
        "warning": [
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
            "LGPL-3.0-or-later", "MPL-2.0", "BSL-1.0",
        ],
    },
    "Unlicense": {
        "compatible": [
            "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
            "Unlicense", "CC0-1.0", "0BSD", "Python-2.0", "Zlib",
            "PostgreSQL",
        ],
        "incompatible": [
            "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only",
            "GPL-3.0-or-later", "AGPL-3.0-only", "AGPL-3.0-or-later",
            "SSPL-1.0", "EUPL-1.2", "CC-BY-NC-4.0",
        ],
        "warning": [
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
            "LGPL-3.0-or-later", "MPL-2.0", "BSL-1.0",
        ],
    },
}

CLEAN_LICENSE_MAP = {
    "MIT": "MIT",
    "apache": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "gpl": "GPL-3.0-only",
    "gpl-3.0": "GPL-3.0-only",
    "gpl-2.0": "GPL-2.0-only",
    "agpl": "AGPL-3.0-only",
    "agpl-3.0": "AGPL-3.0-only",
    "lgpl": "LGPL-3.0-only",
    "lgpl-3.0": "LGPL-3.0-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "mpl-2.0": "MPL-2.0",
    "bsd": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "isc": "ISC",
    "unlicense": "Unlicense",
    "cc0-1.0": "CC0-1.0",
    "0bsd": "0BSD",
    "python-2.0": "Python-2.0",
    "zlib": "Zlib",
    "postgresql": "PostgreSQL",
    "eupl-1.2": "EUPL-1.2",
    "sspl-1.0": "SSPL-1.0",
    "bsl-1.0": "BSL-1.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0",
}

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def color(text, code, use_color=True):
    return f"{code}{text}{RESET}" if use_color else text


def warn(text, use_color=True):
    return color(text, YELLOW, use_color)


def fail(text, use_color=True):
    return color(text, RED, use_color)


def ok(text, use_color=True):
    return color(text, GREEN, use_color)


def head(text, use_color=True):
    return color(text, CYAN + BOLD, use_color)


def fetch_json(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "license-compatibility/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def clean_license(raw):
    if not raw:
        return None
    raw = raw.strip().strip('"').strip("'")
    low = raw.lower()
    if low in CLEAN_LICENSE_MAP:
        return CLEAN_LICENSE_MAP[low]
    if "gpl" in low and "3" in low and "agpl" not in low:
        return "GPL-3.0-only"
    if "gpl" in low and "2" in low and "agpl" not in low:
        return "GPL-2.0-only"
    if "agpl" in low:
        return "AGPL-3.0-only"
    if "lgpl" in low:
        if "3" in low:
            return "LGPL-3.0-only"
        return "LGPL-2.1-only"
    if "mit" in low:
        return "MIT"
    if "apache" in low:
        return "Apache-2.0"
    if "bsd" in low:
        if "2" in low:
            return "BSD-2-Clause"
        return "BSD-3-Clause"
    if "mpl" in low or "moz" in low:
        return "MPL-2.0"
    if "unlicense" in low:
        return "Unlicense"
    return raw


def get_compatibility(project_license, dep_license):
    pl = clean_license(project_license)
    dl = clean_license(dep_license)
    if not pl or not dl:
        return "unknown", "Unknown license — manual review required"
    if pl not in COMPATIBILITY:
        return "unknown", f"Project license '{pl}' not in compatibility matrix — manual review"
    matrix = COMPATIBILITY[pl]
    if dl in matrix["compatible"]:
        return "compatible", None
    if dl in matrix["incompatible"]:
        return "incompatible", get_incompat_reason(pl, dl)
    if dl in matrix["warning"]:
        return "warning", get_warning_reason(dl)
    return "unknown", f"'{dl}' not classified for '{pl}' — manual review"


def get_incompat_reason(project_license, dep_license):
    if dep_license in ("SSPL-1.0",):
        return "Not compatible with any FOSS license"
    if "GPL" in dep_license and "AGPL" not in dep_license:
        return f"GPL dependencies cannot be used in {project_license} projects"
    if "AGPL" in dep_license:
        return f"AGPL dependencies cannot be used in {project_license} projects"
    if dep_license == "CC-BY-NC-4.0":
        return "Non-commercial license — cannot be used in OSS projects"
    if dep_license == "EUPL-1.2":
        return f"Incompatible with {project_license}"
    return f"Incompatible with {project_license}"


def get_warning_reason(dep_license):
    m = {
        "LGPL-2.1-only": "LGPL requires dynamic linking — verify usage",
        "LGPL-2.1-or-later": "LGPL requires dynamic linking — verify usage",
        "LGPL-3.0-only": "LGPL requires dynamic linking — verify usage",
        "LGPL-3.0-or-later": "LGPL requires dynamic linking — verify usage",
        "MPL-2.0": "Check MPL requirements (file-level copyleft)",
        "BSL-1.0": "Boost license — verify compatibility terms",
        "EUPL-1.2": "EUPL has specific compatibility provisions — verify",
    }
    return m.get(dep_license, "Verify license terms")


def detect_project_license(path):
    license_file = os.path.join(path, "LICENSE")
    if os.path.isfile(license_file):
        try:
            with open(license_file, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            detected = _detect_license_from_text(text)
            if detected:
                return detected
        except OSError:
            pass

    pkg_json = os.path.join(path, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            lic = data.get("license") or (data.get("licenses") or [{}])[0].get("type")
            if lic:
                return clean_license(lic)
        except (OSError, json.JSONDecodeError):
            pass

    pyproj = os.path.join(path, "pyproject.toml")
    if os.path.isfile(pyproj):
        lic = _parse_license_from_toml(pyproj)
        if lic:
            return clean_license(lic)

    cargo = os.path.join(path, "Cargo.toml")
    if os.path.isfile(cargo):
        lic = _parse_license_from_toml(cargo)
        if lic:
            return clean_license(lic)

    return None


def _detect_license_from_text(text):
    text_lower = text.strip().lower()
    if text_lower.startswith("mit license"):
        return "MIT"
    if "apache license" in text_lower and "2.0" in text_lower:
        return "Apache-2.0"
    if "gnu general public license" in text_lower:
        if "version 3" in text_lower or "gpl-3.0" in text_lower:
            return "GPL-3.0-only"
        if "version 2" in text_lower or "gpl-2.0" in text_lower:
            return "GPL-2.0-only"
    if "gnu affero general public license" in text_lower:
        return "AGPL-3.0-only"
    if "gnu lesser general public license" in text_lower:
        return "LGPL-3.0-only"
    if "bsd" in text_lower and "3" in text_lower:
        return "BSD-3-Clause"
    if "bsd" in text_lower and "2" in text_lower:
        return "BSD-2-Clause"
    return None


def _parse_license_from_toml(toml_path):
    try:
        with open(toml_path, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r'license\s*=\s*"([^"]+)"', content)
        if m:
            return m.group(1)
        m = re.search(r'license\s*=\s*{text\s*=\s*"([^"]+)"', content)
        if m:
            return m.group(1)
    except OSError:
        pass
    return None


def scan_dependencies(path):
    deps = []
    deps.extend(_scan_npm(path))
    deps.extend(_scan_requirements_txt(path))
    deps.extend(_scan_cargo(path))
    deps.extend(_scan_pyproject_toml(path))
    return deps


def _scan_npm(path):
    pkg_json = os.path.join(path, "package.json")
    if not os.path.isfile(pkg_json):
        return []
    try:
        with open(pkg_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    names = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(section, {})
        names.extend(deps.keys())
    results = []
    for name in names:
        lic = _fetch_npm_license(name)
        results.append({"name": name, "license_raw": lic, "license": clean_license(lic), "source": "npm"})
    return results


def _fetch_npm_license(name):
    data = fetch_json(f"https://registry.npmjs.org/{urllib.request.quote(name, safe='@/%')}/latest")
    if data:
        lic = data.get("license")
        if lic:
            return lic
    return "unknown"


def _scan_requirements_txt(path):
    req_file = os.path.join(path, "requirements.txt")
    if not os.path.isfile(req_file):
        return []
    try:
        with open(req_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return []
    results = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = re.split(r"[=~<>!\[;]", line)[0].strip()
        if not name or name in seen:
            continue
        seen.add(name)
        lic = _fetch_pypi_license(name)
        results.append({"name": name, "license_raw": lic, "license": clean_license(lic), "source": "pypi"})
    return results


def _fetch_pypi_license(name):
    data = fetch_json(f"https://pypi.org/pypi/{urllib.request.quote(name)}/json")
    if data:
        lic = data.get("info", {}).get("license")
        classifiers = data.get("info", {}).get("classifiers", [])
        if not lic or lic == "UNKNOWN":
            for c in classifiers:
                if c.startswith("License ::") and "OSI Approved" in c:
                    parts = c.split(" :: ")
                    if len(parts) >= 3:
                        return parts[-1]
        if lic and lic != "UNKNOWN":
            return lic
    return "unknown"


def _scan_cargo(path):
    cargo_file = os.path.join(path, "Cargo.toml")
    if not os.path.isfile(cargo_file):
        return []
    try:
        with open(cargo_file, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []
    results = []
    in_deps = False
    seen = set()
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[dependencies"):
            in_deps = True
            continue
        if stripped.startswith("[") and in_deps:
            in_deps = False
            continue
        if in_deps and "=" in stripped and not stripped.startswith("#"):
            name = stripped.split("=")[0].strip()
            if name and name not in seen:
                seen.add(name)
                results.append({"name": name, "license_raw": "unknown", "license": None, "source": "cargo"})
    return results


def _scan_pyproject_toml(path):
    pyproj = os.path.join(path, "pyproject.toml")
    if not os.path.isfile(pyproj):
        return []
    try:
        with open(pyproj, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []
    results = []
    seen = set()

    m = re.search(r'\[project\]', content)
    if m:
        in_project = False
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "[project]":
                in_project = True
                continue
            if stripped.startswith("[") and in_project:
                break
            if in_project and stripped.startswith("dependencies"):
                continue
            if in_project and stripped.startswith('"') and "," in stripped:
                parts = stripped.strip(",").strip('"').split()
                if parts:
                    name = re.split(r"[=~<>!\[;]", parts[0])[0].strip()
                    if name and name not in seen:
                        seen.add(name)
                        results.append({"name": name, "license_raw": "unknown", "license": None, "source": "pyproject"})

    m = re.search(r'\[tool\.poetry\.dependencies\]', content)
    if m:
        in_poetry = False
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("[tool.poetry.dependencies]"):
                in_poetry = True
                continue
            if stripped.startswith("[") and in_poetry:
                break
            if in_poetry and not stripped.startswith("#") and not stripped.startswith("python"):
                name = stripped.split("=")[0].strip()
                name = name.strip('"').strip("'")
                if name and name not in seen:
                    seen.add(name)
                    results.append({"name": name, "license_raw": "unknown", "license": None, "source": "pyproject"})

    return results


def format_reason(dep, status, reason, use_color):
    text = f"  {dep['name']} ({dep['source']}) — {dep['license_raw']}"
    if reason:
        text += f" — {reason}"
    if status == "incompatible":
        return fail(text, use_color)
    if status == "warning":
        return warn(text, use_color)
    return ok(text, use_color)


def generate_report_text(project_license, deps, use_color):
    lines = []
    lines.append(head("\U0001f50d License Compatibility Scan", use_color))
    lines.append(f"Project license: {project_license}")
    lines.append("\u2501" * 40)

    incompatible = [d for d in deps if d["status"] == "incompatible"]
    warnings = [d for d in deps if d["status"] == "warning"]
    compatible = [d for d in deps if d["status"] == "compatible"]
    unknown = [d for d in deps if d["status"] == "unknown"]

    if incompatible:
        lines.append("")
        lines.append(fail(f"\U0001f534 INCOMPATIBLE ({len(incompatible)})", use_color))
        for dep in incompatible:
            lines.append(format_reason(dep, "incompatible", dep["reason"], use_color))

    if warnings:
        lines.append("")
        lines.append(warn(f"\u26a0\ufe0f  WARNING ({len(warnings)})", use_color))
        for dep in warnings:
            lines.append(format_reason(dep, "warning", dep["reason"], use_color))

    if compatible:
        lines.append("")
        lines.append(ok(f"\u2705 COMPATIBLE ({len(compatible)})", use_color))
        if len(compatible) <= 10:
            for dep in compatible:
                lines.append(format_reason(dep, "compatible", None, use_color))
        else:
            lines.append(ok(f"  ({len(compatible)} dependencies — use --verbose to list all)", use_color))

    if unknown:
        lines.append("")
        lines.append(warn(f"\u2753 UNKNOWN ({len(unknown)})", use_color))
        for dep in unknown:
            lines.append(format_reason(dep, "unknown", dep["reason"], use_color))

    total = len(deps)
    lines.append("")
    lines.append(f"\U0001f4cb Summary: {total} total deps scanned. "
                 f"{len(incompatible)} incompatible, {len(warnings)} warnings, "
                 f"{len(compatible)} safe, {len(unknown)} unknown.")
    return "\n".join(lines)


def generate_json(project_license, deps):
    return json.dumps({
        "project_license": project_license,
        "dependencies": deps,
        "summary": {
            "total": len(deps),
            "incompatible": sum(1 for d in deps if d["status"] == "incompatible"),
            "warning": sum(1 for d in deps if d["status"] == "warning"),
            "compatible": sum(1 for d in deps if d["status"] == "compatible"),
            "unknown": sum(1 for d in deps if d["status"] == "unknown"),
        },
    }, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Check dependency license compatibility for your project."
    )
    parser.add_argument("--path", default=os.getcwd(),
                        help="Project root path (default: current dir)")
    parser.add_argument("--project-license",
                        help="Override project license (e.g. MIT, Apache-2.0)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--verbose", action="store_true",
                        help="Show all dependencies including compatible ones")
    parser.add_argument("--fail-on", default="incompatible",
                        choices=["incompatible", "warning", "all"],
                        help="When to exit non-zero (default: incompatible)")
    args = parser.parse_args()

    project_path = os.path.abspath(args.path)

    project_license = args.project_license or detect_project_license(project_path)
    if not project_license:
        print("Error: Could not detect project license. Use --project-license.", file=sys.stderr)
        sys.exit(1)

    project_license = clean_license(project_license)
    if project_license not in COMPATIBILITY:
        print(f"Error: Unsupported project license '{project_license}'.", file=sys.stderr)
        sys.exit(1)

    deps = scan_dependencies(project_path)

    if not deps:
        print("No dependencies found. Nothing to check.")
        sys.exit(0)

    for dep in deps:
        status, reason = get_compatibility(project_license, dep["license"])
        dep["status"] = status
        dep["reason"] = reason

    if args.verbose:
        for dep in deps:
            if dep["status"] == "compatible":
                dep["_show"] = True

    if args.json:
        print(generate_json(project_license, deps))
    else:
        use_color = sys.stdout.isatty()
        print(generate_report_text(project_license, deps, use_color))

    incompatible = [d for d in deps if d["status"] == "incompatible"]
    warnings = [d for d in deps if d["status"] == "warning"]
    should_fail = False
    if args.fail_on == "incompatible" and incompatible:
        should_fail = True
    elif args.fail_on == "warning" and (incompatible or warnings):
        should_fail = True

    sys.exit(1 if should_fail else 0)


if __name__ == "__main__":
    main()
