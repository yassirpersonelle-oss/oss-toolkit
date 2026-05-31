#!/usr/bin/env python3
"""image-slim: Analyze Dockerfiles and suggest ways to reduce image size."""

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_IMAGE_SIZES = {
    "alpine:3.18": 7, "alpine:3.17": 7, "alpine:latest": 7,
    "ubuntu:22.04": 77, "ubuntu:20.04": 72, "ubuntu:latest": 77,
    "debian:12": 116, "debian:11": 118, "debian:slim": 80,
    "python:3.12": 1010, "python:3.11": 920, "python:3.10": 910,
    "python:3.12-slim": 130, "python:3.11-slim": 120, "python:3.10-slim": 115,
    "python:3.12-alpine": 55, "python:3.11-alpine": 55,
    "node:20": 1100, "node:18": 1050, "node:20-slim": 200, "node:18-slim": 190,
    "node:20-alpine": 120, "node:18-alpine": 115,
    "golang:1.21": 800, "golang:1.20": 790,
    "golang:1.21-alpine": 250, "golang:1.21-slim": 200,
    "rust:1.73": 1300, "rust:1.73-slim": 200, "rust:1.73-alpine": 350,
    "openjdk:21": 450, "openjdk:17": 440, "openjdk:11": 430,
    "ruby:3.2": 350, "ruby:3.2-slim": 120, "ruby:3.2-alpine": 55,
    "php:8.2": 500, "php:8.2-cli": 450, "php:8.2-fpm": 480,
    "nginx:latest": 140, "nginx:alpine": 40,
    "redis:latest": 110, "redis:alpine": 35,
    "postgres:16": 380, "postgres:15": 370,
    "mysql:8": 550, "mongo:7": 700,
    "busybox:latest": 5, "scratch": 0,
}

BUILD_PACKAGES = {
    "apt": [
        "build-essential", "gcc", "g++", "make", "cmake", "autoconf",
        "automake", "pkg-config", "wget", "curl", "ca-certificates", "git",
        "libc6-dev", "linux-headers-generic", "perl", "python3-dev",
        "python3-setuptools", "python3-pip", "libffi-dev", "libssl-dev",
        "zlib1g-dev", "libbz2-dev", "libreadline-dev", "libsqlite3-dev",
        "libncurses5-dev", "libncursesw5-dev", "xz-utils", "tk-dev",
        "libxml2-dev", "libxmlsec1-dev", "liblzma-dev", "libsqlite3-dev",
        "rustc", "cargo", "protobuf-compiler", "libprotobuf-dev",
        "clang", "lld", "nasm", "yasm", "libtool",
    ],
    "apk": [
        "build-base", "gcc", "g++", "make", "cmake", "autoconf", "automake",
        "pkgconf", "wget", "curl", "ca-certificates", "git", "musl-dev",
        "linux-headers", "perl", "python3-dev", "py3-pip", "libffi-dev",
        "openssl-dev", "zlib-dev", "bzip2-dev", "readline-dev",
        "sqlite-dev", "ncurses-dev", "xz-dev", "tk-dev", "xml2-dev",
        "xmlsec-dev", "lzma-dev", "protobuf", "protoc", "clang", "lld",
        "nasm", "yasm", "libtool", "cargo", "rust",
    ],
    "yum": [
        "gcc", "gcc-c++", "make", "cmake", "autoconf", "automake",
        "pkgconfig", "wget", "curl", "ca-certificates", "git", "glibc-devel",
        "kernel-headers", "perl", "python3-devel", "python3-pip", "libffi-devel",
        "openssl-devel", "zlib-devel", "bzip2-devel", "readline-devel",
        "sqlite-devel", "ncurses-devel", "xz-devel", "libxml2-devel",
        "libtool", "protobuf-compiler", "protobuf-devel", "clang", "lld",
        "nasm", "yasm", "cargo", "rust",
    ],
}

