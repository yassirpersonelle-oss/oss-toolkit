# remote-event-logger

**Audit your game's attack surface in one command.**

A Python CLI that scans a Roblox/Luau codebase for every `RemoteEvent`, `RemoteFunction`, and `UnreliableRemoteEvent` — then generates a security report ranking each one by exploit risk.

---

## Why RemoteEvents are the #1 exploit vector in Roblox

In Roblox's client-server model, `RemoteEvent:FireServer()` lets a client send arbitrary data to the server. Every single one of these calls is an **entry point an attacker can abuse**:

- **SaveData events** — a cheater fires with crafted arguments to overwrite player data
- **PurchaseItem events** — an exploiter fires with a fake item ID to get items for free
- **GiveCurrency events** — an attacker fires repeatedly to duplicate currency
- **KickPlayer events** — a malicious client kicks other players from the server

If the server handler doesn't validate inputs, the client controls what happens. **This is the root cause of most Roblox exploits.**

`remote-event-logger` finds every `FireServer` call and every `OnServerEvent` handler in your codebase, checks whether input validation exists, and gives each one a severity rating — so you know exactly where to focus your hardening efforts.

---

## Installation

Requires Python 3.7+. No dependencies beyond the standard library.

```bash
# Download the script
curl -O https://raw.githubusercontent.com/.../remote-event-logger.py
chmod +x remote-event-logger.py
```

Or clone the repository:

```bash
git clone https://github.com/.../remote-event-logger.git
```

---

## Usage

```bash
# Basic scan
python remote-event-logger.py --path ./src

# JSON output for CI / machine processing
python remote-event-logger.py --path ./src --json -o report.json

# Plain-text summary
python remote-event-logger.py --path ./src --format text

# Verbose mode — see every file being scanned
python remote-event-logger.py --path ./src --verbose
```

### Options

| Flag | Description |
|------|-------------|
| `--path` | **Required.** Directory to scan recursively for `.lua` / `.luau` files |
| `--output`, `-o` | Write report to a file (default: stdout) |
| `--json` | Shortcut for `--format json` |
| `--format` | Output format: `markdown` (default), `json`, or `text` |
| `--verbose` | Print scan progress to stderr |

---

## Understanding severity levels

Each remote event receives one of four ratings:

| Level | Meaning |
|-------|---------|
| **HIGH RISK** | Client can fire with arbitrary data — no input validation found in the server handler. This is a confirmed exploit vector. |
| **MEDIUM** | Some validation detected (e.g., nil check, assert), but no comprehensive type or range checks. Likely exploitable with crafted input. |
| **LOW** | Full validation detected — type checks (`typeof`, `:IsA`), guard clauses, and error handling. Unlikely to be exploitable. |
| **INFO** | No client-to-server path detected in the scanned files. Event may be unused or fired exclusively server-to-client. |

### How validation is detected

The scanner looks inside `OnServerEvent` and `OnServerInvoke` handler functions for:

- `typeof(param) == "string"` — explicit type checking
- `assert(param, msg)` — assertion guards
- `if not param then return end` — nil-guard pattern
- `pcall(...)` — protected call wrappers
- `object:IsA("ClassName")` — Roblox type checking
- `type(param) ~= "table"` — Lua type comparison

A handler needs **both** type checks **and** guard clauses to qualify as LOW risk.

---

## How to fix high-risk remotes

### Before (HIGH RISK)

```lua
-- Server handler with zero validation
saveData.OnServerEvent:Connect(function(player, data)
    dataStore:SetAsync(player.UserId, data)  -- attacker controls 'data'
end)
```

### After (LOW RISK)

```lua
saveData.OnServerEvent:Connect(function(player, data)
    -- 1. Nil guard
    if not data then return end

    -- 2. Type check
    if typeof(data) ~= "table" then return end

    -- 3. Field validation
    if typeof(data.coins) ~= "number" then return end
    if data.coins < 0 or data.coins > 1000000 then return end

    -- 4. Whois/authorization check
    if not canPlayerSave(player) then return end

    -- 5. Protected call
    local ok, err = pcall(function()
        dataStore:SetAsync(player.UserId, data)
    end)
    if not ok then
        warn("SaveData failed:", err)
    end
end)
```

