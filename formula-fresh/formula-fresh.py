#!/usr/bin/env python3
"""
formula-fresh: Watch your Homebrew tap and automatically open PRs for new versions.

Keeps your tap formulae fresh without manual work by checking upstream sources
(GitHub Releases, PyPI, crates.io) for new releases.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Formula:
    path: Path
    name: str
    class_name: str
    url: str
    version: str
    sha256: str
    homepage: str = ""

    # Filled later by upstream lookup
    upstream_latest: Optional[str] = None
    upstream_url: Optional[str] = None


@dataclass
class Result:
    checked: int = 0
    upgradable: int = 0
    prs_created: int = 0
    skipped: int = 0
    errors: int = 0
    details: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ruby DSL parsing (regex‑based)
# ---------------------------------------------------------------------------

RE_CLASS = re.compile(r"class\s+(\w+)\s*<\s*Formula\b")
RE_URL = re.compile(r'url\s+"([^"]+)"')
RE_VERSION = re.compile(r'version\s+"([^"]+)"')
RE_SHA256 = re.compile(r'sha256\s+"([a-f0-9]{64})"')
RE_HOMEPAGE = re.compile(r'homepage\s+"([^"]+)"')


def parse_formula(path: Path) -> Optional[Formula]:
    """Parse a Homebrew formula file and extract key fields."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  [WARN] Could not read {path.name}: {exc}", file=sys.stderr)
        return None

    m_class = RE_CLASS.search(text)
    m_url = RE_URL.search(text)
    m_sha = RE_SHA256.search(text)
    m_home = RE_HOMEPAGE.search(text)

    if not m_url or not m_sha:
        print(f"  [WARN] {path.name}: missing url or sha256 – skipping", file=sys.stderr)
        return None

    url = m_url.group(1)

    # Version: explicit `version` block or extracted from URL
    m_ver = RE_VERSION.search(text)
    if m_ver:
        version = m_ver.group(1)
    else:
        version = extract_version_from_url(url)

    class_name = m_class.group(1) if m_class else path.stem
    formula_name = re.sub(r"-(\w)", lambda m: m.group(1).upper(), path.stem)

    return Formula(
        path=path,
        name=formula_name,
        class_name=class_name,
        url=url,
        version=version,
        sha256=m_sha.group(1),
        homepage=m_home.group(1) if m_home else "",
    )


def extract_version_from_url(url: str) -> str:
    """Best‑effort version extraction from a download URL."""
    # Strip query string / fragment
    clean = url.split("?")[0].split("#")[0]

    # GitHub style: …/v1.2.3/…  or  …/1.2.3/…
    m = re.search(r"/v?(\d[\d.]*?)(?:[/_-]|$)", clean)
    if m:
        return m.group(1)

    # PyPI style: …/package-1.2.3.tar.gz
    m = re.search(r"-([\d][\d.]*)\.(?:tar|zip|whl)", clean)
    if m:
        return m.group(1)

    # crates.io: …/crate-name/1.2.3/download
    m = re.search(r"/(\d[\d.]*)/download", clean)
    if m:
        return m.group(1)

    return "unknown"


# ---------------------------------------------------------------------------
# Upstream version lookup
# ---------------------------------------------------------------------------