UNNECESSARY_PACKAGES = {
    "apt": [
        ("man-db", "~12MB"), ("vim", "~8MB"), ("vim-common", "~8MB"),
        ("nano", "~2MB"), ("less", "~1MB"), ("wget", "~1MB"),
        ("telnet", "~1MB"), ("netcat", "~1MB"), ("tcpdump", "~2MB"),
        ("strace", "~1MB"), ("lsof", "~1MB"), ("htop", "~1MB"),
        ("sysstat", "~1MB"), ("rsync", "~1MB"), ("screen", "~1MB"),
        ("tmux", "~3MB"), ("openssh-client", "~2MB"),
    ],
    "apk": [
        ("man-db", "~12MB"), ("vim", "~8MB"), ("vim-common", "~8MB"),
        ("nano", "~2MB"), ("less", "~1MB"), ("wget", "~1MB"),
        ("htop", "~1MB"), ("rsync", "~1MB"),
    ],
    "yum": [
        ("man-db", "~12MB"), ("vim", "~8MB"), ("vim-minimal", "~8MB"),
        ("nano", "~2MB"), ("less", "~1MB"), ("wget", "~1MB"),
        ("telnet", "~1MB"), ("net-tools", "~1MB"), ("strace", "~1MB"),
        ("lsof", "~1MB"), ("htop", "~1MB"), ("sysstat", "~1MB"),
        ("rsync", "~1MB"), ("screen", "~1MB"), ("tmux", "~3MB"),
        ("openssh-clients", "~2MB"),
    ],
}

COMPILE_INDICATORS = [
    "make", "cmake", "cargo build", "go build", "go install",
    "gcc", "g++", "cc", "c++", "protoc", "mix compile",
    "mvn package", "gradle", "npm run build", "yarn build",
    "python setup.py", "pip install --no-binary",
]

LAYER_COMBINE_PATTERNS = [
    (r"apt-get\s+install", r"apt-get\s+clean|rm\s+-rf\s+/var/lib/apt/lists"),
    (r"yum\s+install", r"yum\s+clean\s+all|rm\s+-rf\s+/var/cache/yum"),
    (r"apk\s+add", r"rm\s+-rf\s+/var/cache/apk"),
]


@dataclass
class Layer:
    index: int
    instruction: str
    packages: list = field(default_factory=list)
    pkg_manager: str = ""
    raw: str = ""
    is_compile: bool = False


@dataclass
class AnalysisResult:
    base_image: str
    base_image_est_size: int
    layers: list = field(default_factory=list)
    build_packages: dict = field(default_factory=dict)
    unnecessary_packages: list = field(default_factory=list)
    layer_optimizations: list = field(default_factory=list)
    multi_stage_suggestions: list = field(default_factory=list)
    missing_cache_clear: list = field(default_factory=list)
    estimated_savings: int = 0


def parse_dockerfile(path: str) -> tuple[list[str], dict]:
    """Parse a Dockerfile into instructions."""
    if not os.path.isfile(path):
        return [], {}

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    instructions = []
    metadata = {"from_instructions": [], "run_count": 0, "copy_count": 0, "add_count": 0}

    current_line = ""
    for line in content.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            current_line += stripped[:-1] + " "
            continue
        current_line += stripped
        instructions.append(current_line.strip())
        current_line = ""
    if current_line.strip():
        instructions.append(current_line.strip())

    parsed = []
    for instr in instructions:
        if not instr or instr.startswith("#"):
            continue
        upper = instr.upper().strip()
        if upper.startswith("FROM "):
            parts = instr.split(None, 1)
            img = parts[1].split(" AS ")[0].split(" as ")[0].strip() if len(parts) > 1 else ""
            metadata["from_instructions"].append(img)
        elif upper.startswith("RUN "):
            metadata["run_count"] += 1
        elif upper.startswith("COPY "):
            metadata["copy_count"] += 1
        elif upper.startswith("ADD "):
            metadata["add_count"] += 1
        parsed.append(instr)

    return parsed, metadata


