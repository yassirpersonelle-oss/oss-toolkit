# plugin-hot-reload

**Stop closing and reopening Studio to test your plugin.**

---

## The Problem

Roblox Studio plugin development is painful. Every time you change a line of code:

1. Save the file
2. Close Studio (or disable/re-enable the plugin)
3. Re-open Studio (or have to hunt through plugin management UI)
4. Wait for everything to load
5. Finally test your change

This breaks flow completely. A 5-second code change turns into a 30–60 second cycle. Over a session, hours are lost to Studio restarts.

## The Solution

`plugin-hot-reload` watches your plugin source files. When any file changes on disk, it signals a lightweight Luau wrapper running inside Studio to re-require your modules — instantly, without restarting.

```
Save file  →  Watcher detects change  →  Studio reloads code  →  See result immediately
```

## How It Works

### 1. Python Watcher (this CLI)

- Polls your plugin source directories every N seconds
- Detects new, modified, and deleted files by comparing mtimes
- Touches a signal file on any change

### 2. Generated Luau Wrapper

- Installed as your plugin in Studio (instead of your raw source)
- Shows a toolbar button for manual reload
- Watches the signal file for changes (via `GetAttribute("Changed")`)
- Calls `reloadAll()` which clears the module cache and re-requires your entry point
- Runs a `task.spawn` loop checking every 0.5s

### 3. Signal File

A small `.rbxm` file in a folder next to your generated wrapper. The Python watcher touches it on file changes, and the Luau wrapper polls `:GetAttribute("Changed")` to know when to reload.

## Setup Guide

### Step 1: Generate the wrapper

```bash
python plugin-hot-reload.py \
  --watch path/to/your/plugin/src \
  --package-name "MyPlugin" \
  --output path/to/your/plugin
```

This creates:
- `MyPlugin-reload.luau` — install this as your plugin in Studio
- `MyPlugin-reload-signal/__reload_signal.rbxm` — signal file for change detection

### Step 2: Install in Studio

1. In Roblox Studio, go to **Plugins Folder** (right-click the Plugins tab)
2. Copy `MyPlugin-reload.luau` and the `MyPlugin-reload-signal/` folder into the plugins directory
3. Restart Studio (one last time!)

### Step 3: Start the watcher

```bash
python plugin-hot-reload.py \
  --watch path/to/your/plugin/src \
  --package-name "MyPlugin" \
  --output %LOCALAPPDATA%\Roblox\Plugins\MyPlugin
```

### Step 4: Code freely

Edit your source files. Save. See the change in Studio immediately.

## Usage

```
usage: plugin-hot-reload [-h] -w WATCH [WATCH ...] [-o OUTPUT]
                         [-i INTERVAL] [-n PACKAGE_NAME] [--generate-only]

Auto-reload Roblox Studio plugin code when files change on disk.

required arguments:
  -w, --watch WATCH [WATCH ...]
                        Directory(s) to watch (comma-separated or multiple args)

optional arguments:
  -o, --output OUTPUT   Output directory for generated wrapper (default: current dir)
  -i, --interval INTERVAL
                        Poll interval in seconds (default: 2)
  -n, --package-name PACKAGE_NAME
                        Plugin name for generated script (default: basename of first watch dir)
  --generate-only       Only generate the wrapper script without watching
```

### Examples

Watch a single source directory:
```bash
python plugin-hot-reload.py -w plugins/my-plugin/src
```

Watch multiple directories (src + libs + types):
```bash
python plugin-hot-reload.py -w plugins/my-plugin/src plugins/my-plugin/lib plugins/my-plugin/types
```

Only generate the wrapper (no watching):
```bash
python plugin-hot-reload.py -w plugins/my-plugin/src --generate-only
```

Custom plugin name and output location:
```bash
python plugin-hot-reload.py -w src/ -n "UIDragControls" -o ~/Roblox/Plugins/
```

## Requirements

- Python 3.6+
- Roblox Studio
- No dependencies outside the Python standard library

## Limitations

- **Rojo not required** — this uses direct file polling, not Rojo. The wrapper only needs to reach the signal file.
- Module state is fully reset on reload (`modules[path] = nil`). Any global state stored outside the module table will persist between reloads — use `Reloader.modules` if you need per-reload cleanup.
- Changes to the wrapper script itself require a Studio restart.
- Entry point is auto-detected as `init.luau`, `plugin.luau`, or `main.luau` (first found in watch dirs).
