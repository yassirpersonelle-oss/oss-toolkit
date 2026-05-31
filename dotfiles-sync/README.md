# dotfiles-sync

Watch your `~/.config/` and auto-commit changes to a local dotfiles git repo.

## Why Dotfiles Matter

Keep your configuration backed up, versioned, and reproducible across machines.

## Usage

### One-shot sync (cron-friendly)

```bash
python dotfiles-sync.py --once
```

### Daemon mode

```bash
python dotfiles-sync.py --watch ~/.config --repo ~/dotfiles --interval 300
```

### With auto-push

```bash
python dotfiles-sync.py --auto-push
```

## Options

| Flag              | Description                              |
|-------------------|------------------------------------------|
| `--watch`, `-w`   | Path to watch (default: ~/.config)        |
| `--repo`, `-r`    | Path to dotfiles git repo (default: ~/dotfiles) |
| `--interval`, `-i`| Poll interval in seconds (default: 300)   |
| `--auto-push`     | Push to remote after each commit          |
| `--once`          | Single sync and exit (for cron)           |

## Cron Job

```
*/10 * * * * /usr/bin/python3 /path/to/dotfiles-sync.py --once
```

## Setup

1. Create a bare repo: `git init --bare ~/dotfiles`
2. Or use a regular repo: `git init ~/dotfiles && git remote add origin <url>`
3. Run dotfiles-sync
