#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

TEMPLATE_INFO = {
    "obby":       "Obby/parkour game with checkpoint system",
    "rpg":        "RPG with combat, quests, inventory",
    "simulator":  "Clicker/simulator with upgrade system",
    "tycoon":     "Tycoon with purchase grid + income",
    "pvp":        "PvP arena with round system + loadouts",
    "framework":  "Reusable module/library structure",
    "minimal":    "Bare minimum: Server/Client/Shared",
}

BASE_DIRS = [
    "src/Server/ServerScriptService",
    "src/Client/StarterPlayer/StarterPlayerScripts",
    "src/Shared",
]

TEMPLATE_DIRS = {
    "minimal": [],
    "obby": [
        "src/Server/ServerScriptService/Stages",
        "lib",
        "assets/Sounds",
        "assets/Images",
    ],
    "rpg": [
        "src/Server/ServerScriptService/Combat",
        "src/Server/ServerScriptService/Quests",
        "src/Server/ServerScriptService/Inventory",
        "src/Server/ServerScriptService/NPC",
        "src/Client/StarterPlayer/StarterPlayerScripts/UI",
        "src/Client/StarterPlayer/StarterPlayerScripts/Camera",
    ],
    "simulator": [
        "assets/Sounds",
    ],
    "tycoon": [],
    "pvp": [
        "assets/Sounds",
    ],
    "framework": [
        "lib",
        "src/Shared/Components",
        "src/Shared/State",
    ],
}

TEMPLATE_FILES = {
    "minimal": {
        "src/Server/ServerScriptService/init.server":     "init_server",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client": "init_client",
        "src/Shared/init":                                 "init_shared",
    },
    "obby": {
        "src/Server/ServerScriptService/init.server":               "init_server",
        "src/Server/ServerScriptService/Stages/CheckpointManager":  "checkpoint_manager",
        "src/Server/ServerScriptService/Stages/StageLoader":        "stage_loader",
        "src/Server/ServerScriptService/PlayerData":                "player_data",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client":"init_client",
        "src/Client/StarterPlayer/StarterPlayerScripts/GameUI":     "game_ui",
        "src/Client/StarterPlayer/StarterPlayerScripts/CameraController": "camera",
        "src/Shared/Types":                                          "types",
        "src/Shared/Config":                                         "config",
    },
    "rpg": {
        "src/Server/ServerScriptService/init.server":               "init_server",
        "src/Server/ServerScriptService/PlayerData":                "player_data",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client":"init_client",
        "src/Client/StarterPlayer/StarterPlayerScripts/InputHandler":"input",
        "src/Shared/Types":                                          "types",
        "src/Shared/Config":                                         "config",
        "src/Shared/Items":                                          "items",
        "src/Shared/Enums":                                          "enums",
    },
    "simulator": {
        "src/Server/ServerScriptService/init.server":               "init_server",
        "src/Server/ServerScriptService/UpgradeSystem":             "upgrade",
        "src/Server/ServerScriptService/RebirthManager":           "rebirth",
        "src/Server/ServerScriptService/PlayerData":                "player_data",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client":"init_client",
        "src/Client/StarterPlayer/StarterPlayerScripts/ClickHandler":"click",
        "src/Client/StarterPlayer/StarterPlayerScripts/ShopUI":     "shop_ui",
        "src/Shared/Types":                                          "types",
        "src/Shared/Config":                                         "config",
    },
    "tycoon": {
        "src/Server/ServerScriptService/init.server":               "init_server",
        "src/Server/ServerScriptService/TycoonManager":             "tycoon_mgr",
        "src/Server/ServerScriptService/PurchaseGrid":              "purchase",
        "src/Server/ServerScriptService/IncomeSystem":              "income",
        "src/Server/ServerScriptService/PlayerData":                "player_data",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client":"init_client",
        "src/Client/StarterPlayer/StarterPlayerScripts/PurchaseUI": "purchase",
        "src/Client/StarterPlayer/StarterPlayerScripts/TycoonCamera":"camera",
        "src/Shared/Types":                                          "types",
        "src/Shared/Config":                                         "config",
    },
    "pvp": {
        "src/Server/ServerScriptService/init.server":               "init_server",
        "src/Server/ServerScriptService/RoundSystem":               "round",
        "src/Server/ServerScriptService/LoadoutManager":            "loadout",
        "src/Server/ServerScriptService/PlayerData":                "player_data",
        "src/Server/ServerScriptService/Matchmaker":                "matchmaker",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client":"init_client",
        "src/Client/StarterPlayer/StarterPlayerScripts/HUD":        "hud",
        "src/Client/StarterPlayer/StarterPlayerScripts/LoadoutUI":  "loadout",
        "src/Shared/Types":                                          "types",
        "src/Shared/Config":                                         "config",
        "src/Shared/Weapons":                                        "weapons",
    },
    "framework": {
        "src/Server/ServerScriptService/init.server":               "init_server",
        "src/Client/StarterPlayer/StarterPlayerScripts/init.client":"init_client",
        "src/Shared/init":                                          "init_shared",
    },
}

