# gh-draft

Preview before you publish. See the full PR diff before pushing, then push and open the PR in one command.

## Usage

```bash
# Preview changes compared to main
python gh-draft.py

# Preview against a different base branch
python gh-draft.py --base develop

# Skip preview, push and create PR immediately
python gh-draft.py --push --title "My feature" --body "Closes #123"

# Dry-run: see diff without pushing
python gh-draft.py --dry-run

# Show full diff without truncation
python gh-draft.py --more
```

## How It Works

1. Computes `git diff HEAD...<base>` to show a changes summary and preview
2. Prompts for confirmation before pushing
3. Pushes the current branch to `origin`
4. Creates a PR using `gh pr create` if available, otherwise opens a browser link

## Options

| Flag           | Description                          |
|----------------|--------------------------------------|
| `--base`, `-b` | Target branch (default: main)        |
| `--title`, `-t`| PR title                             |
| `--body`, `-B` | PR body                              |
| `--push`       | Skip preview, go straight to push+PR  |
| `--dry-run`    | Show diff without pushing            |
| `--more`        | Show full diff without truncation    |

## Requirements

- Git
- A remote named `origin`
- (Optional) GitHub CLI `gh` for automatic PR creation
