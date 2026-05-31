#!/usr/bin/env python3
"""UI Scale Optimizer — Scan Roblox Luau scripts for UDim2 scaling issues."""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

SCREEN_REF_W = 1920
SCREEN_REF_H = 1080

DEVICE_PRESETS = {
    "iPhone SE (375x667)": (375, 667),
    "iPhone 14 Pro (393x852)": (393, 852),
    "iPad (768x1024)": (768, 1024),
    "iPad Pro (1024x1366)": (1024, 1366),
    "1080p (1920x1080)": (1920, 1080),
}

UDIM_NEW_RE = re.compile(
    r"UDim2\.new\s*\(\s*"
    r"([\d.]+)\s*,\s*([\d.-]+)\s*,\s*"
    r"([\d.]+)\s*,\s*([\d.-]+)\s*"
    r"\)",
    re.IGNORECASE,
)

UDIM_FROMSCALE_RE = re.compile(
    r"UDim2\.fromScale\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)",
    re.IGNORECASE,
)

UDIM_FROMOFFSET_RE = re.compile(
    r"UDim2\.fromOffset\s*\(\s*([\d.-]+)\s*,\s*([\d.-]+)\s*\)",
    re.IGNORECASE,
)

ANCHOR_POINT_RE = re.compile(
    r"\.AnchorPoint\s*=\s*Vector2\.new\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)",
    re.IGNORECASE,
)

TEXT_SIZE_RE = re.compile(r"\.TextSize\s*=\s*(\d+)", re.IGNORECASE)

FRAME_SIZE_RE = re.compile(r"\.Size\s*=\s*UDim2\.new\s*\([\d.,\s]+\)", re.IGNORECASE)

SCALE_SMALL_OFFSET_THRESHOLD = 50
LARGE_OFFSET_THRESHOLD = 300
LARGE_TEXT_THRESHOLD = 48

SEVERITY_GOOD = "GOOD"
SEVERITY_OK = "OK"
SEVERITY_REVIEW = "REVIEW"
SEVERITY_FIX = "FIX"


@dataclass
class Finding:
    severity: str
    file: str
    line: int
    context: str
    scale_x: float = 0.0
    offset_x: float = 0.0
    scale_y: float = 0.0
    offset_y: float = 0.0
    suggestion: str = ""
    overflow: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)


def parse_udim_new(match) -> tuple[float, float, float, float]:
    return (
        float(match.group(1)),
        float(match.group(2)),
        float(match.group(3)),
        float(match.group(4)),
    )


def classify_udim(sx: float, ox: float, sy: float, oy: float) -> str:
    has_scale = sx > 0 or sy > 0
    has_offset = abs(ox) > 0 or abs(oy) > 0
    large_offset = max(abs(ox), abs(oy)) > SCALE_SMALL_OFFSET_THRESHOLD
    huge_offset = max(abs(ox), abs(oy)) >= LARGE_OFFSET_THRESHOLD

    if has_scale and not has_offset:
        return SEVERITY_GOOD
    if has_scale and has_offset and not large_offset:
        return SEVERITY_OK
    if has_scale and has_offset and large_offset:
        return SEVERITY_REVIEW
    if not has_scale and has_offset:
        return SEVERITY_FIX
    if not has_scale and not has_offset:
        return SEVERITY_OK
    return SEVERITY_REVIEW


def suggest_fix(sx: float, ox: float, sy: float, oy: float, raw_line: str) -> str:
    is_size = ".Size" in raw_line or "Size" in raw_line
    is_position = ".Position" in raw_line or "Position" in raw_line

    if sx == 0 and ox != 0 and sy == 0 and oy != 0:
        if is_size:
            w_approx = min(ox / SCREEN_REF_W, 1.0)
            h_approx = min(oy / SCREEN_REF_H, 1.0)
            return (
                f"UDim2.new({w_approx:.3f},0,{h_approx:.3f},0) -- converts "
                f"{ox:.0f}x{oy:.0f}px offset to scale"
            )
        return "UDim2.fromScale(X, Y) where X,Y = desired fraction of screen"
    if sx > 0 and (abs(ox) > SCALE_SMALL_OFFSET_THRESHOLD or abs(oy) > SCALE_SMALL_OFFSET_THRESHOLD):
        w_r = min(ox / SCREEN_REF_W, 1.0)
        h_r = min(oy / SCREEN_REF_H, 1.0)
        return (
            f"UDim2.new({sx + w_r:.3f},0,{sy + h_r:.3f},0) -- absorbed "
            f"{ox:.0f}x{oy:.0f}px offset into scale"
        )
    return "Replace offset with proportional scale values"


