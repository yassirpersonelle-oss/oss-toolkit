#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone


def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto-label good first issues and generate contributing docs"
    )
    parser.add_argument("-r", "--repo", default=None,
                        help="Repository (owner/repo). Detected from git remote or GITHUB_REPOSITORY")
    parser.add_argument("--token", default=None,
                        help="GitHub API token. Falls back to GITHUB_TOKEN env")
    parser.add_argument("--label", default="good first issue",
                        help="Label name to apply (default: good first issue)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be labeled without applying labels")
    parser.add_argument("--generate-contributing", action="store_true",
                        help="Generate CONTRIBUTING.md sections")
    return parser.parse_args()


def detect_repo():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        url = result.stdout.strip()
        for prefix in ["https://github.com/", "git@github.com:"]:
            if prefix in url:
                repo = url.split(prefix, 1)[1]
                break
        if repo:
            repo = repo.replace(".git", "")
        return repo
    except Exception:
        return None


def api_request(url, token):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "contributor-welcome")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 403:
            print("Rate limited. Provide a token.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def get_issues(repo, token):
    issues = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100&page={page}"
        data = api_request(url, token)
        if data is None:
            return None
        if not data:
            break
        issues.extend(data)
        page += 1
    issues = [i for i in issues if "pull_request" not in i]
    return issues


def score_issue(issue):
    score = 0
    label_names = [lbl["name"].lower() for lbl in issue.get("labels", [])]
    body = issue.get("body") or ""

    if "bug" in label_names and not any(l in label_names for l in ["critical", "blocker", "security"]):
        score += 1
    if "documentation" in label_names:
        score += 1
    if "enhancement" in label_names:
        score += 1
    if "help wanted" in label_names:
        score += 1
    if len(body) < 200:
        score += 2
    if re.search(r'[\w./\\-]+\.[a-zA-Z]{2,4}:\d+', body) or \
       re.search(r'`[\w./\\-]+\.[a-zA-Z]{2,4}`', body) or \
       re.search(r'\bline\s+\d+\b', body, re.I):
        score += 2
    if re.search(r'(refactor|redesign|rewrite)', body, re.I):
        score -= 2
    if "discussion" in label_names or "question" in label_names:
        score -= 2
    if issue.get("assignee") is None:
        score += 1
    created_at = issue.get("created_at")
    if created_at:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).days > 30:
            score += 1
    if "security" in label_names or "blocker" in label_names:
        score -= 3

    return score


def label_issue(repo, issue_number, label, token):
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    data = json.dumps({"labels": [label]}).encode()
    req = urllib.request.Request(url, method="POST", data=data)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "contributor-welcome")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status in (200, 201)
    except Exception:
        return False


def detect_ecosystem():
    try:
        files = os.listdir(".")
    except Exception:
        return {"lang": "Unknown", "manager": "unknown", "has_docker": False, "has_ci": False}
    eco = {"lang": "Unknown", "manager": "unknown", "has_docker": False, "has_ci": False}
    if "package.json" in files:
        eco["lang"] = "Node.js"
        eco["manager"] = "npm"
    elif "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files or "setup.cfg" in files:
        eco["lang"] = "Python"
        eco["manager"] = "pip"
    elif "Cargo.toml" in files:
        eco["lang"] = "Rust"
        eco["manager"] = "cargo"
    elif "Gemfile" in files:
        eco["lang"] = "Ruby"
        eco["manager"] = "bundler"
    elif "go.mod" in files:
        eco["lang"] = "Go"
        eco["manager"] = "go mod"
    elif "pom.xml" in files:
        eco["lang"] = "Java"
        eco["manager"] = "mvn"
    elif "build.gradle" in files or "build.gradle.kts" in files:
        eco["lang"] = "Java"
        eco["manager"] = "gradle"
    elif "Makefile" in files or "makefile" in files:
        eco["lang"] = "C/C++"
        eco["manager"] = "make"
    if "Dockerfile" in files:
        eco["has_docker"] = True
    if os.path.isdir(".github/workflows"):
        eco["has_ci"] = True
    return eco


