#!/usr/bin/env python3
"""
Ansible Drift Detector - Run Ansible playbooks in check mode and report changes.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime


SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_NORMAL = "NORMAL"
SEVERITY_INFO = "INFO"

SEVERITY_ICONS = {
    SEVERITY_CRITICAL: "🔴",
    SEVERITY_HIGH: "🟡",
    SEVERITY_NORMAL: "⚪",
    SEVERITY_INFO: "🔵",
}

CRITICAL_PATTERNS = [
    r"ufw",
    r"firewalld",
    r"iptables",
    r"selinux",
    r"ssh",
    r"sshd",
    r"user\b",
    r"users",
    r"sudoers",
    r"authorized_keys",
    r"passwd",
    r"shadow",
    r"chmod.*[0-7]{3}[0-7]{3}[0-7]",  # dangerous permissions
    r"pam",
    r"audit",
]

HIGH_PATTERNS = [
    r"service",
    r"systemd",
    r"supervisor",
    r"nginx",
    r"apache",
    r"httpd",
    r"haproxy",
    r"package",
    r"apt",
    r"yum",
    r"dnf",
    r"pip",
    r"npm",
    r"cron",
    r"crontab",
    r"template",
    r"copy",
    r"lineinfile",
    r"blockinfile",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Detect configuration drift using Ansible check mode"
    )
    parser.add_argument(
        "-p", "--playbook", required=True, help="Path to the Ansible playbook"
    )
    parser.add_argument(
        "-i", "--inventory", default=None, help="Inventory file (optional)"
    )
    parser.add_argument(
        "-o", "--output", default="drift-report.md", help="Output file (default: drift-report.md)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of markdown")
    parser.add_argument("--verbose", action="store_true", help="Show detailed change info")
    parser.add_argument("--hosts", default=None, help="Limit to specific hosts (comma-separated)")
    parser.add_argument("--tags", default=None, help="Only check specific tags (comma-separated)")
    return parser.parse_args()


def verify_prerequisites(playbook_path):
    errors = []
    try:
        result = subprocess.run(
            ["ansible-playbook", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            errors.append("ansible-playbook command failed. Is Ansible installed?")
    except FileNotFoundError:
        errors.append("ansible-playbook not found. Please install Ansible: pip install ansible")
    except subprocess.TimeoutExpired:
        errors.append("ansible-playbook timed out during version check")

    if not os.path.isfile(playbook_path):
        errors.append(f"Playbook not found: {playbook_path}")

    return errors


def run_check_mode(playbook, inventory=None, hosts=None, tags=None):
    cmd = ["ansible-playbook", playbook, "--check", "--diff"]

    if inventory:
        cmd.extend(["-i", inventory])
    if hosts:
        cmd.extend(["--limit", hosts])
    if tags:
        cmd.extend(["--tags", tags])

    cmd.append("-v")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "ERROR: Playbook execution timed out after 600 seconds", 1
    except Exception as e:
        return f"ERROR: Failed to run playbook: {e}", 1


def classify_severity(task_name, module, diff_text):
    text = f"{task_name} {module} {diff_text}".lower()

    for pattern in CRITICAL_PATTERNS:
        if re.search(pattern, text):
            return SEVERITY_CRITICAL

    for pattern in HIGH_PATTERNS:
        if re.search(pattern, text):
            return SEVERITY_HIGH

    return SEVERITY_NORMAL


def parse_playbook_output(output):
    results = {
        "total_tasks": 0,
        "would_change": [],
        "already_ok": [],
        "failed": [],
    }

    task_blocks = re.split(r"(?=TASK|PLAY|PLAY RECAP)", output)

    current_host = None
    current_play = None

    for block in task_blocks:
        play_match = re.search(r"PLAY\s+\[([^\]]*)\]", block)
        if play_match:
            current_play = play_match.group(1).strip()
            if current_play.startswith("***"):
                current_play = current_play.strip("*").strip()
            continue

        task_match = re.search(
            r"TASK\s+\[(.+?)(?:\s*\*\*\*.*?)?\]\s*$",
            block,
            re.MULTILINE
        )
        if not task_match:
            continue

        task_line = task_match.group(1).strip()
        task_name = task_line
        task_target = None

        if ":" in task_line:
            parts = task_line.split(":", 1)
            task_name = parts[0].strip()
            task_target = parts[1].strip() if len(parts) > 1 else None

        task_data = {
            "task": task_name,
            "target": task_target or current_play,
            "host": current_host or "unknown",
            "module": extract_module(block),
            "diff": extract_diff(block),
            "severity": SEVERITY_NORMAL,
        }

        results["total_tasks"] += 1

        changed = False
        failed = False

        if re.search(r"changed:\s*\{", block) or "would be changed" in block.lower():
            changed = True
        if re.search(r"changed:\s*\{.*?\"false\"", block):
            changed = False

        if re.search(r"ok:\s*\{", block) and not changed:
            results["already_ok"].append(task_data)
            task_data["severity"] = SEVERITY_INFO
            continue

        if re.search(r"FAILED|fatal:", block):
            failed = True
            results["failed"].append(task_data)
            continue

        if changed:
            task_data["severity"] = classify_severity(
                task_name, task_data["module"], task_data["diff"]
            )
            results["would_change"].append(task_data)

        host_match = re.search(r"(\S+)(?:\s*=>)?\s*:\s*(?:ok|changed|failed)", block)
        if host_match:
            current_host = host_match.group(1)

    return results


def extract_module(block):
    module_match = re.search(r"module_args:", block)
    if module_match:
        context = block[max(0, module_match.start() - 200):module_match.start()]
        mod = re.search(r"(\w+):\s*$", context, re.MULTILINE)
        if mod:
            return mod.group(1)

    for m in ["copy", "template", "service", "package", "apt", "yum", "dnf",
              "user", "group", "file", "lineinfile", "blockinfile", "command",
              "shell", "pip", "npm", "git", "cron", "systemd", "ufw",
              "firewalld", "iptables", "selinux", "get_url", "uri", "debug",
              "assert", "set_fact", "include_tasks", "import_tasks",
              "include_role", "import_role", "setup", "gather_facts"]:
        if re.search(rf"\b{m}\b", block[:500], re.IGNORECASE):
            return m

    return "unknown"


def extract_diff(block):
    diff_match = re.search(r"diff\s*\n(.+?)(?=changed:|ok:|failed:|PLAY RECAP|\Z)", block, re.DOTALL)
    if diff_match:
        diff_text = diff_match.group(1).strip()
        lines = diff_text.split("\n")
        meaningful = []
        for line in lines[:20]:
            if line.startswith(("+++", "---", "@@", "+", "-")):
                meaningful.append(line)
        if meaningful:
            return "\n".join(meaningful[:10])

    for line in block.split("\n"):
        if any(kw in line.lower() for kw in [
            "would be updated", "would be created", "would be removed",
            "would change", "would be changed", "does not exist"
        ]):
            return line.strip()

    return ""


def format_markdown(results, playbook, inventory):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = results["total_tasks"]
    changes = len(results["would_change"])
    ok = len(results["already_ok"])
    failed_count = len(results["failed"])

    lines = []
    lines.append("# Ansible Drift Report")
    lines.append("")
    lines.append(f"**Playbook:** `{os.path.basename(playbook)}`")
    lines.append(f"**Inventory:** `{inventory or '(default)'}`")
    lines.append(f"**Date:** {now}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- {total} tasks total")
    lines.append(f"- {changes} would change")
    lines.append(f"- {ok} already in desired state")
    lines.append(f"- {failed_count} failed")
    lines.append("")

    severity_order = [SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_NORMAL]
    severity_counts = {}
    for item in results["would_change"]:
        sev = item["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    for severity in severity_order:
        count = severity_counts.get(severity, 0)
        if count == 0:
            continue

        icon = SEVERITY_ICONS[severity]
        lines.append(f"## {icon} {severity} CHANGES ({count})")
        lines.append("")

        for item in results["would_change"]:
            if item["severity"] != severity:
                continue

            task_label = item["task"]
            if item["target"] and item["target"] != item["task"]:
                task_label = f"{item['target']}: {item['task']}"

            lines.append(f"### {task_label}")
            lines.append(f"- **Host:** {item['host']}")
            lines.append(f"- **Module:** {item['module']}")

            if item["diff"]:
                lines.append(f"- **Change:**")
                lines.append(f"  ```")
                for diff_line in item["diff"].split("\n"):
                    lines.append(f"  {diff_line}")
                lines.append(f"  ```")
            else:
                lines.append(f"- **Change:** Detected (run with --verbose for details)")

            lines.append("")

    if results["failed"]:
        lines.append("## ❌ FAILED TASKS")
        lines.append("")
        for item in results["failed"]:
            lines.append(f"### {item['task']}")
            lines.append(f"- **Host:** {item['host']}")
            lines.append(f"- **Module:** {item['module']}")
            lines.append(f"- **Status:** Failed")
            lines.append("")

    if results["already_ok"]:
        lines.append("## 🔵 OK (Already in desired state)")
        lines.append("")
        lines.append(f"**{len(results['already_ok'])} tasks** are already configured correctly.")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Click to expand OK tasks</summary>")
        lines.append("")
        for item in results["already_ok"]:
            task_label = item["task"]
            if item["target"] and item["target"] != item["task"]:
                task_label = f"{item['target']}: {item['task']}"
            lines.append(f"- {task_label} ({item['host']})")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by ansible-drift*")
    lines.append("")

    return "\n".join(lines)


def format_json(results, playbook, inventory):
    now = datetime.now().isoformat()
    output = {
        "playbook": playbook,
        "inventory": inventory,
        "date": now,
        "summary": {
            "total_tasks": results["total_tasks"],
            "would_change": len(results["would_change"]),
            "already_ok": len(results["already_ok"]),
            "failed": len(results["failed"]),
        },
        "changes": results["would_change"],
        "ok": results["already_ok"],
        "failed": results["failed"],
    }
    return json.dumps(output, indent=2)


def print_summary(results):
    total = results["total_tasks"]
    changes = len(results["would_change"])
    ok = len(results["already_ok"])
    failed_count = len(results["failed"])

    print(f"\n{'='*50}")
    print(f"  DRIFT SUMMARY")
    print(f"{'='*50}")
    print(f"  Total tasks:    {total}")
    print(f"  Would change:   {changes}")
    print(f"  Already OK:     {ok}")
    print(f"  Failed:         {failed_count}")

    if changes > 0:
        print(f"\n  Severity breakdown:")
        for sev in [SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_NORMAL]:
            count = sum(1 for c in results["would_change"] if c["severity"] == sev)
            if count > 0:
                icon = SEVERITY_ICONS[sev]
                print(f"    {icon} {sev}: {count}")

    print(f"{'='*50}\n")


def main():
    args = parse_args()

    errors = verify_prerequisites(args.playbook)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Running check mode on: {args.playbook}")
    raw_output, returncode = run_check_mode(
        args.playbook,
        inventory=args.inventory,
        hosts=args.hosts,
        tags=args.tags,
    )

    if not raw_output.strip():
        print("WARNING: No output captured from ansible-playbook", file=sys.stderr)
        if returncode != 0:
            print("Playbook exited with errors", file=sys.stderr)

    results = parse_playbook_output(raw_output)

    if args.verbose:
        print(f"\n--- Raw ansible-playbook output ---\n")
        print(raw_output)
        print(f"--- End output ---\n")

    print_summary(results)

    if args.json:
        output = format_json(results, args.playbook, args.inventory)
    else:
        output = format_markdown(results, args.playbook, args.inventory)

    with open(args.output, "w") as f:
        f.write(output)

    print(f"Report written to: {args.output}")

    if results["would_change"]:
        sys.exit(2)
    elif results["failed"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
