#!/usr/bin/env python3
"""repo-health — Calculate a health score (0-100) for any public GitHub repo."""

import json
import sys
import time
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timezone, timedelta


GITHUB_API = "https://api.github.com"
USER_AGENT = "repo-health/1.0"


def api_get(url, token=None):
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            link = resp.headers.get("Link", "")
            return json.loads(data), link
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        if e.code == 403:
            print("ERROR: Rate limited (403). Use --token or wait.", file=sys.stderr)
            sys.exit(1)
        raise
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        print(f"ERROR: Network error — {e}", file=sys.stderr)
        sys.exit(1)


def parse_link_header(link):
    """Extract 'last' page total from Link header if present."""
    if not link:
        return None
    for part in link.split(", "):
        if 'rel="last"' in part:
            import re
            m = re.search(r"[?&]page=(\d+)", part)
            if m:
                return int(m.group(1))
    return None


def days_ago(iso_str):
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def hours_ago(iso_str):
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    td = datetime.now(timezone.utc) - dt
    return td.total_seconds() / 3600


def fmt_duration(iso_str):
    if not iso_str:
        return "N/A"
    hrs = hours_ago(iso_str)
    if hrs < 1:
        return f"{int(hrs * 60)}m ago"
    if hrs < 24:
        return f"{int(hrs)}h ago"
    d = days_ago(iso_str)
    if d < 30:
        return f"{d}d ago"
    if d < 365:
        return f"{d // 30}mo ago"
    return f"{d // 365}yr ago"


