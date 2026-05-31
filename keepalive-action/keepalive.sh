#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$(dirname "$0")/../../.github"
date > "$(dirname "$0")/../../.github/keepalive"
