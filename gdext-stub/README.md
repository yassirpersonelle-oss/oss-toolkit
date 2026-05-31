# gdext-stub

Stop writing GDScript stubs by hand.

## Why

When you build a GDExtension project in C++ or Rust, Godot has no autocomplete or type information for your custom classes in GDScript. Every time you add a new node or resource class, you manually create a stub file with `class_name`, `extends`, and boilerplate methods just to get autocomplete working. This takes 45+ minutes of tedious boilerplate per class.

`gdext-stub` parses your `.gdextension` file and generates complete GDScript stubs with full type signatures in seconds.

## Usage

```bash
python gdext-stub.py --input my_extension.gdextension --output game/stubs/
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-i`, `--input` | Path to the `.gdextension` file | **(required)** |
| `-o`, `--output` | Output directory for generated stubs | `stubs/` |
| `--godot-version` | Target Godot version | `4.3` |

## Example

Given `my_extension.gdextension`:

```ini
[configuration]
entry_symbol = "gdext_rust_init"

[extension]
types = ["MyNode", "MyResource", "MyEditorPlugin"]
```

Running:

```bash
python gdext-stub.py -i my_extension.gdextension -o game/stubs/
```

Produces:

```
Generated 3 stub files in game/stubs/
```

With `game/stubs/MyNode.gd`:

```gdscript
class_name MyNode
extends Node


## Auto-generated stub for MyNode.
## Add your implementation below.

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
```

## Requirements

- Python 3.6+
- No external dependencies (stdlib only)
