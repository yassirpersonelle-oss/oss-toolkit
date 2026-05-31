# gh-backup

> Your OSS project deserves a backup plan.

**gh-backup** is a zero-dependency Python CLI that backs up an entire GitHub repository — issues, pull requests, discussions, releases, and the git history itself — to local markdown files. One command, local archive.

## Why?

- **GitHub downtime** — even GitHub has blips. Your issues and PRs aren't backed up anywhere else.
- **Account issues** — locked out, banned, or deleted? Your project data shouldn't disappear.
- **Project transitions** — moving away from GitHub? Take your full project history with you.

## Installation

```bash
git clone https://github.com/your-org/gh-backup.git
cd gh-backup
# No dependencies — uses only Python stdlib + urllib
```

## Usage

```bash
# Basic backup (public repo, no token — lower rate limits)
python gh-backup.py --repo owner/repo

# With GitHub token (recommended — 5000 req/hr)
python gh-backup.py --repo owner/repo --token ghp_xxxxxxxxxxxx

# Via environment variable
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
python gh-backup.py --repo owner/repo

# Custom output directory
python gh-backup.py --repo owner/repo --output ./my-backups/project

# Selective backup (only issues and PRs)
python gh-backup.py --repo owner/repo --include issues,prs

# Limit pages (100 items per page)
python gh-backup.py --repo owner/repo --pages 3

# Skip git mirror clone for large repos
python gh-backup.py --repo owner/repo --skip-clone

# Verbose progress
python gh-backup.py --repo owner/repo --verbose
```

### Output structure

```
backups/
  owner/
    repo/
      README.md
      meta.json
      issues/
        issue-1.md
        issue-2.md
        ...
      prs/
        pr-1.md
        pr-2.md
        ...
      releases/
        v1.0.0.md
        v1.1.0.md
        ...
      discussions/
        discussion-1.md
        ...
      .git/          (mirror clone, unless --skip-clone)
```

## Permissions

- **Public repos**: No token needed (unauthenticated — 60 req/hr limit).
- **Private repos**: Token requires `repo` scope.
- **Discussions API**: Requires a token with appropriate scopes; may not be available on all repo types.

A [classic personal access token](https://github.com/settings/tokens) with `repo` scope works for all cases.

## Restore

gh-backup is backup-only. To restore, you would:

1. **Issues/PRs**: Use the GitHub API or import tools like `github-issue-importer` to recreate issues and PRs from the markdown files.
2. **Git history**: Push the mirrored `.git` to a new remote:
   ```bash
   cd backups/owner/repo/.git
   git remote add new-origin https://github.com/new-owner/new-repo.git
   git push --mirror new-origin
   ```
3. **Releases**: Recreate releases via the GitHub UI or API from the markdown notes.

## Cron (scheduled backups)

Back up your critical repos daily:

```cron
# Every day at 3am
0 3 * * * cd /path/to/gh-backup && python gh-backup.py --repo owner/repo --token $(cat ~/.github-token) --skip-clone >> backup.log 2>&1
```

For multiple repos, wrap in a shell script:

```bash
#!/bin/bash
REPOS=("owner/repo1" "owner/repo2" "org/repo3")
for REPO in "${REPOS[@]}"; do
  python gh-backup.py --repo "$REPO" --token "$GITHUB_TOKEN" --skip-clone
done
```