def detect_pkg_manager(cmd: str) -> str:
    if "apt-get" in cmd or "apt " in cmd:
        return "apt"
    if "apk " in cmd:
        return "apk"
    if "yum " in cmd:
        return "yum"
    if "dnf " in cmd:
        return "yum"
    if "pip install" in cmd:
        return "pip"
    if "npm install" in cmd or "npm ci" in cmd:
        return "npm"
    if "cargo install" in cmd or "cargo build" in cmd:
        return "cargo"
    if "go install" in cmd or "go build" in cmd:
        return "go"
    return ""


def extract_packages(cmd: str, pkg_manager: str) -> list[str]:
    if pkg_manager == "apt":
        match = re.search(r"apt-get\s+install\s+(?:-[yq]+\s+)*(.+?)(?:\s*\||\s*$)", cmd)
        if match:
            pkgs = match.group(1).strip()
            pkgs = re.sub(r"\s*--\S+", "", pkgs)
            return [p.strip() for p in pkgs.split() if p.strip() and not p.startswith("-")]
    elif pkg_manager == "apk":
        match = re.search(r"apk\s+add\s+(?:--no-cache\s+)?(.+?)(?:\s*\||\s*$)", cmd)
        if match:
            pkgs = match.group(1).strip()
            pkgs = re.sub(r"\s*--\S+", "", pkgs)
            return [p.strip() for p in pkgs.split() if p.strip() and not p.startswith("-")]
    elif pkg_manager == "yum":
        match = re.search(r"yum\s+install\s+(?:-[yq]+\s+)*(.+?)(?:\s*\||\s*$)", cmd)
        if match:
            pkgs = match.group(1).strip()
            pkgs = re.sub(r"\s*--\S+", "", pkgs)
            return [p.strip() for p in pkgs.split() if p.strip() and not p.startswith("-")]
    elif pkg_manager == "pip":
        match = re.search(r"pip(?:3)?\s+install\s+(.+?)(?:\s*\||\s*$)", cmd)
        if match:
            pkgs = match.group(1).strip()
            pkgs = re.sub(r"\s*--\S+", "", pkgs)
            return [p.strip() for p in re.split(r"[=<>!\s]+", pkgs) if p.strip() and not p.startswith("-")]
    elif pkg_manager == "npm":
        match = re.search(r"npm\s+(?:install|ci)\s+(.+?)(?:\s*\||\s*$)", cmd)
        if match:
            pkgs = match.group(1).strip()
            pkgs = re.sub(r"\s*--\S+", "", pkgs)
            return [p.strip() for p in pkgs.split() if p.strip() and not p.startswith("-")]
    elif pkg_manager == "cargo":
        match = re.search(r"cargo\s+install\s+(.+?)(?:\s*\||\s*$)", cmd)
        if match:
            pkgs = match.group(1).strip()
            pkgs = re.sub(r"\s*--\S+", "", pkgs)
            return [p.strip() for p in pkgs.split() if p.strip() and not p.startswith("-")]
    return []


def check_compile(cmd: str) -> bool:
    cmd_lower = cmd.lower()
    return any(ind in cmd_lower for ind in COMPILE_INDICATORS)


def has_cache_clear(cmd: str) -> bool:
    return bool(re.search(r"rm\s+-rf\s+/var/lib/apt/lists", cmd))


