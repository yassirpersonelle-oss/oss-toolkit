# Keepalive Action

Prevents GitHub from automatically disabling cron-triggered workflows after 60 days of inactivity.

## Problem

GitHub Actions disables scheduled workflows in public repositories that haven't had a commit in 60 days. This action prevents that by making a small weekly commit that updates a timestamp file (`.github/keepalive`).

## Usage

```yaml
name: Keepalive
on:
  schedule:
    - cron: '0 0 * * 0'  # weekly
jobs:
  keepalive:
    runs-on: ubuntu-latest
    steps:
      - uses: yassir/oss-toolkit/keepalive-action@main
```

### Inputs

| Input            | Required | Default                | Description                              |
|------------------|----------|------------------------|------------------------------------------|
| `auto_push`      | No       | `true`                 | Whether to auto-commit and push changes  |
| `commit_message` | No       | `chore: keepalive ping`| Commit message for the keepalive ping    |

### Example with custom message

```yaml
- uses: yassir/oss-toolkit/keepalive-action@main
  with:
    commit_message: 'chore: weekly keepalive'
```

### Disable auto-push (manual commit)

```yaml
- uses: yassir/oss-toolkit/keepalive-action@main
  with:
    auto_push: 'false'
```