### Validation checklist

- [ ] Nil/type guard on the main argument
- [ ] Type check on every expected field (`typeof`, `:IsA`)
- [ ] Range/bounds checks on numeric values
- [ ] Authorization check (does this player have permission?)
- [ ] Protected call wrapping the database/state mutation
- [ ] Rate limiting for spam prevention

---

## CI Integration

### GitHub Actions

```yaml
name: Security Audit
on: [push, pull_request]

jobs:
  remote-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run remote-event-logger
        run: |
          python remote-event-logger.py --path ./src --json -o audit.json
      - name: Fail on high-risk findings
        run: |
          HIGH=$(python -c "import json; d=json.load(open('audit.json')); print(d['summary']['high_risk'])")
          if [ "$HIGH" -gt 0 ]; then
            echo "::error::$HIGH high-risk remote event(s) found!"
            exit 1
          fi
```

### Pre-commit hook

```bash
#!/bin/bash
# .git/hooks/pre-commit
python remote-event-logger.py --path ./src --format text
HIGH=$(python -c "import json; d=json.load(open('audit.json')); print(d['summary']['high_risk'])")
if [ "$HIGH" -gt 0 ]; then
    echo "Commit blocked: $HIGH high-risk remote event(s) without validation."
    exit 1
fi
```

---

## Sample output

```
# Remote Event Attack Surface

| Category                | Count |
|-------------------------|-------|
| RemoteEvents            | 8     |
| RemoteFunctions         | 3     |
| UnreliableRemoteEvents  | 1     |
| **Total**               | **12** |

## HIGH RISK (4)

**SaveData** (RemoteEvent) -- `ServerScriptService`
  - File: `src/server/Data.lua:23`
  - **FireServer**: 2 call(s)
    - Line 156: `:player, saveData`
  - Server handler(s): onSaveData
  - Validation checks: **NONE**
  - Potential: client supplies arbitrary data -- exploit vector

**PurchaseItem** (RemoteEvent) -- `ReplicatedStorage/Remotes`
  - File: `src/shared/Remotes.lua:45`
  - **FireServer**: 3 call(s)
    - Line 89: `:itemId`
  - Server handler(s): onPurchaseItem
  - Validation checks: **NONE**
  - Potential: client supplies arbitrary data -- exploit vector

## MEDIUM (5)

**RequestGameData** (RemoteFunction) -- `ReplicatedStorage`
  - File: `src/server/Handlers.lua:67`
  - **InvokeServer**: 1 call(s)
    - Line 203: `:requestType`
  - Server handler(s): onRequestData
  - Validation checks: assert(), nil-guard
  - Note: basic validation present, consider strengthening

## LOW (3)

**PlaySound** (RemoteEvent) -- `ReplicatedStorage`
  - File: `src/server/Audio.lua:89`
  - **FireServer**: 1 call(s)
    - Line 45: `:soundId, volume`
  - Server handler(s): onPlaySound
  - Validation checks: typeof(), nil-guard, :IsA()
  - Validation level: full

---

## SUMMARY: 4 high-risk entry point(s) detected
```

---

## Limitations

- **Regex-based**: The scanner uses regular expressions, not a full Lua parser. Complex or obfuscated patterns may be missed.
- **Single-file scope**: Validation analysis is per-file. If a handler is defined in a different file than the `.Connect()` call, it may not be linked.
- **No data-flow analysis**: The scanner detects validation patterns but doesn't trace data flow through intermediate functions.
- **Comment stripping is basic**: Nested `--[=[ ]=]` block comments may not be fully stripped.

This tool is designed for **quick, high-signal auditing** — not formal verification. Use it as a first pass before manual code review.

---

## License

MIT
