# DataStore Debugger

Debug Roblox DataStore logic locally without publishing to Live Servers.

## Why

Debugging DataStore code on Roblox is painful:

- **Requires published servers** — every change needs a new publish cycle
- **Hard to reproduce edge cases** — throttling, concurrency conflicts, data loss
- **No visibility** — you can't inspect what's actually stored or step through transactions
- **No error injection** — testing error-handling code means waiting for real failures

DataStore Debugger simulates the full `DataStoreService` API locally with transaction history, conflict replay, and chaos testing so you can iterate fast.

## Usage

### CLI mode — simulate a Luau script

```
python datastore-debugger.py --import-script test_datastore.luau
```

The tool parses your Luau script, identifies DataStore calls (`SetAsync`, `GetAsync`, `UpdateAsync`, etc.), and executes them against a local JSON-backed store. You see every operation, its result, and any conflicts or errors.

### CLI mode — with chaos testing

```
python datastore-debugger.py --chaos --import-script my_script.luau --verbose
```

`--chaos` randomly fails ~30% of operations to let you test retry/error-handling logic without waiting for real outages.

### Web UI mode

```
python datastore-debugger.py --web
```

Opens `http://localhost:8765` with an interactive panel for:

- Live transaction log (auto-refreshing)
- Data browser to view all keys and values
- Operation panel — SetAsync, GetAsync, UpdateAsync, IncrementAsync, RemoveAsync
- Conflict simulator — fires concurrent UpdateAsync calls
- Export / Import data as JSON
- Create named DataStores and OrderedDataStores

Use `--port` to change the port:

```
python datastore-debugger.py --web --port 8080
```

### Dump all stored data

```
python datastore-debugger.py --dump
```

### Custom store file

```
python datastore-debugger.py --store mydata.json --import-script script.luau
```

## Supported APIs

| API | Simulated |
|---|---|
| `DataStoreService:GetDataStore(name, scope, options)` | yes |
| `DataStoreService:GetOrderedDataStore(name, scope)` | yes |
| `DataStore:SetAsync(key, value, userIds, options)` | yes |
| `DataStore:GetAsync(key)` | yes |
| `DataStore:UpdateAsync(key, transformFn)` | yes — with conflict detection |
| `DataStore:IncrementAsync(key, delta, userIds, options)` | yes |
| `DataStore:RemoveAsync(key)` | yes |
| `DataStore:ListKeysAsync(prefix, pageSize, cursor)` | yes — paginated |
| `DataStore:ListVersionsAsync(key, sortDirection, minDate, maxDate, pageSize)` | yes |
| `DataStore:GetVersionAsync(key, version)` | yes |
| `OrderedDataStore:GetSortedAsync(ascending, pageSize, minValue, maxValue)` | yes |

## Special features

- **Version history** — last 10 versions per key preserved (configurable)
- **Conflict detection** — `UpdateAsync` simulates concurrent writes with retry logic
- **Transaction log** — timestamped record of every operation
- **Schema validation** — validates value structure against expected schema
- **Rate limiting** — simulates DataStore throttle and quota limits
- **Error injection** — `--chaos` randomly fails operations to test error handling
- **Data persistence** — all data stored in a JSON file, survives restarts

## Requirements

- Python 3.7+ (stdlib only — no pip install needed)

## Examples

### Basic script simulation

Create `test_datastore.luau`:

```lua
local DataStoreService = game:GetService("DataStoreService")
local ds = DataStoreService:GetDataStore("PlayerData")

ds:SetAsync("player_123", {coins = 100, level = 5})
ds:SetAsync("player_456", {coins = 50, level = 3})

local data = ds:GetAsync("player_123")
ds:UpdateAsync("player_123", function(old)
    old.coins = old.coins + 10
    return old
end)
ds:IncrementAsync("player_123_coins", 100)

local keys = ds:ListKeysAsync("player_")
```

Run it:

```
python datastore-debugger.py -i test_datastore.luau
```

Output:

```
💾 DataStore Debugger — local mode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  📂 Store: datastore.json (3 keys, 5 versions)

  Running import script: test_datastore.luau

  [14:23:01] 📝 SetAsync             player_123           → {"coins":100,"level":5} ✓
  [14:23:01] 📝 SetAsync             player_456           → {"coins":50,"level":3} ✓
  [14:23:02] 🔍 GetAsync             player_123           → {"coins":100,"level":5} ✓
  [14:23:02] 🔄 UpdateAsync          player_123           → {"coins":110,"level":5} ✓
  [14:23:02] ➕ IncrementAsync       player_123_coins     → 100 ✓
  [14:23:03] 📋 ListKeysAsync        player_              ✓

  📊 Summary: 6 operations, 6 succeeded, 0 conflicts, 0 errors
```

### Testing error handling with chaos

```
python datastore-debugger.py --chaos -i my_script.luau -v
```

With `--chaos`, ~30% of operations will randomly throw errors like:
- Simulated network error
- Simulated timeout
- Simulated internal server error
- Simulated quota exceeded

This lets you verify your retry and error-handling code without deploying to Roblox.
