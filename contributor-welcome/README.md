# Contributor Welcome

Make your repository welcoming to first-time contributors.

## How It Works

New contributors often struggle to find a good place to start. **Contributor Welcome** solves this by:

1. **Scraping your open issues** via the GitHub API
2. **Scoring each issue** with a complexity heuristic (0–10)
3. **Auto-labeling** high-scoring issues as `good first issue`
4. **Generating CONTRIBUTING.md sections** to guide new contributors

### Complexity Scoring

| Criterion | Points |
|---|---|
| Has label `bug` (and not `critical`/`blocker`/`security`) | +1 |
| Has label `documentation` | +1 |
| Has label `enhancement` | +1 |
| Has label `help wanted` | +1 |
| Body length < 200 characters | +2 |
| Body mentions a specific file or line number | +2 |
| No assignee | +1 |
| Created > 30 days ago (cold issue) | +1 |
| Body mentions `refactor` / `redesign` / `rewrite` | –2 |
| Has label `discussion` or `question` | –2 |
| Has label `security` or `blocker` | –3 |

Issues with a **score ≥ 5** get labeled as `good first issue`.

## Usage

### As a GitHub Action (recommended)

Create `.github/workflows/contributor-welcome.yml`:

```yaml
name: Contributor Welcome
on:
  schedule:
    - cron: "0 12 * * 1"   # every Monday at noon
  workflow_dispatch:        # allow manual trigger

jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/contributor-welcome@v1
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          label: "good first issue"
          dry-run: "false"
          generate-contributing: "true"
```

### As a Standalone CLI

```bash
# Label qualifying issues
python contributor-welcome.py --repo owner/repo --token ghp_xxx

# Dry-run (see what would be labeled)
python contributor-welcome.py --repo owner/repo --token ghp_xxx --dry-run

# Generate CONTRIBUTING.md sections
python contributor-welcome.py --repo owner/repo --generate-contributing

# Use a custom label
python contributor-welcome.py --repo owner/repo --token ghp_xxx --label "beginner"
```

All options can be set via environment variables:
- `GITHUB_REPOSITORY` instead of `--repo`
- `GITHUB_TOKEN` instead of `--token`

## Example Output

```
Labeled #12: Fix typo in README (score=7)
Labeled #34: Add input validation for email field (score=6)
[DRY RUN] Would label #56: Write unit tests for auth module (score=5)

Found 23 open issues. Labeled 4 as 'good first issue'. Generated CONTRIBUTING.md template.
```