def analyze(instructions: list[str], metadata: dict) -> AnalysisResult:
    base_image = metadata["from_instructions"][-1] if metadata["from_instructions"] else "unknown"
    est_size = BASE_IMAGE_SIZES.get(base_image, 500)

    result = AnalysisResult(
        base_image=base_image,
        base_image_est_size=est_size,
    )

    layers = []
    from_seen = set()
    layer_idx = 0

    for instr in instructions:
        upper = instr.upper().strip()
        if upper.startswith("FROM "):
            parts = instr.split(None, 1)
            img = parts[1].split(" AS ")[0].split(" as ")[0].strip() if len(parts) > 1 else ""
            from_seen.add(img)
            continue

        if not (upper.startswith("RUN ") or upper.startswith("COPY ") or upper.startswith("ADD ")):
            continue

        layer_idx += 1
        is_run = upper.startswith("RUN ")
        cmd = instr[4:].strip() if is_run else ""
        pkg_mgr = detect_pkg_manager(cmd) if is_run else ""
        packages = extract_packages(cmd, pkg_mgr) if pkg_mgr else []
        is_compile = check_compile(cmd) if is_run else False

        layer = Layer(
            index=layer_idx,
            instruction=instr,
            packages=packages,
            pkg_manager=pkg_mgr,
            raw=cmd,
            is_compile=is_compile,
        )
        layers.append(layer)

    result.layers = layers

    from_instructions = metadata["from_instructions"]
    final_from = from_instructions[-1] if from_instructions else ""
    build_froms = from_instructions[:-1] if len(from_instructions) > 1 else []

    all_build_pkgs = set()
    pkg_manager_layer = {}

    for layer in layers:
        if layer.packages and layer.pkg_manager in BUILD_PACKAGES:
            mgr_build = BUILD_PACKAGES[layer.pkg_manager]
            for pkg in layer.packages:
                if pkg in mgr_build or pkg in BUILD_PACKAGES.get("apt", []):
                    result.build_packages.setdefault(pkg, []).append(layer.index)
                    all_build_pkgs.add(pkg)
                    pkg_manager_layer[pkg] = layer.index

    pkg_mgr_for_final = detect_pkg_manager(final_from)
    if pkg_mgr_for_final:
        for pkg in list(all_build_pkgs):
            if pkg not in BUILD_PACKAGES.get(pkg_mgr_for_final, []):
                continue

    unnecessary = []
    for layer in layers:
        if layer.packages and layer.pkg_manager in UNNECESSARY_PACKAGES:
            mgr_unnecessary = UNNECESSARY_PACKAGES[layer.pkg_manager]
            for pkg in layer.packages:
                for unec_pkg, size_str in mgr_unnecessary:
                    if pkg == unec_pkg:
                        unnecessary.append((pkg, size_str, layer.index))
    result.unnecessary_packages = unnecessary

    for i in range(len(layers) - 1):
        curr = layers[i]
        nxt = layers[i + 1]
        if curr.raw and nxt.raw:
            for install_pat, clean_pat in LAYER_COMBINE_PATTERNS:
                if re.search(install_pat, curr.raw) and re.search(clean_pat, nxt.raw):
                    result.layer_optimizations.append({
                        "install_layer": curr.index,
                        "clean_layer": nxt.index,
                        "install": curr.raw[:60],
                        "clean": nxt.raw[:60],
                    })
                    break

    for layer in layers:
        if layer.raw and layer.pkg_manager in ("apt", "yum", "apk"):
            if not has_cache_clear(layer.raw):
                result.missing_cache_clear.append(layer.index)

    for layer in layers:
        if layer.is_compile:
            suggestions = []
            cmd_lower = layer.raw.lower()
            if "cargo build" in cmd_lower or "cargo install" in cmd_lower:
                suggestions.append("use builder stage with rust:slim, copy only binary to final")
            elif "go build" in cmd_lower or "go install" in cmd_lower:
                suggestions.append("use builder stage with golang:alpine, copy only binary to final")
            elif "make" in cmd_lower:
                suggestions.append("use builder stage with build-essential, copy only output to final")
            elif "cmake" in cmd_lower:
                suggestions.append("use builder stage with cmake + build-essential, copy only binary to final")
            elif "npm run build" in cmd_lower or "yarn build" in cmd_lower:
                suggestions.append("use builder stage with node:slim for build, copy dist/ to final node:slim-alpine")
            else:
                suggestions.append("consider multi-stage build to separate build and runtime dependencies")
            result.multi_stage_suggestions.append({
                "layer": layer.index,
                "command": layer.raw[:60],
                "suggestions": suggestions,
            })

    savings = 0
    for pkg in result.build_packages:
        for mgr_unnecessary in UNNECESSARY_PACKAGES.values():
            for unec_pkg, size_str in mgr_unnecessary:
                if pkg == unec_pkg:
                    try:
                        savings += int(re.sub(r"[^0-9]", "", size_str))
                    except ValueError:
                        pass
                    break

    for _, size_str, _ in result.unnecessary_packages:
        try:
            savings += int(re.sub(r"[^0-9]", "", size_str))
        except ValueError:
            pass

    if result.multi_stage_suggestions:
        savings += int(est_size * 0.15)

    if savings == 0 and (result.build_packages or result.multi_stage_suggestions):
        savings = int(est_size * 0.12)

    result.estimated_savings = savings
    return result


