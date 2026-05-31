# rbx-asset-audit

**Your game doesn't need to be 500MB.**

Roblox games that exceed 100MB on disk routinely lose 40-60% of potential players
on mobile — every megabyte adds seconds to load time. `rbx-asset-audit` scans your
Rojo project or `.rbxl`/`.rbxm` file and surfaces exactly which assets are bloated,
duplicated, or potentially unused, so you can trim before you ship.

## Installation

No dependencies — Python 3.8+ standard library only.

```bash
python3 rbx-asset-audit.py --path your-game/
```

## Usage

```
usage: rbx-asset-audit.py --path PATH [--json] [--verbose] [--threshold MB]
                          [--unused] [--duplicates] [--output PATH]

  --path DIR|FILE     Rojo project directory, .rbxl file, or .rbxm file
  --json              Emit JSON instead of a terminal report
  --verbose           Show every file, not just flagged ones
  --threshold N       Minimum file size in MB to flag (default: 5)
  --unused            Scan .lua/.luau scripts for asset references and
                      report assets not referenced in any script
  --duplicates        Hash every file and report identical duplicates
  --output, -o PATH   Write report to file
```

### Examples

```bash
# Quick audit of a Rojo project
python3 rbx-asset-audit.py --path src/assets/

# Full audit with unused and duplicate detection, save to file
python3 rbx-asset-audit.py --path my-game/ --unused --duplicates -o audit-report.txt

# Low threshold (1MB) for a mobile project
python3 rbx-asset-audit.py --path my-game/ --threshold 1

# Inspect a single .rbxl file
python3 rbx-asset-audit.py --path my-place.rbxl --json
```

## What it checks

### Directory mode (Rojo asset folders)

| Category | Extensions | What's reported |
|---|---|---|
| Images   | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tga` | File size, pixel dimensions. Flagged if >2048px in any dimension. |
| Audio    | `.mp3`, `.ogg`, `.wav` | File size, estimated duration (from header). Flagged if >5 minutes. |
| Animations | `.rbxm` | File size. Keyframe sequences can be heavy and are flagged above the threshold. |
| Meshes   | `.obj`, `.fbx` | File size, vertex count. Flagged if >50K vertices. |
| Scripts  | `.lua`, `.luau` | File size, line count. Flagged if >10K lines (monolithic scripts). |
| Unknown  | Everything else | Flagged above the threshold for manual review (fonts, archives, etc.). |

### .rbxl / .rbxmx mode

| Check | Why it matters |
|---|---|
| Instance class counts | Too many `Part` instances (>2000) inflate physics and rendering. |
| Large embedded scripts | Scripts with thousands of lines bloat the place file and compile slowly. |
| MeshPart triangle counts | High-poly collision meshes crush physics performance. |
| Embedded content sizes | Base64-encoded textures/sounds stored directly in the file. |
| External asset URLs | `rbxassetid://` references that may be outdated or unused. |

### Unused asset detection (`--unused`)

Scans every `.lua` and `.luau` file for:
- `rbxassetid://` numeric IDs
- Quoted file paths (e.g. `"assets/icon.png"`)
- `rbxasset://` and `asset://` URIs

Cross-references with files on disk. Reports:
- Files on disk that no script references
- This is a heuristic — manually verify before deleting

### Duplicate detection (`--duplicates`)

SHA-256 hashes every file >1KB. Identical files are grouped and reported
with the wasted space. Common culprits:
- Backup copies (`bg.png` + `bg-copy.png`)
- Versioned duplicates (`explosion.png` + `explosion-v2.png`)
- Assets copied between folders

## How durations and dimensions are calculated

| Format | Method |
|---|---|
| PNG dimensions | Parses IHDR chunk (bytes 16-23). |
| JPEG dimensions | Walks JFIF segments to find the SOF0/SOF2 marker. |
| BMP dimensions | Reads the BITMAPINFOHEADER. |
| TGA dimensions | Reads header bytes 12-15. |
| MP3 duration | Finds the first MPEG frame header, extracts bitrate, estimates from file size. |
| WAV duration | Reads sample rate and byte rate from the RIFF header, divides data chunk size. |
| OGG duration | Reads the last page's granule position and the Vorbis sample rate from the ID header. |
| OBJ vertices | Counts lines starting with `v `. |
| FBX vertices | Extracts vertex coordinate triplets from `Vertices:` blocks. |

All parsing is approximate — for authoritative values use dedicated tools —
but it's correct enough to identify obvious bloat.

## Tips for reducing asset sizes

- **Images:** Never ship >2048px. Use 1024px for most textures, 512px for
  UI elements. Convert PNG to JPG for photographic content. Run through
  `pngcrush` or `oxipng` for lossless compression.
- **Audio:** Keep background music under 3 minutes, sound effects under 5
  seconds. Encode at 128kbps MP3 or 96kbps OGG. Mono for SFX.
- **Meshes:** Decimate to <10K triangles for static objects, <5K for
  dynamic. Use LODs for distant objects.
- **Scripts:** Split monoliths into ModuleScripts. LuaU compiles to
  bytecode — fewer lines mean faster load.
- **Animations:** Use compression keyframes. Fewer bones and shorter
  sequences.
- **Fonts:** Subset custom fonts to only the glyphs you actually use.
- **Spritesheets:** Combine frame sequences into a single atlas texture.

## License

MIT
