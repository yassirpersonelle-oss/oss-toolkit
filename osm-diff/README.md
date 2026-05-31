# osm-diff

**Review OpenStreetMap changes like a human**

## Why?

OSM changesets are hard to review with existing tools. Raw XML diffs are overwhelming and impossible to parse at a glance. `osm-diff` generates human-readable changelogs that categorize changes into logical groups: roads, buildings, POIs, nature, infrastructure, and generic changes.

## Usage

```bash
# Compare two OSM files
osm-diff --old old.osm --new new.osm

# Process a diff/osc file directly
osm-diff --old changes.osc

# Save output to file
osm-diff --old old.osm --new new.osm --output changelog.txt

# JSON output
osm-diff --old old.osm --new new.osm --json --output changelog.json

# Show full tag details
osm-diff --old old.osm --new new.osm --verbose

# Limit entries per category
osm-diff --old old.osm --new new.osm --limit 100
```

## Options

| Option | Description |
|--------|-------------|
| `--old` | Old .osm/.osc file (required) |
| `--new` | New .osm/.osc file (optional - if omitted, treat --old as diff/osc file) |
| `--output`, `-o` | Output file (default: stdout) |
| `--json` | Output in JSON format |
| `--verbose` | Show full tag details |
| `--limit` | Max entries per category (default: 50) |

## Supported OSM Element Types

- **Nodes**: Point features (POIs, traffic signals, etc.)
- **Ways**: Linear features (roads, buildings, etc.)
- **Relations**: Complex features (routes, boundaries, etc.)

## Change Categories

| Category | Examples |
|----------|----------|
| 🛣️ Road changes | highway, motorway, trunk, primary, secondary, etc. |
| 🏢 Building changes | building=yes, commercial, industrial, etc. |
| 🏷️ POI changes | shop, amenity, tourism, leisure, historic, craft |
| 🌳 Nature changes | natural, landuse, waterway |
| 🏗️ Infrastructure changes | power, man_made, emergency |
| 📍 Generic | Everything else |

## How to Get .osm Files

1. **From OpenStreetMap website**:
   - Use the export feature to download a viewport as .osm
   - Use the Overpass API to query specific areas

2. **Using JOSM**:
   - Download data with JOSM and save as .osm

3. **Using osmium**:
   ```bash
   osmium extract -b west,south,east,north input.osm.pbf -o output.osm
   ```

4. **Diff files (.osc)**:
   - Export changesets from OSM website
   - Use `osmium diff` to create diff files