def format_text(result: AnalysisResult, verbose: bool = False) -> str:
    lines = []
    lines.append("\U0001f433 image-slim: Dockerfile")
    lines.append("\u2501" * 24)
    lines.append("")

    est_pct = round(result.base_image_est_size / 10) if result.base_image_est_size else 0
    lines.append(f"  \U0001f4ca Base image: {result.base_image} (est. {result.base_image_est_size}MB)")
    lines.append("")

    if result.build_packages:
        lines.append("  \U0001f534 BUILD-TIME PACKAGES (can be removed in final layer)")
        for pkg, layers in result.build_packages.items():
            layer_str = ", ".join(str(l) for l in layers)
            lines.append(f"     {pkg} \u2014 installed in layer {layer_str} but not in final FROM")
        lines.append("")

    if result.unnecessary_packages:
        lines.append("  \U0001f7e1 UNNECESSARY PACKAGES")
        for pkg, size, layer in result.unnecessary_packages:
            lines.append(f"     {pkg} ({size}) \u2014 rarely needed at runtime (layer {layer})")
        lines.append("")

    if result.layer_optimizations:
        lines.append("  \U0001f7e1 LAYER OPTIMIZATION")
        for opt in result.layer_optimizations:
            lines.append(
                f"     Layer {opt['install_layer']}: apt-get install + layer {opt['clean_layer']}: "
                f"apt-get clean \u2014 combine into single RUN"
            )
        lines.append("")

    if result.missing_cache_clear:
        lines.append("  \U0001f7e1 MISSING CACHE CLEAR")
        lines.append(f"     Layers without 'rm -rf /var/lib/apt/lists/*': {result.missing_cache_clear}")
        lines.append("")

    if result.multi_stage_suggestions:
        lines.append("  \U0001f4a1 MULTI-STAGE SUGGESTION")
        for sug in result.multi_stage_suggestions:
            lines.append(f"     Detected: `{sug['command']}` in layer {sug['layer']}")
            for s in sug["suggestions"]:
                lines.append(f"     Suggested: {s}")
        lines.append("")

    if result.estimated_savings > 0:
        pct = round(result.estimated_savings / max(result.base_image_est_size, 1) * 100)
        lines.append(f"  \U0001f4ca Estimated savings: ~{result.estimated_savings}MB ({pct}% of base image)")
    else:
        lines.append("  \u2705 Dockerfile looks optimized! No significant savings found.")

    if verbose:
        lines.append("")
        lines.append("  \U0001f50d DETAILED LAYER BREAKDOWN")
        for layer in result.layers:
            pkg_info = f" [{', '.join(layer.packages)}]" if layer.packages else ""
            compile_tag = " (compile)" if layer.is_compile else ""
            lines.append(f"     Layer {layer.index}: {layer.instruction[:70]}{pkg_info}{compile_tag}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="image-slim: Analyze Dockerfiles and suggest ways to reduce image size"
    )
    parser.add_argument(
        "-f", "--dockerfile",
        default="Dockerfile",
        help="Path to Dockerfile (default: Dockerfile)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Auto-generate an optimized Dockerfile"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.dockerfile):
        print(f"\u274c Error: Dockerfile not found at '{args.dockerfile}'", file=sys.stderr)
        sys.exit(1)

    instructions, metadata = parse_dockerfile(args.dockerfile)
    if not instructions:
        print(f"\u274c Error: Could not parse '{args.dockerfile}'", file=sys.stderr)
        sys.exit(1)

    result = analyze(instructions, metadata)

    if args.json:
        output = {
            "base_image": result.base_image,
            "base_image_est_size_mb": result.base_image_est_size,
            "build_packages": result.build_packages,
            "unnecessary_packages": [
                {"package": p, "estimated_size": s, "layer": l} for p, s, l in result.unnecessary_packages
            ],
            "layer_optimizations": result.layer_optimizations,
            "multi_stage_suggestions": result.multi_stage_suggestions,
            "missing_cache_clear": result.missing_cache_clear,
            "estimated_savings_mb": result.estimated_savings,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_text(result, verbose=args.verbose))

    if args.suggest:
        suggest_path = args.dockerfile + ".optimized"
        suggestions = generate_suggestions(result)
        with open(suggest_path, "w", encoding="utf-8") as f:
            f.write(suggestions)
        print(f"\n  \U0001f4dd Optimized Dockerfile written to: {suggest_path}")


