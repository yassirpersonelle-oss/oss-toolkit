# rojo-template-scaffold

Scaffold a Rojo project in one command.

Every Roblox project starts from scratch wasting 30--60 minutes on boilerplate: folder structures, `default.project.json`, init scripts, wally config, `.gitignore`. **rojo-template-scaffold** eliminates that — like `create-react-app` or `cookiecutter` but for Roblox development.

## Usage

```bash
python rojo-template-scaffold.py init --name MyGame --template rpg --wally
```

### Arguments

| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--name` | `-n` | Project name | `my-game` |
| `--template` | `-t` | Template to scaffold | `minimal` |
| `--path` | `-p` | Output directory | `.` |
| `--syntax` | | `luau` or `lua` | `luau` |
| `--wally` | | Generate `wally.toml` | off |
| `--luau-types` | | Include Luau type definitions | off |
| `--storybook` | | Include UI component storybook | off |
| `--force` | | Overwrite existing directory | off |
| `--list-templates` | | Show available templates | — |

### Examples

```bash
# Minimal scaffold
python rojo-template-scaffold.py init

# RPG with all the bells and whistles
python rojo-template-scaffold.py init -n EpicQuest -t rpg --wally --luau-types

# Obby game in a specific directory
python rojo-template-scaffold.py init -n ParkourWorld -t obby -p ~/Projects

# Framework/lib with wally
python rojo-template-scaffold.py init -n MyLib -t framework --wally

# Overwrite an existing scaffold
python rojo-template-scaffold.py init -n MyGame -t tycoon --force
```

## Templates

| Template | Description |
|----------|-------------|
| **minimal** | Bare minimum: Server/Client/Shared. Start from scratch with proper structure. |
| **obby** | Obby/parkour game with checkpoint system, stage loader, camera controller, and player data. Includes `lib/` and `assets/`. |
| **rpg** | Role-playing game with combat, quests, inventory, NPC directories, input handler, item/enum definitions. Wally config with Promise, Signal, and `t` included. |
| **simulator** | Clicker/simulator game with upgrade system, rebirth manager, click handler, and shop UI. |
| **tycoon** | Tycoon game with purchase grid, income system, tycoon manager, and purchase UI. |
| **pvp** | PvP arena with round system, loadout manager, matchmaker, HUD, and weapon definitions. |
| **framework** | Reusable module/library structure with `lib/`, `Components/`, and `State/` directories. Ideal for building packages. |

## Generated Structure

Every project includes:
- **`default.project.json`** — Rojo project config with correct Roblox service class names (`ServerScriptService`, `ReplicatedStorage`, `StarterPlayer`, `StarterGui`, `SoundService`, `Workspace`, `Players`)
- **`src/Server/ServerScriptService/`** — Server-side scripts
- **`src/Client/StarterPlayer/StarterPlayerScripts/`** — Client-side scripts
- **`src/Shared/`** — Modules shared between server and client
- **`.gitignore`** — Pre-configured for Roblox projects
- **`README.md`** — Template-specific docs with build commands and folder walkthrough

Template-specific additions:
- **`wally.toml`** (RPG always, others with `--wally`) — Dependencies like Promise, Signal, `t`
- **`lib/`** (Obby, Framework) — Rojo-managed external dependency directory
- **`assets/Sounds/`**, **`assets/Images/`** (Obby, Simulator, PvP) — Asset directories
- **`src/Shared/Components/`**, **`src/Shared/State/`** (Framework) — Roact/Rodux structure
- **`LuaUTypes.luau`** (`--luau-types`) — Roblox Luau type stubs
- **`Storybook/`** (`--storybook`) — UI component storybook launcher

## After Scaffolding

```bash
cd my-game
rojo serve       # Start live-sync server
rojo build       # Build .rbxl/.rbxmx
```

## Requirements

- Python 3.6+ (stdlib only — no pip install needed)
- [Rojo](https://rojo.space/) for syncing into Roblox Studio
- [Wally](https://wally.run/) if using `--wally` templates (for dependency management)