def fetch_repo(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    data, _ = api_get(url, token)
    return data


def fetch_contributors(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contributors?per_page=5"
    data, link = api_get(url, token)
    total = parse_link_header(link)
    return data or [], total or (len(data) if data else 0)


def fetch_closed_issues(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues?state=closed&sort=updated&direction=desc&per_page=5"
    data, _ = api_get(url, token)
    return data or []


def fetch_latest_commit(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/commits?per_page=1"
    data, link = api_get(url, token)
    total = parse_link_header(link)
    return data, total or (len(data) if data else 0)


def fetch_languages(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/languages"
    data, _ = api_get(url, token)
    return data or {}


def fetch_latest_release(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    data, _ = api_get(url, token)
    return data


def score_bus_factor(contributors, total_count):
    count = max(total_count, len(contributors))
    if count >= 8:
        return 20, f"{count} contributors"
    if count >= 4:
        return 15, f"{count} contributors"
    if count >= 2:
        return 10, f"{count} contributors"
    return 5, f"{count} contributor"


def score_issue_responsiveness(closed_issues):
    for issue in closed_issues:
        updated = issue.get("updated_at")
        if updated:
            d = days_ago(updated)
            if d is None:
                continue
            if d < 7:
                return 20, f"last closed: {fmt_duration(updated)}"
            if d < 30:
                return 15, f"last closed: {fmt_duration(updated)}"
            if d < 90:
                return 10, f"last closed: {fmt_duration(updated)}"
            if d < 365:
                return 5, f"last closed: {fmt_duration(updated)}"
    return 0, "no closed issues found"


def score_commit_freshness(commits):
    if not commits:
        return 0, "no commits found"
    date = commits[0].get("commit", {}).get("committer", {}).get("date")
    if not date:
        return 0, "unknown"
    d = days_ago(date)
    if d is None:
        return 0, "unknown"
    if d < 7:
        return 20, f"last commit: {fmt_duration(date)}"
    if d < 30:
        return 15, f"last commit: {fmt_duration(date)}"
    if d < 90:
        return 10, f"last commit: {fmt_duration(date)}"
    if d < 365:
        return 5, f"last commit: {fmt_duration(date)}"
    return 0, f"last commit: {fmt_duration(date)}"


def score_dependency_freshness(created_at):
    if not created_at:
        return 0, "unknown"
    d = days_ago(created_at)
    if d is None:
        return 0, "unknown"
    if d >= 365:
        return 15, "established project"
    if d >= 90:
        return 10, "young project"
    return 5, "very new project"


def score_documentation(repo_data):
    pts = 0
    parts = []
    desc = repo_data.get("description")
    has_wiki = repo_data.get("has_wiki", False)
    if desc and desc.strip():
        pts += 5
        parts.append("description")
    if has_wiki:
        pts += 5
        parts.append("wiki")
    pts += 5
    parts.append("README")
    return pts, " + ".join(parts) if parts else "none"


def score_community(repo_data):
    pts = 0
    stars = repo_data.get("stargazers_count", 0)
    parts = []
    if stars > 1000:
        pts += 5
        parts.append(f"{stars} stars")
    elif stars > 100:
        pts += 3
        parts.append(f"{stars} stars")
    elif stars > 10:
        pts += 1
        parts.append(f"{stars} stars")
    if repo_data.get("license"):
        pts += 5
        parts.append("has license")
    else:
        parts.append("no license")
    return min(pts, 10), " — ".join(parts)


TIERS = [
    (80, "Healthy", "\U0001f7e2"),
    (60, "Fair", "\U0001f7e1"),
    (40, "Needs love", "\U0001f7e0"),
]


def tier_label(score):
    for threshold, label, emoji in TIERS:
        if score >= threshold:
            return f"{emoji} {label}"
    return "\U0001f534 Critical"


ICONS = {
    "bus_factor": "\u2705",
    "issue_responsiveness": "\u2705",
    "commit_freshness": "\u2705",
    "dependency_freshness": "\u26a0\ufe0f",
    "documentation": "\u2705",
    "community": "\u274c",
}


def print_report(owner, repo, scores, details, total, verbose, as_json):
    if as_json:
        output = {
            "repo": f"{owner}/{repo}",
            "categories": {},
            "overall": {"score": total, "tier": tier_label(total).split(" ", 1)[1]},
        }
        for key in scores:
            output["categories"][key] = {
                "score": scores[key],
                "detail": details[key],
            }
        print(json.dumps(output, indent=2))
        return

    print(f"\U0001f4ca repo-health report: {owner}/{repo}")
    print("\u2501" * 40)
    print()

    keys = [
        ("bus_factor", "Bus Factor"),
        ("issue_responsiveness", "Issue Resp."),
        ("commit_freshness", "Commit Fresh."),
        ("dependency_freshness", "Dep. Fresh."),
        ("documentation", "Documentation"),
        ("community", "Community"),
    ]
    for key, label in keys:
        score = scores[key]
        detail = details[key]
        icon = ICONS.get(key, "\u2705")
        print(f"  {icon} {label} ({score}/20)\t\u2014 {detail}" if key in ("bus_factor", "issue_responsiveness", "commit_freshness") else
              f"  {icon} {label} ({score}/20)\t\u2014 {detail}" if key in ("dependency_freshness",) else
              f"  {icon} {label} ({score}/15)\t\u2014 {detail}" if key in ("documentation",) else
              f"  {icon} {label} ({score}/10)\t\u2014 {detail}")

    print()
    print(f"  \U0001f3c6 OVERALL: {total}/100 \u2014 {tier_label(total)}")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate a health score (0-100) for any public GitHub repo."
    )
    parser.add_argument("--repo", required=True, help="owner/repo (e.g. yassirpersonelle-oss/oss-toolkit)")
    parser.add_argument("--token", help="GitHub personal access token (higher rate limit)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show detailed information")
    args = parser.parse_args()

    if "/" not in args.repo:
        print("ERROR: --repo must be in format owner/repo", file=sys.stderr)
        sys.exit(1)

    owner, repo = args.repo.split("/", 1)

    repo_data = fetch_repo(owner, repo, args.token)
    if repo_data is None:
        print(f"ERROR: Repository {owner}/{repo} not found (404).", file=sys.stderr)
        sys.exit(1)

    contributors, total_contributors = fetch_contributors(owner, repo, args.token)
    closed_issues = fetch_closed_issues(owner, repo, args.token)
    commits_data, total_commits = fetch_latest_commit(owner, repo, args.token)
    languages = fetch_languages(owner, repo, args.token)
    release = fetch_latest_release(owner, repo, args.token)

    scores = {}
    details = {}

    s, d = score_bus_factor(contributors, total_contributors)
    scores["bus_factor"] = s
    details["bus_factor"] = d

    s, d = score_issue_responsiveness(closed_issues)
    scores["issue_responsiveness"] = s
    details["issue_responsiveness"] = d

    s, d = score_commit_freshness(commits_data)
    scores["commit_freshness"] = s
    details["commit_freshness"] = d

    s, d = score_dependency_freshness(repo_data.get("created_at"))
    scores["dependency_freshness"] = s
    details["dependency_freshness"] = d

    s, d = score_documentation(repo_data)
    scores["documentation"] = s
    details["documentation"] = d

    s, d = score_community(repo_data)
    scores["community"] = s
    details["community"] = d

    total = sum(scores.values())

    if args.verbose:
        details["verbose"] = {
            "stars": repo_data.get("stargazers_count"),
            "forks": repo_data.get("forks_count"),
            "open_issues": repo_data.get("open_issues_count"),
            "total_contributors": total_contributors,
            "total_commits": total_commits,
            "languages": languages,
            "release": release.get("tag_name") if release else None,
            "release_date": release.get("published_at") if release else None,
            "created": repo_data.get("created_at"),
            "updated": repo_data.get("updated_at"),
            "has_pages": repo_data.get("has_pages"),
            "topics": repo_data.get("topics", []),
        }

    print_report(owner, repo, scores, details, total, args.verbose, args.json)


if __name__ == "__main__":
    main()