_TEMPLATES_CACHE = {}

def _render(key, name):
    if key not in _TEMPLATES_CACHE:
        _TEMPLATES_CACHE[key] = FILE_CONTENT_TEMPLATES.get(key, "-- TODO: Implement\n")
    return _TEMPLATES_CACHE[key].replace("__PROJECT_NAME__", name)

FILE_CONTENT_TEMPLATES = {}

def _reg(key, s):
    FILE_CONTENT_TEMPLATES[key] = s

_reg("init_server", """-- __PROJECT_NAME__ Server Initialization
-- Runs when the server starts

local Players = game:GetService("Players")

Players.PlayerAdded:Connect(function(player)
    print(string.format("[Server] Player %s joined", player.Name))
end)

print("[Server] __PROJECT_NAME__ server initialized!")
""")

_reg("init_client", """-- __PROJECT_NAME__ Client Initialization
-- Runs when the player loads in

local Players = game:GetService("Players")
local player = Players.LocalPlayer

if player then
    print(string.format("[Client] __PROJECT_NAME__ client initialized for %s", player.Name))
else
    print("[Client] __PROJECT_NAME__ client initialized")
end
""")

_reg("init_shared", """-- __PROJECT_NAME__ Shared Module
-- Code shared between server and client

local module = {}

function module.GetVersion()
    return "0.1.0"
end

return module
""")

_reg("types", """-- __PROJECT_NAME__ Type Definitions

export type PlayerData = {
    coins: number,
    level: number,
}
""")

_reg("config", """-- __PROJECT_NAME__ Game Configuration

local Config = {
    gameName = "__PROJECT_NAME__",
    maxPlayers = 20,
    version = "0.1.0",
}

return Config
""")

_reg("player_data", """-- Player Data Service

local PlayerData = {}

function PlayerData.Load(player)
end

function PlayerData.Save(player)
end

return PlayerData
""")

_reg("checkpoint_manager", """-- Checkpoint Manager

local CheckpointManager = {}

function CheckpointManager.RegisterCheckpoint(stage, checkpoint)
end

function CheckpointManager.GetPlayerCheckpoint(player)
end

return CheckpointManager
""")

_reg("stage_loader", """-- Stage Loader

local StageLoader = {}

function StageLoader.LoadStage(stageId)
end

function StageLoader.UnloadCurrentStage()
end

return StageLoader
""")

_reg("game_ui", """-- Game UI Controller

local GameUI = {}

function GameUI.ShowStageComplete(stageNumber)
end

function GameUI.UpdateTimer(seconds)
end

return GameUI
""")

_reg("camera", """-- Camera Controller

local CameraController = {}

function CameraController.SetupCamera()
end

function CameraController.ShakeCamera(intensity, duration)
end

return CameraController
""")

