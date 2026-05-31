# ansible-drift

**Know exactly what's drifted from your Ansible config.**

## Why?

Configuration drift causes outages. Playbooks that were once correct slowly diverge from production as manual changes accumulate, patches modify configs, and team members make one-off fixes. By the time you notice, the drift is everywhere and hard to quantify.

`ansible-drift` makes drift visible. It runs your playbooks in Ansible's check mode, captures the output, and generates a clear report of every task that would change something — grouped by severity so you know what to fix first.

## Installation

Requires Python 3.7+ and Ansible installed.

```bash
pip install ansible
```

Clone or download `ansible-drift.py` — it's a single-file CLI tool with no dependencies beyond Python stdlib and Ansible.

## Usage

```bash
# Basic usage
python ansible-drift.py -p playbook.yml

# Specify inventory
python ansible-drift.py -p playbook.yml -i inventory/production

# Output to specific file
python ansible-drift.py -p deploy.yml -o my-report.md

# JSON output
python ansible-drift.py -p deploy.yml --json

# Limit to specific hosts
python ansible-drift.py -p deploy.yml --hosts web-01,web-02

# Only check specific tags
python ansible-drift.py -p deploy.yml --tags nginx,ssl

# Verbose mode (includes raw ansible output)
python ansible-drift.py -p deploy.yml --verbose
```

## CLI Options

| Flag | Description |
|------|-------------|
| `-p, --playbook` | Path to the Ansible playbook (required) |
| `-i, --inventory` | Inventory file (optional, uses Ansible defaults) |
| `-o, --output` | Output file path (default: `drift-report.md`) |
| `--json` | Output report as JSON instead of markdown |
| `--verbose` | Show raw ansible-playbook output |
| `--hosts` | Limit check to specific hosts (comma-separated) |
| `--tags` | Only check specific task tags (comma-separated) |

## How to Interpret Results

### Severity Levels

| Level | Meaning | Examples |
|-------|---------|----------|
| 🔴 **CRITICAL** | Security-related changes | Firewall rules, SSH config, user management, sudoers, SELinux |
| 🟡 **HIGH** | Service or package changes | Service restarts, package installs/removals, config file updates, cron jobs |
| ⚪ **NORMAL** | Low-risk changes | File permissions, variable updates, template rendering |
| 🔵 **INFO** | Already correct | Tasks that are already in the desired state (no action needed) |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No drift detected — everything is in desired state |
| `1` | Playbook execution failed or errored |
| `2` | Drift detected — tasks would change something |

Use exit codes in scripts:

```bash
python ansible-drift.py -p deploy.yml -i inventory/prod
if [ $? -eq 2 ]; then
    echo "Drift detected! Review the report."
    # send alert, open ticket, etc.
fi
```

## Running as a Scheduled Check

Set up a cron job (Linux) or scheduled task (Windows) to detect drift early.

### Linux (cron)

```bash
# Run daily at 6 AM
0 6 * * * cd /opt/ansible && python ansible-drift.py -p site.yml -i inventory/prod -o /var/reports/drift-$(date +\%F).md 2>&1 | logger -t ansible-drift
```

### GitHub Actions

```yaml
name: Drift Check
on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  check-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - run: pip install ansible
      - run: python ansible-drift.py -p site.yml -i inventory/prod --json -o drift-report.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: drift-report
          path: drift-report.json
```

### Using the Exit Code

```bash
# In a CI pipeline, fail if drift is detected
python ansible-drift.py -p deploy.yml -i inventory/prod
EXIT_CODE=$?
if [ $EXIT_CODE -eq 2 ]; then
    echo "::error::Configuration drift detected. Review drift-report.md."
    exit 1
fi
```

## Example Report

```markdown
# Ansible Drift Report
**Playbook:** deploy.yml
**Inventory:** production
**Date:** 2026-06-01 09:30:00

## Summary
- 42 tasks total
- 3 would change
- 39 already in desired state
- 0 failed

## 🔴 CRITICAL CHANGES (1)
### security: Add SSH key
- **Host:** prod-web-01
- **Module:** authorized_key
- **Change:** Would add key for user 'deploy'

## 🟡 HIGH CHANGES (2)
### nginx: Update vhost config
- **Host:** prod-web-01
- **Module:** template
- **Change:**
  ```diff
  -  server_name old.example.com;
  +  server_name new.example.com;
  ```

### packages: Ensure latest nginx
- **Host:** prod-web-01
- **Module:** apt
- **Change:** Would upgrade nginx 1.22.0 -> 1.24.0
```

## Tips

- Run `ansible-drift` before and after manual changes to verify your state.
- Compare reports over time by saving dated output files (`-o drift-$(date +%F).md`).
- Use `--tags` to focus on specific components (e.g., `--tags ssl,nginx`).
- The `--json` output works well with dashboards and alerting tools.