def generate_suggestions(result: AnalysisResult) -> str:
    lines = [
        "# Optimized Dockerfile generated by image-slim",
        "# Review and adjust before using in production",
        "",
    ]

    has_compile = bool(result.multi_stage_suggestions)

    if has_compile:
        lines.append("# Stage 1: Build stage")
        lines.append(f"FROM {result.base_image} AS builder")
        lines.append("RUN apt-get update && apt-get install -y --no-install-recommends \\")
        build_deps = sorted(result.build_packages.keys())
        for i, pkg in enumerate(build_deps):
            comma = "\\" if i < len(build_deps) - 1 else ""
            lines.append(f"    {pkg} {comma}")
        lines.append("")

        for layer in result.layers:
            if layer.raw and layer.pkg_manager in ("apt", "yum", "apk"):
                lines.append(layer.instruction)
        lines.append("")

        lines.append("# Stage 2: Runtime stage")
        lines.append(f"FROM {result.base_image}")
        lines.append("RUN apt-get update && apt-get install -y --no-install-recommends \\")
        runtime_deps = sorted(
            {pkg for layer in result.layers for pkg in layer.packages}
            - set(build_deps)
            - {p for p, _, _ in result.unnecessary_packages}
        )
        for i, pkg in enumerate(runtime_deps):
            comma = "\\" if i < len(runtime_deps) - 1 else ""
            lines.append(f"    {pkg} {comma}")
        lines.append("    && rm -rf /var/lib/apt/lists/*")
        lines.append("")
        lines.append("# Copy built artifacts from builder stage")
        lines.append("COPY --from=builder /path/to/binary /usr/local/bin/")
    else:
        lines.append(f"FROM {result.base_image}")
        unnecessary = {p for p, _, _ in result.unnecessary_packages}
        build_pkgs = set(result.build_packages.keys())

        all_pkgs = []
        for layer in result.layers:
            if layer.packages:
                all_pkgs.extend(layer.packages)

        if build_pkgs:
            lines.append("RUN apt-get update && apt-get install -y --no-install-recommends \\")
            deps = sorted(set(all_pkgs) - unnecessary)
            for i, pkg in enumerate(deps):
                comma = "\\" if i < len(deps) - 1 else ""
                lines.append(f"    {pkg} {comma}")
            lines.append("    && rm -rf /var/lib/apt/lists/*")
        else:
            lines.append("RUN apt-get update && apt-get install -y --no-install-recommends \\")
            deps = sorted(set(all_pkgs) - unnecessary)
            for i, pkg in enumerate(deps):
                comma = "\\" if i < len(deps) - 1 else ""
                lines.append(f"    {pkg} {comma}")
            lines.append("    && rm -rf /var/lib/apt/lists/*")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