def generate_contributing(repo, label):
    eco = detect_ecosystem()
    lang = eco["lang"]
    manager = eco["manager"]
    lines = []

    lines.append("## Getting Started\n")
    if lang != "Unknown":
        lines.append(f"This is a **{lang}** project.\n\n")
    lines.append("1. **Fork** the repository and **clone** your fork.\n")
    lines.append("2. **Install dependencies:**\n")
    if manager == "npm":
        lines.append("   ```bash\n   npm install\n   ```\n")
    elif manager == "pip":
        lines.append("   ```bash\n   pip install -r requirements.txt\n   ```\n")
    elif manager == "cargo":
        lines.append("   ```bash\n   cargo build\n   ```\n")
    elif manager == "bundler":
        lines.append("   ```bash\n   bundle install\n   ```\n")
    elif manager == "go mod":
        lines.append("   ```bash\n   go mod download\n   ```\n")
    elif manager == "mvn":
        lines.append("   ```bash\n   mvn install\n   ```\n")
    elif manager == "gradle":
        lines.append("   ```bash\n   gradle build\n   ```\n")
    elif manager == "make":
        lines.append("   ```bash\n   make\n   ```\n")
    else:
        lines.append("   Follow the instructions in the project's documentation.\n")
    if eco["has_docker"]:
        lines.append("\n   Or use Docker:\n   ```bash\n   docker build -t project .\n   docker run -it project\n   ```\n")
    lines.append("\n")

    lines.append("## Finding Good First Issues\n")
    lines.append(f"We label beginner-friendly issues with the **\"{label}\"** label. ")
    if repo:
        lines.append(f"[Browse good first issues](https://github.com/{repo}/issues?q=is%3Aissue+is%3Aopen+label%3A%22{label.replace(' ', '+')}%22)\n\n")
    else:
        lines.append("Check the Issues tab and filter by that label.\n\n")
    lines.append("If you're new to the project, start there\u2014they are well-scoped and have clear instructions.\n\n")

    lines.append("## Running Locally\n")
    if manager == "npm":
        lines.append("```bash\n# Start development server\nnpm run dev\n\n# Run tests\nnpm test\n```\n")
    elif manager == "pip":
        lines.append("```bash\n# Run the project\npython main.py\n\n# Run tests\npython -m pytest\n```\n")
    elif manager == "cargo":
        lines.append("```bash\n# Build and run\ncargo run\n\n# Run tests\ncargo test\n```\n")
    elif manager == "bundler":
        lines.append("```bash\n# Run tests\nbundle exec rspec\n```\n")
    elif manager == "go mod":
        lines.append("```bash\n# Build and run\ngo run .\n\n# Run tests\ngo test ./...\n```\n")
    elif manager == "mvn":
        lines.append("```bash\n# Run tests\nmvn test\n```\n")
    elif manager == "gradle":
        lines.append("```bash\n# Run tests\ngradle test\n```\n")
    elif manager == "make":
        lines.append("```bash\n# Build\nmake\n\n# Run tests\nmake test\n```\n")
    else:
        lines.append("Refer to the project's documentation for instructions.\n")
    lines.append("\n")

    lines.append("## Submitting a PR\n")
    lines.append("1. Create a new branch: `git checkout -b my-feature-branch`\n")
    lines.append("2. Make your changes and commit them: `git commit -m 'Add feature'`\n")
    lines.append("3. Push to your fork: `git push origin my-feature-branch`\n")
    lines.append("4. Open a pull request against the `main` (or `master`) branch.\n")
    lines.append("5. In your PR description, reference the issue it addresses (e.g., \"Closes #42\").\n")
    lines.append("6. Wait for a maintainer to review. Address any feedback promptly.\n\n")

    lines.append("## Code Style\n")
    if lang == "Node.js":
        lines.append("- Run `npm run lint` to check for style issues.\n")
        lines.append("- We use Prettier for formatting. Run `npm run format` before committing.\n")
    elif lang == "Python":
        lines.append("- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide.\n")
        lines.append("- Run `flake8` or `pylint` before submitting.\n")
        lines.append("- Use `black` for auto-formatting: `black .`\n")
    elif lang == "Rust":
        lines.append("- Run `cargo clippy` to catch common mistakes.\n")
        lines.append("- Run `cargo fmt` to auto-format your code.\n")
    elif lang == "Go":
        lines.append("- Run `gofmt` to format your code.\n")
        lines.append("- Run `go vet` to check for suspicious constructs.\n")
    elif lang == "Ruby":
        lines.append("- Run `rubocop` to check for style issues.\n")
    else:
        lines.append("- Check if a linter config exists (e.g., `.eslintrc`, `.flake8`, `rustfmt.toml`).\n")
        lines.append("- Run the project's linter before submitting.\n")
    lines.append("- Keep your changes focused\u2014one PR per feature or fix.\n")

    return "".join(lines)


def main():
    args = parse_args()
    token = args.token or os.environ.get("GITHUB_TOKEN")
    repo = args.repo or detect_repo()
    label = args.label

    if not repo:
        print("Could not detect repository. Provide --repo or set GITHUB_REPOSITORY.", file=sys.stderr)
        sys.exit(1)

    if args.generate_contributing:
        text = generate_contributing(repo, label)
        with open("CONTRIBUTING.md", "a") as f:
            f.write("\n" + text)
        print(text)

    if not token:
        if args.generate_contributing:
            print("Found 0 open issues. Labeled 0 as '{0}'. Generated CONTRIBUTING.md template.".format(label))
            return
        print("No GitHub token provided. Use --token or set GITHUB_TOKEN.", file=sys.stderr)
        sys.exit(1)

    issues = get_issues(repo, token)
    if issues is None:
        if args.generate_contributing:
            print("Found 0 open issues. Labeled 0 as '{0}'. Generated CONTRIBUTING.md template.".format(label))
            return
        sys.exit(1)

    labeled = 0
    for issue in issues:
        if any(lbl["name"].lower() == label.lower() for lbl in issue.get("labels", [])):
            continue
        s = score_issue(issue)
        if s >= 5:
            num = issue["number"]
            title = issue["title"]
            if args.dry_run:
                print(f"[DRY RUN] Would label #{num}: {title} (score={s})")
                labeled += 1
            else:
                if label_issue(repo, num, label, token):
                    print(f"Labeled #{num}: {title} (score={s})")
                    labeled += 1
                else:
                    print(f"Failed to label #{num}: {title}", file=sys.stderr)

    summary = f"Found {len(issues)} open issues. Labeled {labeled} as '{label}'."
    if args.generate_contributing:
        summary += " Generated CONTRIBUTING.md template."
    print(summary)


if __name__ == "__main__":
    main()