_reg("upgrade", """-- Upgrade System

local UpgradeSystem = {}

function UpgradeSystem.PurchaseUpgrade(player, upgradeId)
end

function UpgradeSystem.GetUpgradeLevel(player, upgradeId)
end

return UpgradeSystem
""")

_reg("rebirth", """-- Rebirth Manager

local RebirthManager = {}

function RebirthManager.Rebirth(player)
end

function RebirthManager.GetRebirthCount(player)
end

return RebirthManager
""")

_reg("click", """-- Click Handler

local ClickHandler = {}

function ClickHandler.OnClick(player, clickMultiplier)
end

return ClickHandler
""")

_reg("shop_ui", """-- Shop UI

local ShopUI = {}

function ShopUI.ShowShop(player)
end

function ShopUI.HideShop(player)
end

return ShopUI
""")

_reg("tycoon_mgr", """-- Tycoon Manager

local TycoonManager = {}

function TycoonManager.CreateTycoon(player)
end

function TycoonManager.RemoveTycoon(player)
end

return TycoonManager
""")

_reg("purchase", """-- Purchase System

local PurchaseSystem = {}

function PurchaseSystem.CanAfford(player, itemId)
    return false
end

function PurchaseSystem.Purchase(player, itemId)
end

return PurchaseSystem
""")

_reg("income", """-- Income System

local IncomeSystem = {}

function IncomeSystem.StartIncome(player, tycoon)
end

function IncomeSystem.StopIncome(player)
end

return IncomeSystem
""")

_reg("round", """-- Round System

local RoundSystem = {}

function RoundSystem.StartRound()
end

function RoundSystem.EndRound(winner)
end

return RoundSystem
""")

_reg("loadout", """-- Loadout System

local LoadoutSystem = {}

function LoadoutSystem.EquipLoadout(player, loadoutId)
end

function LoadoutSystem.GetPlayerLoadout(player)
end

return LoadoutSystem
""")

_reg("matchmaker", """-- Matchmaker

local Matchmaker = {}

function Matchmaker.FindMatch(player)
end

function Matchmaker.CancelSearch(player)
end

return Matchmaker
""")

_reg("hud", """-- HUD Controller

local HUD = {}

function HUD.ShowScore(score)
end

function HUD.ShowTimer(seconds)
end

return HUD
""")

_reg("input", """-- Input Handler

local InputHandler = {}

function InputHandler.OnAction(actionName, inputState)
end

function InputHandler.BindAction(actionName, callback)
end

return InputHandler
""")

_reg("items", """-- Item Definitions

local Items = {}

Items.List = {
    -- Define items here
}

return Items
""")

_reg("enums", """-- Game Enums

local Enums = {
    GameState = {
        LOBBY = "Lobby",
        PLAYING = "Playing",
        ENDED = "Ended",
    },
}

return Enums
""")

_reg("weapons", """-- Weapon Definitions

local Weapons = {}

Weapons.List = {
    -- Define weapons here
}

return Weapons
""")

LUAU_TYPES_CONTENT = """-- Luau Type Definitions for Roblox

export type Vector3 = {x: number, y: number, z: number}
export type CFrame = {
    Position: Vector3,
    X: Vector3,
    Y: Vector3,
    Z: Vector3,
}
"""

STORYBOOK_INIT_CONTENT = """-- UI Storybook Launcher
-- Showcase and test UI components in isolation

local Storybook = {}

function Storybook.Show(storyName)
end

return Storybook
"""

GITIGNORE_CONTENT = """# Roblox
*.rbxl
*.rbxlx
*.rbxmx

# Build output
build/
out/

# Dependencies
wally.lock
Packages/
node_modules/

# OS files
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
"""

WALLY_BASE_DEPS = [
    ("Promise", "evaera/promise@4.1.0"),
    ("Signal", "sleitnick/signal@2.1.0"),
]

WALLY_EXTRA_DEPS = {
    "rpg": [("t", "osyrisrblx/t@3.0.0")],
}

TEMPLATES_ALWAYS_WALLY = {"rpg"}