def compute_overflow(sx: float, ox: float, sy: float, oy: float) -> dict:
    overflows = {}
    for name, (dw, dh) in DEVICE_PRESETS.items():
        w = sx * dw + ox
        h = sy * dh + oy
        overflows[name] = {
            "device_width": dw,
            "device_height": dh,
            "element_width": round(w, 1),
            "element_height": round(h, 1),
            "overflow_x": round(max(0, w - dw), 1),
            "overflow_y": round(max(0, h - dh), 1),
        }
    return overflows


def check_text_size(value: int, line: str) -> list[str]:
    issues = []
    if value >= LARGE_TEXT_THRESHOLD:
        issues.append(f"TextSize={value} may overflow on small screens")
    return issues


def check_anchor_point(x_scale: float, y_scale: float, anchor_x: float, anchor_y: float) -> list[str]:
    issues = []
    if x_scale > 0 and x_scale < 1 and anchor_x == 0:
        issues.append("Scale used but AnchorPoint.X=0 (should be 0.5 for centering)")
    if y_scale > 0 and y_scale < 1 and anchor_y == 0:
        issues.append("Scale used but AnchorPoint.Y=0 (should be 0.5 for centering)")
    return issues


def scan_file(filepath: str) -> list[Finding]:
    findings = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return findings

    recent_anchor = (0.0, 0.0)

    for idx, line in enumerate(lines, 1):
        anchor_m = ANCHOR_POINT_RE.search(line)
        if anchor_m:
            recent_anchor = (float(anchor_m.group(1)), float(anchor_m.group(2)))

        ts_m = TEXT_SIZE_RE.search(line)
        if ts_m:
            ts_value = int(ts_m.group(1))
            issues = check_text_size(ts_value, line)
            if issues:
                findings.append(Finding(
                    severity=SEVERITY_REVIEW,
                    file=filepath,
                    line=idx,
                    context=line.strip()[:120],
                    checks=issues,
                    suggestion=f"Consider using UIAspectRatioConstraint or scaled TextSize relative to screen",
                ))

        fs_match = UDIM_FROMSCALE_RE.search(line)
        if fs_match:
            sx, sy = float(fs_match.group(1)), float(fs_match.group(2))
            findings.append(Finding(
                severity=SEVERITY_GOOD,
                file=filepath,
                line=idx,
                context=line.strip()[:120],
                scale_x=sx,
                scale_y=sy,
                suggestion="",
            ))
            continue

        fo_match = UDIM_FROMOFFSET_RE.search(line)
        if fo_match:
            ox, oy = float(fo_match.group(1)), float(fo_match.group(2))
            sev = classify_udim(0, ox, 0, oy)
            overflows = compute_overflow(0, ox, 0, oy)
            checks = []
            if abs(ox) >= LARGE_OFFSET_THRESHOLD or abs(oy) >= LARGE_OFFSET_THRESHOLD:
                checks.append(f"Large offset: {ox:.0f}x{oy:.0f}px — exceeds {LARGE_OFFSET_THRESHOLD}px threshold")
            findings.append(Finding(
                severity=sev,
                file=filepath,
                line=idx,
                context=line.strip()[:120],
                offset_x=ox,
                offset_y=oy,
                checks=checks,
                suggestion=suggest_fix(0, ox, 0, oy, line),
                overflow=overflows,
            ))
            continue

        udim_match = UDIM_NEW_RE.search(line)
        if udim_match:
            sx, ox, sy, oy = parse_udim_new(udim_match)
            sev = classify_udim(sx, ox, sy, oy)
            overflows = compute_overflow(sx, ox, sy, oy)
            checks = []

            if sev in (SEVERITY_FIX, SEVERITY_REVIEW):
                if sx == 0 and sy == 0:
                    checks.append("No scale component — size depends entirely on pixels")
                if abs(ox) >= LARGE_OFFSET_THRESHOLD or abs(oy) >= LARGE_OFFSET_THRESHOLD:
                    checks.append(f"Large offset ({ox:.0f}x{oy:.0f}px) — likely assumes 1920x1080")
            anchor_issues = check_anchor_point(sx, sy, recent_anchor[0], recent_anchor[1])
            checks.extend(anchor_issues)

            findings.append(Finding(
                severity=sev,
                file=filepath,
                line=idx,
                context=line.strip()[:120],
                scale_x=sx,
                offset_x=ox,
                scale_y=sy,
                offset_y=oy,
                checks=checks,
                suggestion=suggest_fix(sx, ox, sy, oy, line),
                overflow=overflows,
            ))

    return findings


