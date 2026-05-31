#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime

SECTIONS = OrderedDict([
    ("breaking", "## ⚠️ Breaking Changes"),
    ("feat", "## 🚀 Features"),
    ("feature", "## 🚀 Features"),
    ("fix", "## 🐛 Bug Fixes"),
    ("docs", "## 📝 Documentation"),
    ("perf", "## ⚡ Performance"),
    ("refactor", "## ♻️ Refactoring"),
    ("style", "## 🎨 Style"),
    ("test", "## 🧪 Tests"),
    ("build", "## 🏗️ Build & CI"),
    ("ci", "## 🏗️ Build & CI"),
    ("chore", "## 🧹 Chores"),
    ("deps", "## 🧹 Chores"),
])

SECTION_ORDER = [
    "breaking",
    "feat", "feature",
    "fix",
    "docs",
    "perf",
    "refactor",
    "style",
    "test",
    "build", "ci",
    "chore", "deps",
]

CONVENTIONAL_RE = re.compile(
    r'^(?P<type>[a-zA-Z]+)'       # type
    r'(?:\((?P<scope>[^)]*)\))?'  # optional (scope)
    r'(?P<breaking>!)?'           # optional !
    r'\s*:\s*'                    # colon separator
    r'(?P<description>.+)$'       # description
)

MIGRATION_PREFIXES = re.compile(r'^(MIGRATION|UPGRADE|DEPRECATED):', re.IGNORECASE)


def run_git(args, repo):
    cmd = ["git", "-C", repo] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running git command: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return result.stdout.rstrip("\n")


def run_git_quiet(args, repo):
    cmd = ["git", "-C", repo] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip("\n")


def get_last_tag(repo):
    return run_git_quiet(["describe", "--tags", "--abbrev=0"], repo)


def get_first_commit(repo):
    return run_git_quiet(["rev-list", "--max-parents=0", "HEAD"], repo)


def parse_commits(repo, from_ref, to_ref):
    log = run_git(
        [
            "log",
            "--pretty=format:===COMMIT===%n%H%n%an%n%ae%n%aI%n%s%n%b",
            "--no-merges",
            f"{from_ref}..{to_ref}",
        ],
        repo,
    )
    if not log:
        return []
    blocks = log.split("\n===COMMIT===\n")
    commits = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 5:
            continue
        hash_ = lines[0].strip()
        author_name = lines[1].strip()
        author_email = lines[2].strip()
        date_str = lines[3].strip()
        subject = lines[4].strip()
        body = "\n".join(lines[5:]) if len(lines) > 5 else ""
        commits.append({
            "hash": hash_,
            "author_name": author_name,
            "author_email": author_email,
            "date": date_str,
            "subject": subject,
            "body": body.strip(),
        })
    commits.reverse()
    return commits


def parse_conventional(subject, body):
    m = CONVENTIONAL_RE.match(subject)
    if not m:
        return None
    info = m.groupdict()
    if body and "BREAKING CHANGE:" in body:
        info["breaking"] = True
    return info


def categorize_commits(commits):
    sections = OrderedDict()
    for key in SECTION_ORDER:
        sections[key] = []
    sections["other"] = []

    for commit in commits:
        info = parse_conventional(commit["subject"], commit["body"])
        if info:
            type_ = info["type"].lower()
            is_breaking = bool(info["breaking"])
            desc = info["description"].strip()
            commit["category_type"] = type_
            commit["parsed_description"] = desc
            commit["is_breaking"] = is_breaking
            commit["scope"] = info.get("scope") or ""
            if is_breaking and type_ in SECTIONS:
                sections["breaking"].append(commit)
            elif type_ in sections:
                sections[type_].append(commit)
            else:
                sections["other"].append(commit)
        else:
            commit["category_type"] = "other"
            commit["parsed_description"] = commit["subject"]
            commit["is_breaking"] = False
            commit["scope"] = ""
            sections["other"].append(commit)
    return sections


def format_migration(body):
    lines = body.split("\n")
    notices = []
    for line in lines:
        if MIGRATION_PREFIXES.match(line.strip()):
            notices.append(line.strip())
    return notices


def format_entry(commit, template):
    author_link = f"[{commit['author_name']}](https://github.com/{commit['author_name']})"
    desc = commit["parsed_description"]
    if commit["scope"]:
        desc = f"**{commit['scope']}**: {desc}"
    entry = f"- {desc} ({author_link})"
    if template == "detailed":
        date = datetime.fromisoformat(commit["date"]).strftime("%Y-%m-%d")
        short_hash = commit["hash"][:7]
        entry = f"- {desc} ({author_link}) — {date}, `{short_hash}`"
    return entry