def build_project_tree(template, name):
    tree = {
        "name": name,
        "tree": {
            "$className": "DataModel",
            "ServerScriptService": {
                "$className": "ServerScriptService",
                "Server": {"$path": "src/Server/ServerScriptService"},
            },
            "ReplicatedStorage": {
                "$className": "ReplicatedStorage",
                "Shared": {"$path": "src/Shared"},
            },
            "StarterPlayer": {
                "$className": "StarterPlayer",
                "StarterPlayerScripts": {
                    "$className": "StarterPlayerScripts",
                    "Client": {"$path": "src/Client/StarterPlayer/StarterPlayerScripts"},
                },
            },
        },
    }

    t = tree["tree"]

    if template in ("obby", "simulator", "pvp"):
        t["SoundService"] = {
            "$className": "SoundService",
            "Sounds": {"$path": "assets/Sounds"},
        }

    if template == "obby":
        t["StarterGui"] = {
            "$className": "StarterGui",
            "Images": {"$path": "assets/Images"},
        }

    if template in ("obby", "framework"):
        t["ReplicatedStorage"]["Lib"] = {"$path": "lib"}

    if template in ("rpg", "simulator", "tycoon", "pvp"):
        t["StarterGui"] = {"$className": "StarterGui"}

    if template in ("obby", "tycoon", "simulator"):
        t["Workspace"] = {"$className": "Workspace"}

    if template == "framework":
        t["ReplicatedStorage"]["Components"] = {"$path": "src/Shared/Components"}
        t["ReplicatedStorage"]["State"] = {"$path": "src/Shared/State"}

    if template in ("rpg", "pvp"):
        t["Players"] = {
            "$className": "Players",
            "$properties": {"MaxPlayers": 20},
        }

    return tree


def generate_wally_toml(template, name, wally_flag):
    if not wally_flag and template not in TEMPLATES_ALWAYS_WALLY:
        return None

    deps = list(WALLY_BASE_DEPS)
    deps.extend(WALLY_EXTRA_DEPS.get(template, []))

    dep_lines = "\n".join('{} = "{}"'.format(alias, path) for alias, path in deps)

    return """[package]
name = "{}"
version = "0.1.0"
registry = "wally.run"
realm = "shared"

[dependencies]
{}
""".format(name, dep_lines)


_README_STRUCTURES = {
    "minimal": """{name}/
├── default.project.json
├── .gitignore
├── README.md
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       └── init.server.{ext}
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           └── init.client.{ext}
    └── Shared/
        └── init.{ext}""",
    "obby": """{name}/
├── default.project.json
├── .gitignore
├── README.md
├── lib/
├── assets/
│   ├── Sounds/
│   └── Images/
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       ├── init.server.{ext}
    │       ├── PlayerData.{ext}
    │       └── Stages/
    │           ├── CheckpointManager.{ext}
    │           └── StageLoader.{ext}
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           ├── init.client.{ext}
    │           ├── GameUI.{ext}
    │           └── CameraController.{ext}
    └── Shared/
        ├── Types.{ext}
        └── Config.{ext}""",
    "rpg": """{name}/
├── default.project.json
├── wally.toml
├── .gitignore
├── README.md
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       ├── init.server.{ext}
    │       ├── PlayerData.{ext}
    │       ├── Combat/
    │       ├── Quests/
    │       ├── Inventory/
    │       └── NPC/
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           ├── init.client.{ext}
    │           ├── InputHandler.{ext}
    │           ├── UI/
    │           └── Camera/
    └── Shared/
        ├── Types.{ext}
        ├── Config.{ext}
        ├── Items.{ext}
        └── Enums.{ext}""",
    "simulator": """{name}/
├── default.project.json
├── .gitignore
├── README.md
├── assets/
│   └── Sounds/
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       ├── init.server.{ext}
    │       ├── UpgradeSystem.{ext}
    │       ├── RebirthManager.{ext}
    │       └── PlayerData.{ext}
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           ├── init.client.{ext}
    │           ├── ClickHandler.{ext}
    │           └── ShopUI.{ext}
    └── Shared/
        ├── Types.{ext}
        └── Config.{ext}""",
    "tycoon": """{name}/
├── default.project.json
├── .gitignore
├── README.md
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       ├── init.server.{ext}
    │       ├── TycoonManager.{ext}
    │       ├── PurchaseGrid.{ext}
    │       ├── IncomeSystem.{ext}
    │       └── PlayerData.{ext}
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           ├── init.client.{ext}
    │           ├── PurchaseUI.{ext}
    │           └── TycoonCamera.{ext}
    └── Shared/
        ├── Types.{ext}
        └── Config.{ext}""",
    "pvp": """{name}/
├── default.project.json
├── .gitignore
├── README.md
├── assets/
│   └── Sounds/
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       ├── init.server.{ext}
    │       ├── RoundSystem.{ext}
    │       ├── LoadoutManager.{ext}
    │       ├── PlayerData.{ext}
    │       └── Matchmaker.{ext}
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           ├── init.client.{ext}
    │           ├── HUD.{ext}
    │           └── LoadoutUI.{ext}
    └── Shared/
        ├── Types.{ext}
        ├── Config.{ext}
        └── Weapons.{ext}""",
    "framework": """{name}/
├── default.project.json
├── .gitignore
├── README.md
├── lib/
└── src/
    ├── Server/
    │   └── ServerScriptService/
    │       └── init.server.{ext}
    ├── Client/
    │   └── StarterPlayer/
    │       └── StarterPlayerScripts/
    │           └── init.client.{ext}
    └── Shared/
        ├── init.{ext}
        ├── Components/
        └── State/""",
}


