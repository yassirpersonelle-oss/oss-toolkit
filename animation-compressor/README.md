# animation-compressor

Slim down Roblox animations for mobile without losing quality.

## Why

R15 rigs pack 30+ bones. At 60 FPS, a 3-second idle animation stores up to 5,400 keyframes. On mobile, this wastes memory and tanks framerate. Most of those keyframes are redundant — bones that barely move, linear segments that can be interpolated, and static limbs that never change pose.

## Usage

```bash
# Compress a single animation
python animation-compressor.py -i idle_wave.rbxm

# Compress all animations in a directory
python animation-compressor.py -i animations/ -o compressed/

# Preview savings without writing files
python animation-compressor.py -i anim.rbxm --dry-run --verbose

# Export a JSON report
python animation-compressor.py -i anim.rbxm --json report.json

# Tighter tolerance for higher precision
python animation-compressor.py -i anim.rbxm -t 0.5 --tolerance-position 0.005
```

### Options

| Flag | Alias | Default | Description |
|------|-------|---------|-------------|
| `--input` | `-i` | *(required)* | Input .rbxm file or directory |
| `--output` | `-o` | `compressed/` | Output directory |
| `--tolerance` | `-t` | `1.0` | Max angle deviation in degrees |
| `--tolerance-position` | | `0.01` | Max position deviation in studs |
| `--json` | | *(none)* | Write JSON report to file |
| `--verbose` | | `false` | Show per-bone statistics |
| `--dry-run` | | `false` | Preview only, don't write files |
| `--target-ratio` | | `0.5` | Target compression ratio |

## How compression works

The tool parses `.rbxm` files (which are XML) to extract the `KeyframeSequence → Keyframe → Pose` hierarchy. It then applies four passes:

1. **Static bone detection** — Bones that never move across the entire animation get all duplicate keyframes stripped, keeping only one.

2. **Redundant keyframe removal** — If two consecutive keyframes have the same pose (within tolerance), the middle one is removed. This catches "hold" frames where the animator left extra keys.

3. **Linear sequence detection** — For any three consecutive keyframes, if the middle one's pose can be reproduced by interpolating between the outer two, it's removed. Works for both position (lerp) and rotation (slerp).

4. **Easing simplification** — If easing is set to `InOut` but the curve is near-linear, it's simplified to a single direction.

## Tolerance vs quality

| Tolerance | Use case | Expected savings |
|-----------|----------|-----------------|
| `0.5°` | Precise combat animations, cutscenes | 15–25% |
| `1.0°` | General locomotion, emotes *(recommended)* | 25–50% |
| `2.0°` | Background NPCs, ambient, decorative | 40–65% |

Lower tolerance preserves more keyframes and fidelity but saves less space. Higher tolerance removes more aggressively — use it for low-priority animations where slight imprecision won't be noticed.

Position tolerance works the same way: `0.01` studs (about 0.28cm) is negligible for most use cases. Increase to `0.05` for aggressive compression.

## License

MIT