def render_section(name, commits, template):
    if not commits:
        return ""
    lines = []
    heading = SECTIONS.get(name, f"## 🔧 {name.capitalize()}")
    if name == "other" and not any(s["category_type"] == "other" for s in commits):
        heading = "## 🔧 Other"
    lines.append(heading)
    for commit in commits:
        entry = format_entry(commit, template)
        migration_notices = format_migration(commit["body"])
        if migration_notices:
            entry += "\n" + "\n".join(f"  > **{n}**" for n in migration_notices)
        lines.append(entry)
    lines.append("")
    return "\n".join(lines)


def render_breaking_section(commits, template):
    if not commits:
        return ""
    lines = [
        "## ⚠️ Breaking Changes",
        "",
        "> [!ALERT]",
        "> This release contains breaking changes. Please review before upgrading.",
        "",
    ]
    for commit in commits:
        entry = format_entry(commit, template)
        lines.append(entry)
    lines.append("")
    return "\n".join(lines)


def render_contributors(commits):
    seen = OrderedDict()
    for commit in commits:
        key = commit["author_email"]
        if key not in seen:
            seen[key] = commit["author_name"]
    if not seen:
        return ""
    lines = ["## 👥 Contributors", ""]
    for name in seen.values():
        lines.append(f"- [{name}](https://github.com/{name})")
    lines.append("")
    return "\n".join(lines)


def render_stats(repo, from_ref, to_ref, commits):
    if not commits:
        return ""
    diff = run_git_quiet(["diff", "--stat", f"{from_ref}..{to_ref}"], repo)
    if not diff:
        return f"{len(commits)} commits\n"
    last_line = diff.strip().split("\n")[-1]
    m = re.search(r"(\d+) files? changed", last_line)
    files_changed = m.group(1) if m else "?"
    plus = len(re.findall(r"\+", re.sub(r"\+.*", "", last_line)))
    minus = len(re.findall(r"-", re.sub(r"-.*", "", last_line)))
    plus_count = len(re.findall(r"\+\d+", last_line))
    minus_count = len(re.findall(r"-\d+", last_line))
    m2 = re.search(r"(\d+) insertion", last_line)
    m3 = re.search(r"(\d+) deletion", last_line)
    insertions = m2.group(1) if m2 else "?"
    deletions = m3.group(1) if m3 else "?"
    return f"{len(commits)} commits, {files_changed} files changed, {insertions}+, {deletions}-\n"


def generate_release_notes(repo, from_ref, to_ref, project_name, version, template):
    commits = parse_commits(repo, from_ref, to_ref)
    sections = categorize_commits(commits)

    lines = []
    lines.append(f"# {project_name}")
    lines.append("")
    lines.append(f"## {version}")
    lines.append("")

    stats = render_stats(repo, from_ref, to_ref, commits)
    if stats:
        lines.append(stats)
        lines.append("")

    breaking_commits = sections.pop("breaking", [])
    if breaking_commits:
        lines.append(render_breaking_section(breaking_commits, template))
        lines.append("")

    for name in SECTION_ORDER:
        if name in ("breaking",):
            continue
        commits_in_section = sections.get(name, [])
        section_text = render_section(name, commits_in_section, template)
        if section_text:
            lines.append(section_text)

    other_commits = sections.get("other", [])
    if other_commits:
        section_text = render_section("other", other_commits, template)
        if section_text:
            lines.append(section_text)

    contributors_text = render_contributors(commits)
    if contributors_text:
        lines.append(contributors_text)

    return "\n".join(lines).strip() + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Generate human-readable release notes from git history."
    )
    parser.add_argument("--from", dest="from_ref", default=None,
                        help="Starting tag or commit (default: last tag)")
    parser.add_argument("--to", dest="to_ref", default="HEAD",
                        help="Ending tag or commit (default: HEAD)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file (default: stdout)")
    parser.add_argument("--repo", default=".",
                        help="Path to git repository (default: current dir)")
    parser.add_argument("--version", default=None,
                        help="Version header text (default: from tag or 'Unreleased')")
    parser.add_argument("--project-name", default=None,
                        help="Project name (default: repo directory basename)")
    parser.add_argument("--template", choices=["simple", "detailed"], default="simple",
                        help="Output template style (default: simple)")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)

    if not os.path.isdir(os.path.join(repo, ".git")):
        print(f"Error: {repo} is not a git repository", file=sys.stderr)
        sys.exit(1)

    project_name = args.project_name or os.path.basename(repo)

    if args.from_ref:
        from_ref = args.from_ref
    else:
        last_tag = get_last_tag(repo)
        if last_tag:
            from_ref = last_tag
        else:
            first = get_first_commit(repo)
            if first:
                from_ref = first
            else:
                print("Error: no tags and no commits found", file=sys.stderr)
                sys.exit(1)

    to_ref = args.to_ref

    version = args.version
    if not version:
        if args.from_ref:
            version = args.from_ref
        else:
            last_tag = get_last_tag(repo)
            version = last_tag or "Unreleased"

    notes = generate_release_notes(repo, from_ref, to_ref, project_name, version, args.template)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(notes)
    else:
        sys.stdout.write(notes)


if __name__ == "__main__":
    main()