def generate_project_readme(template, name, ext):
    tdesc = TEMPLATE_INFO[template]
    structure = _README_STRUCTURES.get(template, "").format(name=name, ext=ext)

    wally_note = ""
    if template == "rpg":
        wally_note = """
## Wally Dependencies

Install dependencies:

```bash
wally install
```
"""

    return """# {name}

{tdesc}

## Getting Started

```bash
rojo serve
```

Build for release:

```bash
rojo build -o {name}.rbxl
```

## Project Structure

```
{structure}
```
{wally_note}
## Scripts

All scripts use {ext_upper} syntax.

### Server
`src/Server/ServerScriptService/` — Server-side scripts that run on the Roblox server.

### Client
`src/Client/StarterPlayer/StarterPlayerScripts/` — Client-side scripts that run on each player's machine.

### Shared
`src/Shared/` — Modules shared between server and client.

## Build & Deploy

This project uses [Rojo](https://rojo.space/) for syncing files into Roblox Studio.

1. Install Rojo: download from [GitHub](https://github.com/rojo-rbx/rojo/releases)
2. Run `rojo serve` to start a live-sync server
3. In Roblox Studio, use the Rojo plugin to connect
""".format(name=name, tdesc=tdesc, structure=structure, wally_note=wally_note, ext_upper=ext.upper())


def list_templates():
    print("Available Templates:")
    for name in ["obby", "rpg", "simulator", "tycoon", "pvp", "framework", "minimal"]:
        desc = TEMPLATE_INFO[name]
        print("  {:<10} {}".format(name, desc))


def _get_gitkeep_dirs(template):
    dirs = []
    if template in ("obby", "framework"):
        dirs.append("lib")
    if template == "rpg":
        dirs.extend([
            "src/Server/ServerScriptService/Combat",
            "src/Server/ServerScriptService/Quests",
            "src/Server/ServerScriptService/Inventory",
            "src/Server/ServerScriptService/NPC",
            "src/Client/StarterPlayer/StarterPlayerScripts/UI",
            "src/Client/StarterPlayer/StarterPlayerScripts/Camera",
        ])
    if template == "framework":
        dirs.extend([
            "src/Shared/Components",
            "src/Shared/State",
        ])
    if template in ("obby", "simulator", "pvp"):
        dirs.append("assets/Sounds")
    if template == "obby":
        dirs.append("assets/Images")
    return dirs


