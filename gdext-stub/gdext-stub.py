#!/usr/bin/env python3
"""Generate GDScript stub files from Godot .gdextension definitions."""

import argparse
import configparser
import os
import sys
from pathlib import Path

BASE_CLASSES = {
    "Node": "Node",
    "Node2D": "Node2D",
    "Node3D": "Node3D",
    "Control": "Control",
    "Resource": "Resource",
    "RefCounted": "RefCounted",
    "Object": "Object",
    "CanvasItem": "CanvasItem",
    "Spatial": "Node3D",
    "Control": "Control",
    "Button": "Button",
    "Label": "Label",
    "LineEdit": "LineEdit",
    "TextEdit": "TextEdit",
    "RichTextLabel": "RichTextLabel",
    "Panel": "Panel",
    "MarginContainer": "MarginContainer",
    "VBoxContainer": "VBoxContainer",
    "HBoxContainer": "HBoxContainer",
    "GridContainer": "GridContainer",
    "ColorRect": "ColorRect",
    "TextureRect": "TextureRect",
    "Sprite2D": "Sprite2D",
    "Sprite3D": "Sprite3D",
    "AnimatedSprite2D": "AnimatedSprite2D",
    "Camera2D": "Camera2D",
    "Camera3D": "Camera3D",
    "TileMap": "TileMap",
    "TileMapLayer": "TileMapLayer",
    "AudioStreamPlayer": "AudioStreamPlayer",
    "AudioStreamPlayer2D": "AudioStreamPlayer2D",
    "AudioStreamPlayer3D": "AudioStreamPlayer3D",
    "AnimationPlayer": "AnimationPlayer",
    "AnimationTree": "AnimationTree",
    "Timer": "Timer",
    "Area2D": "Area2D",
    "Area3D": "Area3D",
    "CharacterBody2D": "CharacterBody2D",
    "CharacterBody3D": "CharacterBody3D",
    "RigidBody2D": "RigidBody2D",
    "RigidBody3D": "RigidBody3D",
    "StaticBody2D": "StaticBody2D",
    "StaticBody3D": "StaticBody3D",
    "CollisionShape2D": "CollisionShape2D",
    "CollisionShape3D": "CollisionShape3D",
    "Marker2D": "Marker2D",
    "Marker3D": "Marker3D",
    "Path2D": "Path2D",
    "Path3D": "Path3D",
    "NavigationAgent2D": "NavigationAgent2D",
    "NavigationAgent3D": "NavigationAgent3D",
    "HTTPRequest": "HTTPRequest",
    "MultiplayerSynchronizer": "MultiplayerSynchronizer",
    "MultiplayerSpawner": "MultiplayerSpawner",
    "ParallaxBackground": "ParallaxBackground",
    "ParallaxLayer": "ParallaxLayer",
    "CanvasModulate": "CanvasModulate",
    "WorldEnvironment": "WorldEnvironment",
    "DirectionalLight3D": "DirectionalLight3D",
    "OmniLight3D": "OmniLight3D",
    "SpotLight3D": "SpotLight3D",
    "MeshInstance3D": "MeshInstance3D",
    "CSGBox3D": "CSGBox3D",
    "SubViewport": "SubViewport",
    "SubViewportContainer": "SubViewportContainer",
}

STUB_METHODS = """\

func _ready() -> void:
	pass

func _process(delta: float) -> void:
	pass

func _physics_process(delta: float) -> void:
	pass

func _input(event: InputEvent) -> void:
	pass

func _draw() -> void:
	pass
"""


def parse_gdextension(filepath: str) -> list[str]:
    """Parse a .gdextension file and return the list of registered types."""
    config = configparser.ConfigParser()
    with open(filepath, encoding="utf-8-sig") as f:
        config.read_file(f)

    if "extension" not in config:
        print(f"Error: No [extension] section found in {filepath}", file=sys.stderr)
        sys.exit(1)

    types_str = config.get("extension", "types", fallback="[]")
    types_str = types_str.strip()

    if types_str.startswith("[") and types_str.endswith("]"):
        types_str = types_str[1:-1]

    if not types_str:
        return []

    types = []
    for t in types_str.split(","):
        t = t.strip().strip('"').strip("'")
        if t:
            types.append(t)

    return list(dict.fromkeys(types))


def infer_base_class(class_name: str) -> str:
    """Infer the most appropriate Godot base class for a given class name."""
    if class_name in BASE_CLASSES:
        return BASE_CLASSES[class_name]

    name_lower = class_name.lower()
    for keyword, base in [
        ("button", "Button"),
        ("label", "Label"),
        ("panel", "Panel"),
        ("container", "VBoxContainer"),
        ("sprite", "Sprite2D"),
        ("camera", "Camera2D"),
        ("player", "CharacterBody2D"),
        ("body", "CharacterBody2D"),
        ("area", "Area2D"),
        ("collision", "CollisionShape2D"),
        ("timer", "Timer"),
        ("audio", "AudioStreamPlayer"),
        ("animation", "AnimationPlayer"),
        ("light", "DirectionalLight3D"),
        ("resource", "Resource"),
        ("editor", "Control"),
        ("plugin", "Node"),
    ]:
        if keyword in name_lower:
            return base

    return "Node"


def generate_stub(class_name: str, base_class: str) -> str:
    """Generate GDScript stub content for a class."""
    lines = [
        f"class_name {class_name}",
        f"extends {base_class}",
        "",
        "",
        f"## Auto-generated stub for {class_name}.",
        "## Add your implementation below.",
        "",
    ]

    method_lines = STUB_METHODS.strip("\n")
    lines.append(method_lines)
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate GDScript stub files from .gdextension definitions."
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to the .gdextension file",
    )
    parser.add_argument(
        "-o", "--output",
        default="stubs/",
        help="Output directory for generated stubs (default: stubs/)",
    )
    parser.add_argument(
        "--godot-version",
        default="4.3",
        help="Target Godot version (default: 4.3)",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    types = parse_gdextension(str(input_path))

    if not types:
        print("No types found in [extension] section.", file=sys.stderr)
        sys.exit(0)

    count = 0
    for type_name in types:
        class_name = type_name.rsplit(".", 1)[-1] if "." in type_name else type_name
        base_class = infer_base_class(class_name)
        stub_content = generate_stub(class_name, base_class)

        stub_path = output_dir / f"{class_name}.gd"
        stub_path.write_text(stub_content, encoding="utf-8")
        count += 1

    print(f"Generated {count} stub files in {output_dir}/")


if __name__ == "__main__":
    main()