def scan_directory(dirpath: str) -> list[Finding]:
    all_findings = []
    for root, _, files in os.walk(dirpath):
        for name in files:
            if name.endswith((".luau", ".lua")):
                all_findings.extend(scan_file(os.path.join(root, name)))
    return all_findings


def render_text_report(findings: list[Finding], dirpath: str, verbose: bool, fix: bool):
    by_sev = defaultdict(list)
    for f in findings:
        by_sev[f.severity].append(f)

    file_count = len(set(f.file for f in findings))
    sep = "-" * 60

    print(f"\nUI Scale Optimizer -- {dirpath}")
    print(sep)
    print(f"\n  Found: {len(findings)} UI elements across {file_count} files\n")

    sev_labels = {
        SEVERITY_FIX: "[FIX] HARDCODED OFFSET",
        SEVERITY_REVIEW: "[REVIEW] MIXED SCALE",
        SEVERITY_OK: "[OK]",
        SEVERITY_GOOD: "[GOOD] SCALE",
    }

    for sev in [SEVERITY_FIX, SEVERITY_REVIEW, SEVERITY_OK, SEVERITY_GOOD]:
        items = by_sev.get(sev, [])
        if not items:
            continue
        print(f"  {sev_labels[sev]} ({len(items)})")
        for f in items[:30] if not verbose else items:
            fname = os.path.basename(f.file)
            print(f"     {fname}:{f.line}  {f.context}")
            for check in f.checks:
                print(f"       -> {check}")
            if fix and f.suggestion:
                print(f"       Fix: {f.suggestion}")
            if sev in (SEVERITY_FIX, SEVERITY_REVIEW) and f.overflow:
                worst = max(
                    f.overflow.values(),
                    key=lambda v: v["overflow_x"] + v["overflow_y"],
                )
                if worst["overflow_x"] > 0 or worst["overflow_y"] > 0:
                    print(
                        f"       -> On {worst['device_width']}px wide screen: "
                        f"overflows by {worst['overflow_x']:.0f}x{worst['overflow_y']:.0f}px"
                    )
        if len(items) > 30 and not verbose:
            print(f"       ... and {len(items) - 30} more (use --verbose for all)")
        print()

    if findings:
        print(f"  DEVICE PREVIEW (most common breakages)")
        for dname, (dw, dh) in DEVICE_PRESETS.items():
            overflow_count = 0
            for f in findings:
                if f.overflow:
                    ov = f.overflow.get(dname, {})
                    if ov.get("overflow_x", 0) > 0 or ov.get("overflow_y", 0) > 0:
                        overflow_count += 1
            label = f"{overflow_count} overflow{'s' if overflow_count != 1 else ''}" if overflow_count else "0 issues"
            print(f"     {dname:30s} {label}")
        print()

    fix_count = len(by_sev.get(SEVERITY_FIX, []))
    review_count = len(by_sev.get(SEVERITY_REVIEW, []))
    if fix_count or review_count:
        print(f"  [!] Summary: {fix_count} elements need fixing, {review_count} need review for mobile compatibility")
    else:
        print(f"  [OK] Summary: UI looks good across devices!")
    print()


def render_json_report(findings: list[Finding]):
    result = {
        "total_elements": len(findings),
        "files_scanned": len(set(f.file for f in findings)),
        "by_severity": {},
        "findings": [],
    }
    for f in findings:
        result["by_severity"].setdefault(f.severity, 0)
        result["by_severity"][f.severity] += 1
        result["findings"].append({
            "severity": f.severity,
            "file": f.file,
            "line": f.line,
            "context": f.context,
            "scale_x": f.scale_x,
            "offset_x": f.offset_x,
            "scale_y": f.scale_y,
            "offset_y": f.offset_y,
            "checks": f.checks,
            "suggestion": f.suggestion,
            "overflow": f.overflow,
        })
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Scan Roblox Luau scripts for UDim2 scaling issues."
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Directory containing .luau/.lua files to scan",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all findings (not just first 30 per category)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Include auto-generated fix suggestions",
    )

    args = parser.parse_args()
    target = args.path

    if not os.path.isdir(target):
        print(f"Error: '{target}' is not a directory or does not exist.", file=sys.stderr)
        sys.exit(1)

    findings = scan_directory(target)

    if args.json:
        render_json_report(findings)
    else:
        render_text_report(findings, target, args.verbose, args.fix)


if __name__ == "__main__":
    main()