def scaffold(args):
    project_name = args.name
    template = args.template
    output_dir = Path(args.path).resolve() / project_name
    ext = args.syntax

    if output_dir.exists():
        if args.force:
            def _rm_error(func, path, excinfo):
                os.chmod(path, 0o777)
                func(path)
            shutil.rmtree(str(output_dir), onerror=_rm_error)
        else:
            print("Error: Directory '{}' already exists. Use --force to overwrite.".format(output_dir))
            sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    all_dirs = list(BASE_DIRS)
    all_dirs.extend(TEMPLATE_DIRS.get(template, []))

    if args.storybook:
        all_dirs.append("src/Client/StarterPlayer/StarterPlayerScripts/Storybook")

    for d in all_dirs:
        (output_dir / d).mkdir(parents=True, exist_ok=True)

    files = TEMPLATE_FILES.get(template, {})
    for filepath, content_key in files.items():
        full_path = output_dir / "{}.{}".format(filepath, ext)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        content = _render(content_key, project_name)
        full_path.write_text(content, encoding="utf-8")

    if args.luau_types:
        types_path = output_dir / "src" / "Shared" / "LuaUTypes.{}".format(ext)
        types_path.parent.mkdir(parents=True, exist_ok=True)
        types_path.write_text(LUAU_TYPES_CONTENT, encoding="utf-8")

    if args.storybook:
        sb_dir = output_dir / "src" / "Client" / "StarterPlayer" / "StarterPlayerScripts" / "Storybook"
        sb_dir.mkdir(parents=True, exist_ok=True)
        (sb_dir / "init.{}".format(ext)).write_text(STORYBOOK_INIT_CONTENT, encoding="utf-8")

    for gkd in _get_gitkeep_dirs(template):
        gk_path = output_dir / gkd / ".gitkeep"
        gk_path.parent.mkdir(parents=True, exist_ok=True)
        gk_path.write_text("", encoding="utf-8")

    project_json = build_project_tree(template, project_name)
    (output_dir / "default.project.json").write_text(
        json.dumps(project_json, indent=2) + "\n",
        encoding="utf-8",
    )

    (output_dir / ".gitignore").write_text(GITIGNORE_CONTENT, encoding="utf-8")

    wally_content = generate_wally_toml(template, project_name, args.wally)
    if wally_content:
        (output_dir / "wally.toml").write_text(wally_content, encoding="utf-8")

    readme = generate_project_readme(template, project_name, ext)
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    print("Project '{}' created at {}".format(project_name, output_dir))
    print("  Template: {}".format(template))
    print("  Syntax:   {}".format(ext))
    print("")
    print("Next steps:")
    print("  cd {}".format(output_dir))
    print("  rojo serve")


def main():
    parser = argparse.ArgumentParser(
        prog="rojo-template-scaffold",
        description="Scaffold a new Rojo-based Roblox project",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("-n", "--name", default="my-game", help="Project name (default: my-game)")
    init_parser.add_argument(
        "-t", "--template",
        default="minimal",
        choices=["obby", "rpg", "simulator", "tycoon", "pvp", "framework", "minimal"],
        help="Template to use (default: minimal)",
    )
    init_parser.add_argument("-p", "--path", default=".", help="Output directory (default: current dir)")
    init_parser.add_argument("--list-templates", action="store_true", help="List available templates and exit")
    init_parser.add_argument("--luau-types", action="store_true", help="Include Luau type definitions")
    init_parser.add_argument("--wally", action="store_true", help="Generate wally.toml with dependencies")
    init_parser.add_argument("--storybook", action="store_true", help="Include UI component storybook structure")
    init_parser.add_argument("--syntax", choices=["luau", "lua"], default="luau", help="Script syntax (default: luau)")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing directory")

    args = parser.parse_args()

    if args.command == "init" and args.list_templates:
        list_templates()
        return

    if hasattr(args, "list_templates") and args.list_templates and args.command is None:
        list_templates()
        return

    if args.command == "init":
        scaffold(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