def _json_get(url: str, verbose: bool = False) -> Optional[dict]:
    """Fetch JSON from *url*, returning None on any error."""
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "formula-fresh/0.1"},
    )
    if verbose:
        print(f"    GET {url}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        if verbose:
            print(f"    [ERR] {exc}", file=sys.stderr)
        return None


def lookup_github_release(owner: str, repo: str, verbose: bool = False) -> tuple[Optional[str], Optional[str]]:
    """Return (version, tarball_url) from latest GitHub release."""
    api = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    data = _json_get(api, verbose)
    if not data:
        return None, None

    tag = data.get("tag_name", "")
    version = re.sub(r"^v", "", tag) if tag else None

    # Find the source tarball asset
    tarball_url = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith((".tar.gz", ".tgz")):
            tarball_url = asset.get("browser_download_url")
            break

    # Fallback: use the release tarball link
    if not tarball_url:
        tarball_url = data.get("tarball_url")

    return version, tarball_url


def lookup_pypi(package: str, verbose: bool = False) -> tuple[Optional[str], Optional[str]]:
    """Return (version, sdist_url) from PyPI JSON API."""
    api = f"https://pypi.org/pypi/{package}/json"
    data = _json_get(api, verbose)
    if not data:
        return None, None

    version = data.get("info", {}).get("version")
    urls = data.get("urls", [])
    sdist_url = None
    for entry in urls:
        if entry.get("packagetype") == "sdist":
            sdist_url = entry.get("url")
            break

    return version, sdist_url


def lookup_crate(crate_name: str, verbose: bool = False) -> tuple[Optional[str], Optional[str]]:
    """Return (version, crate_url) from crates.io JSON API."""
    api = f"https://crates.io/api/v1/crates/{crate_name}"
    data = _json_get(api, verbose)
    if not data:
        return None, None

    versions = data.get("versions", [])
    if not versions:
        return None, None

    # First version is latest
    v0 = versions[0]
    version = v0.get("num")
    crate_url = v0.get("dl_path") or f"https://crates.io/api/v1/crates/{crate_name}/{version}/download"

    return version, crate_url


def determine_upstream(formula: Formula, verbose: bool = False) -> None:
    """Populate formula.upstream_latest / upstream_url."""
    url = formula.url

    # GitHub releases
    m = re.search(r"github\.com/([^/]+)/([^/]+)/releases/download/", url)
    if m:
        owner, repo = m.group(1), m.group(2)
        formula.upstream_latest, formula.upstream_url = lookup_github_release(owner, repo, verbose)
        return

    # PyPI
    if "pypi.org" in url:
        # Try to extract package name from URL: …/package-name/…  or  …/package-name-version…
        m = re.search(r"pypi\.org[^/]*/([^/]+)", url)
        pkg = m.group(1) if m else formula.name
        formula.upstream_latest, formula.upstream_url = lookup_pypi(pkg, verbose)
        return

    # crates.io
    if "crates.io" in url:
        m = re.search(r"crates\.io/([^/]+)/([^/]+)", url)
        if m:
            crate_name = m.group(2)
        else:
            crate_name = formula.name
        formula.upstream_latest, formula.upstream_url = lookup_crate(crate_name, verbose)
        return


# ---------------------------------------------------------------------------
# Version comparison (simple semver‑ish)
# ---------------------------------------------------------------------------

def _parse_ver(v: str) -> list[int]:
    """Split version string into integer components."""
    parts = re.split(r"[^0-9]+", v)
    result = []
    for p in parts:
        if p.isdigit():
            result.append(int(p))
    return result


def version_newer(a: str, b: str) -> bool:
    """Return True if *b* is strictly newer than *a*."""
    pa = _parse_ver(a)
    pb = _parse_ver(b)

    # Pad to same length
    maxlen = max(len(pa), len(pb))
    pa += [0] * (maxlen - len(pa))
    pb += [0] * (maxlen - len(pb))

    return pb > pa


# ---------------------------------------------------------------------------
# Download & sha256
# ---------------------------------------------------------------------------

def download_and_sha256(url: str, verbose: bool = False) -> Optional[str]:
    """Download *url* and return its sha256 hex digest (or None on failure)."""
    if verbose:
        print(f"    Downloading {url} for sha256…")
    req = urllib.request.Request(url, headers={"User-Agent": "formula-fresh/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            h = hashlib.sha256()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                h.update(chunk)
            return h.hexdigest()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        if verbose:
            print(f"    [ERR] Download failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Git operations (branch, edit, commit, push)
# ---------------------------------------------------------------------------

def _git(*args: str, cwd: str = ".", verbose: bool = False) -> subprocess.CompletedProcess:
    cmd = ["git"] + list(args)
    if verbose:
        print(f"    $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def update_formula(formula: Formula, new_version: str, new_sha256: str, dry_run: bool, verbose: bool) -> bool:
    """
    Update the formula file on disk, commit, and push.
    Returns True on success.
    """
    text = formula.path.read_text(encoding="utf-8")
    new_url = re.sub(
        r"(url\s+\")([^\"]+)(\")",
        lambda m: m.group(1) + formula.upstream_url + m.group(3),
        text,
    )

    # Replace version (explicit or inferred)
    if RE_VERSION.search(text):
        new_text = RE_VERSION.sub(f'version "{new_version}"', new_url)
    else:
        # Insert version after url line
        new_text = RE_VERSION.sub("", new_url)  # ensure no stale version
        new_text = new_url  # URL replacement already done

    # Replace sha256
    new_text = RE_SHA256.sub(f'sha256 "{new_sha256}"', new_text)

    if dry_run:
        return True

    # Write updated formula
    formula.path.write_text(new_text, encoding="utf-8")

    # Branch
    branch = f"bump/{formula.name}-{new_version}"
    tap_dir = str(formula.path.parent.parent)  # repo root (Formula/…)
    if tap_dir == ".":
        tap_dir = str(Path.cwd())

    # Detect tap root by looking for .git
    p = formula.path.parent
    while p != p.parent:
        if (p / ".git").exists():
            tap_dir = str(p)
            break
        p = p.parent

    _git("checkout", "-b", branch, cwd=tap_dir, verbose=verbose)
    _git("add", str(formula.path.relative_to(tap_dir)), cwd=tap_dir, verbose=verbose)
    _git(
        "commit",
        "-m",
        f"{formula.name}: bump to {new_version}",
        cwd=tap_dir,
        verbose=verbose,
    )
    _git("push", "-u", "origin", branch, cwd=tap_dir, verbose=verbose)
    return True


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formula-fresh",
        description="Watch a Homebrew tap and open PRs for new upstream versions.",
    )
    parser.add_argument("--tap", default=".", help="Path to Homebrew tap repo (default: cwd)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without pushing")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress")
    parser.add_argument("--upstream", default=None, help="Check only this formula (by name)")
    args = parser.parse_args()

    tap_path = Path(args.tap).resolve()
    if not tap_path.is_dir():
        print(f"Error: tap path {tap_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Collect formula files
    formula_dirs = list(tap_path.glob("Formula/**/*.rb")) + list(tap_path.glob("Formulaies/**/*.rb")) + list(tap_path.glob("*.rb"))
    formula_files = sorted(set(f for f in formula_dirs if f.suffix == ".rb"))

    if not formula_files:
        print("No .rb formula files found.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Found {len(formula_files)} formula file(s) in {tap_path}")

    result = Result()

    for fp in formula_files:
        if args.upstream and args.upstream.lower() not in fp.stem.lower():
            continue

        print(f"[{result.checked + 1}] {fp.stem}")
        formula = parse_formula(fp)
        if formula is None:
            result.skipped += 1
            continue
        result.checked += 1

        # Lookup upstream
        determine_upstream(formula, verbose=args.verbose)

        if not formula.upstream_latest:
            print(f"  Can't determine upstream for {formula.name} – skipping")
            result.skipped += 1
            result.details.append({"formula": formula.name, "status": "skipped", "reason": "unknown upstream"})
            continue

        if not version_newer(formula.version, formula.upstream_latest):
            print(f"  Up to date ({formula.version})")
            result.details.append({"formula": formula.name, "status": "up_to_date", "version": formula.version})
            continue

        result.upgradable += 1
        print(f"  New version available: {formula.version} → {formula.upstream_latest}")

        # Download new source to get sha256
        new_sha = None
        if formula.upstream_url:
            new_sha = download_and_sha256(formula.upstream_url, verbose=args.verbose)

        if not new_sha:
            print(f"  [WARN] Could not compute sha256 – skipping this formula")
            result.errors += 1
            result.details.append({"formula": formula.name, "status": "error", "reason": "sha256 download failed"})
            continue

        if args.dry_run:
            print(f"  Would update {formula.path.name}: {formula.version} → {formula.upstream_latest} (sha256: {new_sha[:12]}…)")
            result.details.append({
                "formula": formula.name,
                "status": "would_update",
                "from": formula.version,
                "to": formula.upstream_latest,
                "sha256": new_sha,
            })
            continue

        try:
            update_formula(formula, formula.upstream_latest, new_sha, dry_run=False, verbose=args.verbose)
            result.prs_created += 1
            print(f"  Branch pushed: bump/{formula.name}-{formula.upstream_latest}")
            result.details.append({
                "formula": formula.name,
                "status": "branch_pushed",
                "from": formula.version,
                "to": formula.upstream_latest,
                "branch": f"bump/{formula.name}-{formula.upstream_latest}",
            })
        except Exception as exc:
            print(f"  [ERROR] {exc}", file=sys.stderr)
            result.errors += 1
            result.details.append({"formula": formula.name, "status": "error", "reason": str(exc)})

    # Summary
    print()
    print(f"Checked {result.checked} formula(s).")
    print(f"{result.upgradable} have new version(s) available.")
    if not args.dry_run:
        print(f"Created {result.prs_created} branch(es).")
    if result.skipped:
        print(f"Skipped {result.skipped} formula(s) (parse failure or unknown upstream).")
    if result.errors:
        print(f"{result.errors} error(s).")

    if args.json_output:
        summary = {
            "checked": result.checked,
            "upgradable": result.upgradable,
            "prs_created": result.prs_created,
            "skipped": result.skipped,
            "errors": result.errors,
            "details": result.details,
        }
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
