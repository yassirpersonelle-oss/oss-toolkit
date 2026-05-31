#!/usr/bin/env python3
"""gh-backup: Back up a GitHub repo (issues, PRs, releases, discussions) to local markdown files."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import subprocess
from datetime import datetime, timezone


API_BASE = "https://api.github.com"
USER_AGENT = "gh-backup/1.0"
MAX_PER_PAGE = 100


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backup a GitHub repository to local markdown files."
    )
    parser.add_argument("--repo", "-r", required=True, help="Repository (e.g. owner/name)")
    parser.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN env)")
    parser.add_argument("--output", "-o", help="Backup directory (default: ./backups/{repo})")
    parser.add_argument("--include", default="all",
                        help="Comma-separated: issues,prs,releases,discussions,readme,all (default: all)")
    parser.add_argument("--pages", type=int, default=0,
                        help="Number of pages to fetch per category (0 = all, 100 items per page)")
    parser.add_argument("--skip-clone", action="store_true", help="Skip git mirror clone")
    parser.add_argument("--verbose", action="store_true", help="Show progress output")
    return parser.parse_args()


def get_token(args):
    return args.token or os.environ.get("GITHUB_TOKEN") or ""


def api_headers(token):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def api_discussion_headers(token):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def api_request(url, headers, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read().decode("utf-8")
                link = resp.headers.get("Link", "")
                return json.loads(data), link
        except urllib.error.HTTPError as e:
            if e.code == 403:
                vprint("Rate limited. Waiting 60s...")
                time.sleep(60)
                continue
            elif e.code == 404:
                print("ERROR: Repository not found (404). Check --repo.")
                sys.exit(1)
            else:
                print(f"ERROR: HTTP {e.code} for {url}")
                sys.exit(1)
        except (urllib.error.URLError, OSError) as e:
            print(f"ERROR: Connection error: {e}")
            sys.exit(1)
    print("ERROR: Failed after retries.")
    sys.exit(1)


def paginate(url, headers, max_pages=0):
    results = []
    page = 1
    while url:
        data, link = api_request(url, headers)
        if isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)
            break
        vprint(".")
        if max_pages and page >= max_pages:
            break
        url = next_page_url(link)
        page += 1
    return results


def next_page_url(link_header):
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part[part.index("<") + 1 : part.index(">")]
    return None


def vprint(msg):
    if ARGS.verbose:
        print(msg, end="", flush=True)


def sanitize_filename(name):
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- ")
    return "".join(c if c in keep else "_" for c in name).strip()


def write_frontmatter(file, fields):
    file.write("---\n")
    for k, v in fields.items():
        file.write(f"{k}: {v}\n")
    file.write("---\n")


def fetch_readme(owner, repo, headers, output_dir):
    readme_path = os.path.join(output_dir, "README.md")
    url = f"{API_BASE}/repos/{owner}/{repo}/readme"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
    except Exception as e:
        vprint(f"  (README fetch failed: {e})")
        return False


def fetch_issues(owner, repo, headers, output_dir, max_pages):
    issues_dir = os.path.join(output_dir, "issues")
    os.makedirs(issues_dir, exist_ok=True)
    url = f"{API_BASE}/repos/{owner}/{repo}/issues?state=all&per_page={MAX_PER_PAGE}&page=1"
    all_items = paginate(url, headers, max_pages)
    count = 0
    for item in all_items:
        if "pull_request" in item:
            continue
        count += 1
        labels = ", ".join(l["name"] for l in item.get("labels", []))
        assignees = ", ".join(u["login"] for u in item.get("assignees", []))
        body = (item.get("body") or "No description provided.")
        filename = f"issue-{item['number']}.md"
        filepath = os.path.join(issues_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            write_frontmatter(f, {
                "id": item["number"],
                "title": item["title"],
                "state": item["state"],
                "created": item["created_at"][:10],
                "updated": item["updated_at"][:10],
                "labels": labels,
                "assignees": assignees,
                "comments": item.get("comments", 0),
            })
            f.write("\n## Issue body\n\n")
            f.write(body)
    return count


def fetch_prs(owner, repo, headers, output_dir, max_pages):
    prs_dir = os.path.join(output_dir, "prs")
    os.makedirs(prs_dir, exist_ok=True)
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls?state=all&per_page={MAX_PER_PAGE}&page=1"
    all_items = paginate(url, headers, max_pages)
    count = 0
    for item in all_items:
        count += 1
        labels = ", ".join(l["name"] for l in item.get("labels", []))
        assignees = ", ".join(u["login"] for u in item.get("assignees", []))
        body = (item.get("body") or "No description provided.")
        filename = f"pr-{item['number']}.md"
        filepath = os.path.join(prs_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            write_frontmatter(f, {
                "id": item["number"],
                "title": item["title"],
                "state": item["state"],
                "created": item["created_at"][:10],
                "updated": item["updated_at"][:10],
                "merged": item.get("merged", False),
                "labels": labels,
                "assignees": assignees,
                "comments": item.get("comments", 0),
            })
            f.write("\n## PR body\n\n")
            f.write(body)
    return count


def fetch_releases(owner, repo, headers, output_dir, max_pages):
    releases_dir = os.path.join(output_dir, "releases")
    os.makedirs(releases_dir, exist_ok=True)
    url = f"{API_BASE}/repos/{owner}/{repo}/releases?per_page={MAX_PER_PAGE}&page=1"
    all_items = paginate(url, headers, max_pages)
    count = 0
    for item in all_items:
        count += 1
        tag = item.get("tag_name", "unknown")
        body = (item.get("body") or "No description provided.")
        name = item.get("name") or tag
        author = item.get("author", {}).get("login", "unknown")
        filename = f"{sanitize_filename(tag)}.md"
        filepath = os.path.join(releases_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            write_frontmatter(f, {
                "tag": tag,
                "name": name,
                "author": author,
                "created": item.get("created_at", "")[:10],
                "published": item.get("published_at", "")[:10],
                "prerelease": item.get("prerelease", False),
                "draft": item.get("draft", False),
            })
            f.write("\n## Release notes\n\n")
            f.write(body)
    return count


def fetch_discussions(owner, repo, headers, output_dir, max_pages):
    discussions_dir = os.path.join(output_dir, "discussions")
    os.makedirs(discussions_dir, exist_ok=True)
    url = f"{API_BASE}/repos/{owner}/{repo}/discussions?per_page={MAX_PER_PAGE}&page=1"
    all_items = paginate(url, headers, max_pages)
    count = 0
    for item in all_items:
        count += 1
        number = item.get("number", count)
        title = item.get("title", "Untitled")
        body = (item.get("body") or "No description provided.")
        state = item.get("state", "open")
        labels = ", ".join(l["name"] for l in item.get("labels", []))
        author = item.get("user", {}).get("login", "unknown") if "user" in item else \
                 item.get("author", {}).get("login", "unknown")
        filename = f"discussion-{number}.md"
        filepath = os.path.join(discussions_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            write_frontmatter(f, {
                "id": number,
                "title": title,
                "state": state,
                "author": author,
                "created": item.get("created_at", "")[:10],
                "updated": item.get("updated_at", "")[:10],
                "labels": labels,
            })
            f.write("\n## Discussion body\n\n")
            f.write(body)
    return count


def git_mirror_clone(clone_url, output_dir):
    git_dir = os.path.join(output_dir, ".git")
    vprint(f"\n  Cloning git mirror...")
    try:
        result = subprocess.run(
            ["git", "clone", "--mirror", clone_url, git_dir],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            vprint(f"  (git clone failed: {result.stderr.strip()})")
            return None
        size = dir_size(git_dir)
        return size
    except FileNotFoundError:
        vprint("  (git not found, skipping clone)")
        return None
    except subprocess.TimeoutExpired:
        vprint("  (git clone timed out, skipping)")
        return None


def dir_size(path):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def format_size(size_bytes):
    if size_bytes is None:
        return None
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f}KB"
    return f"{size_bytes / (1024 * 1024):.0f}MB"


def main():
    global ARGS
    ARGS = parse_args()

    repo = ARGS.repo
    if "/" not in repo:
        print("ERROR: --repo must be in format 'owner/name'")
        sys.exit(1)
    owner, name = repo.split("/", 1)

    token = get_token(ARGS)
    headers = api_headers(token)
    discussion_headers = api_discussion_headers(token)

    output_base = ARGS.output or os.path.join("backups", owner, name)
    output_dir = os.path.abspath(output_base)
    os.makedirs(output_dir, exist_ok=True)

    include_raw = ARGS.include.lower().split(",")
    include_all = "all" in include_raw
    do_readme = include_all or "readme" in include_raw
    do_issues = include_all or "issues" in include_raw
    do_prs = include_all or "prs" in include_raw
    do_releases = include_all or "releases" in include_raw
    do_discussions = include_all or "discussions" in include_raw

    if ARGS.verbose:
        print(f"Backing up {repo} → {output_dir}")
        if token:
            print("Using GitHub token (authenticated)")
        else:
            print("No token — lower rate limits apply")

    results = {"issues": 0, "prs": 0, "releases": 0, "discussions": 0, "readme": False, "clone_size": None}

    if do_readme:
        vprint("  Fetching README...")
        results["readme"] = fetch_readme(owner, name, headers, output_dir)
        vprint("\n")

    if do_issues:
        vprint("  Fetching issues")
        results["issues"] = fetch_issues(owner, name, headers, output_dir, ARGS.pages)
        vprint(f" ({results['issues']})\n")

    if do_prs:
        vprint("  Fetching PRs")
        results["prs"] = fetch_prs(owner, name, headers, output_dir, ARGS.pages)
        vprint(f" ({results['prs']})\n")

    if do_releases:
        vprint("  Fetching releases")
        results["releases"] = fetch_releases(owner, name, headers, output_dir, ARGS.pages)
        vprint(f" ({results['releases']})\n")

    if do_discussions:
        vprint("  Fetching discussions")
        results["discussions"] = fetch_discussions(owner, name, discussion_headers, output_dir, ARGS.pages)
        vprint(f" ({results['discussions']})\n")

    clone_url = f"https://github.com/{repo}.git"
    if not ARGS.skip_clone:
        size_bytes = git_mirror_clone(clone_url, output_dir)
        results["clone_size"] = size_bytes

    meta = {
        "repo": repo,
        "backup_date": datetime.now(timezone.utc).isoformat(),
        "total_issues": results["issues"],
        "total_prs": results["prs"],
        "total_releases": results["releases"],
        "total_discussions": results["discussions"],
    }
    meta_path = os.path.join(output_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print()
    print(f"\u2705 Backup complete: {repo}")
    if do_readme:
        print(f"   \U0001f4c4 README {'saved' if results['readme'] else 'failed'}")
    if do_issues:
        print(f"   \U0001f4dd {results['issues']} issues saved to issues/")
    if do_prs:
        print(f"   \U0001f500 {results['prs']} PRs saved to prs/")
    if do_releases:
        print(f"   \U0001f4e6 {results['releases']} releases saved to releases/")
    if do_discussions:
        print(f"   \U0001f4ac {results['discussions']} discussions saved to discussions/")
    if not ARGS.skip_clone:
        size_str = format_size(results["clone_size"])
        if size_str:
            print(f"   \U0001f4c1 Git mirror cloned ({size_str})")
        else:
            print(f"   \U0001f4c1 Git mirror skipped")
    print(f"   \U0001f4ca meta.json saved")
    print(f"   \u2500" * 21)
    print(f"   \U0001f4c2 Backup location: {output_dir}/")


if __name__ == "__main__":
    main()
