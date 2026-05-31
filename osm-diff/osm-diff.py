#!/usr/bin/env python3
"""
osm-diff: A Python CLI that generates human-readable changelogs from OpenStreetMap XML files.

Compares two .osm or .osc (diff) files and categorizes changes into roads, buildings,
POIs, nature, infrastructure, and generic changes.
"""

import argparse
import json
import sys
import io
from collections import defaultdict
from xml.etree import ElementTree as ET

# Fix Windows encoding for emoji output
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# Category classification based on tags
CATEGORIES = {
    "road": {
        "highway": [
            "motorway", "trunk", "primary", "secondary", "tertiary",
            "unclassified", "residential", "service", "motorway_link",
            "trunk_link", "primary_link", "secondary_link", "tertiary_link",
            "living_street", "pedestrian", "track", "path", "footway",
            "cycleway", "bridleway", "steps", "corridor", "construction"
        ],
    },
    "building": {
        "building": ["yes", "house", "commercial", "industrial", "retail",
                     "warehouse", "cathedral", "chapel", "church", "hospital",
                     "school", "stadium", "train_station", "university", "hotel"],
    },
    "poi": {
        "shop": True,
        "amenity": True,
        "tourism": True,
        "leisure": True,
        "historic": True,
        "craft": True,
    },
    "nature": {
        "natural": True,
        "landuse": True,
        "waterway": True,
    },
    "infrastructure": {
        "power": True,
        "man_made": True,
        "emergency": True,
    },
}


def classify_element(tags):
    """Classify an element into a category based on its tags."""
    for tag in tags:
        key = tag["k"]
        value = tag["v"]

        # Check roads
        if key == "highway":
            return "road"

        # Check buildings
        if key == "building":
            return "building"

        # Check POIs
        if key in CATEGORIES["poi"]:
            return "poi"

        # Check nature
        if key in CATEGORIES["nature"]:
            return "nature"

        # Check infrastructure
        if key in CATEGORIES["infrastructure"]:
            return "infrastructure"

    return "generic"


def parse_osm_element(elem):
    """Parse an OSM element (node, way, relation) into a dictionary."""
    element = {
        "type": elem.tag,
        "id": elem.get("id"),
        "lat": elem.get("lat"),
        "lon": elem.get("lon"),
        "tags": [],
        "nds": [],
        "members": [],
    }

    # Parse tags
    for tag in elem.findall("tag"):
        element["tags"].append({
            "k": tag.get("k"),
            "v": tag.get("v"),
        })

    # Parse way nodes
    for nd in elem.findall("nd"):
        element["nds"].append(nd.get("ref"))

    # Parse relation members
    for member in elem.findall("member"):
        element["members"].append({
            "type": member.get("type"),
            "ref": member.get("ref"),
            "role": member.get("role"),
        })

    return element


def parse_osm_file(filepath):
    """Parse an OSM or OSC file and return elements."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    elements = []

    # Check if this is a diff file (.osc)
    if root.tag == "osmChange":
        for action in root.findall("action"):
            if action.get("type") in ("create", "modify", "delete"):
                for elem in action:
                    element = parse_osm_element(elem)
                    element["action"] = action.get("type")
                    elements.append(element)
    else:
        # Regular .osm file
        for elem in root:
            if elem.tag in ("node", "way", "relation"):
                elements.append(parse_osm_element(elem))

    return elements


def get_element_key(element):
    """Get a unique key for an element (type/id)."""
    return f"{element['type']}/{element['id']}"


def get_tag_dict(element):
    """Convert tag list to dictionary for easy comparison."""
    return {tag["k"]: tag["v"] for tag in element["tags"]}


def get_element_name(element):
    """Get the name of an element from its tags."""
    tags = get_tag_dict(element)
    return tags.get("name")


def get_element_summary(element):
    """Get a human-readable summary of an element."""
    tags = get_tag_dict(element)
    name = get_element_name(element)

    # Try to get a meaningful description
    if "highway" in tags:
        road_type = tags["highway"]
        if name:
            return f"{road_type} road \"{name}\""
        else:
            return f"{road_type} road"

    if "building" in tags:
        building_type = tags["building"]
        if building_type == "yes":
            building_type = "building"
        if name:
            return f"{building_type} \"{name}\""
        else:
            return f"{building_type}"

    for poi_key in ["shop", "amenity", "tourism", "leisure", "historic", "craft"]:
        if poi_key in tags:
            poi_type = tags[poi_key]
            if name:
                return f"{poi_type} \"{name}\""
            else:
                return f"{poi_type}"

    if "natural" in tags:
        natural_type = tags["natural"]
        if name:
            return f"{natural_type} \"{name}\""
        else:
            return f"{natural_type}"

    if "landuse" in tags:
        landuse_type = tags["landuse"]
        if name:
            return f"{landuse_type} \"{name}\""
        else:
            return f"{landuse_type}"

    if name:
        return f"\"{name}\""

    if element["type"] == "node" and element["lat"] and element["lon"]:
        return f"node at {element['lat']}, {element['lon']}"

    return f"{element['type']}/{element['id']}"


def compute_changes(old_elements, new_elements):
    """Compute added, deleted, and modified elements between two sets."""
    old_map = {get_element_key(e): e for e in old_elements}
    new_map = {get_element_key(e): e for e in new_elements}

    added = []
    deleted = []
    modified = []

    # Find added and modified elements
    for key, new_elem in new_map.items():
        if key not in old_map:
            added.append(new_elem)
        else:
            old_elem = old_map[key]
            old_tags = get_tag_dict(old_elem)
            new_tags = get_tag_dict(new_elem)

            # Check for changes
            if old_tags != new_tags or old_elem.get("nds") != new_elem.get("nds"):
                # Compute tag changes
                tag_changes = []
                all_keys = set(list(old_tags.keys()) + list(new_tags.keys()))
                for k in sorted(all_keys):
                    old_val = old_tags.get(k)
                    new_val = new_tags.get(k)
                    if old_val != new_val:
                        tag_changes.append({
                            "key": k,
                            "old": old_val,
                            "new": new_val,
                        })

                modified.append({
                    "element": new_elem,
                    "old": old_elem,
                    "tag_changes": tag_changes,
                })

    # Find deleted elements
    for key, old_elem in old_map.items():
        if key not in new_map:
            deleted.append(old_elem)

    return added, deleted, modified


def process_osc_actions(elements):
    """Process OSC file actions (create, modify, delete)."""
    added = []
    deleted = []
    modified = []

    for elem in elements:
        action = elem.get("action", "modify")

        if action == "create":
            added.append(elem)
        elif action == "delete":
            deleted.append(elem)
        elif action == "modify":
            modified.append({
                "element": elem,
                "old": None,  # We don't have the old version in OSC
                "tag_changes": [{"key": tag["k"], "old": None, "new": tag["v"]}
                               for tag in elem["tags"]],
            })

    return added, deleted, modified


def categorize_changes(added, deleted, modified):
    """Categorize all changes by type."""
    categories = {
        "road": {"added": [], "deleted": [], "modified": []},
        "building": {"added": [], "deleted": [], "modified": []},
        "poi": {"added": [], "deleted": [], "modified": []},
        "nature": {"added": [], "deleted": [], "modified": []},
        "infrastructure": {"added": [], "deleted": [], "modified": []},
        "generic": {"added": [], "deleted": [], "modified": []},
    }

    # Categorize added elements
    for elem in added:
        category = classify_element(elem["tags"])
        categories[category]["added"].append(elem)

    # Categorize deleted elements
    for elem in deleted:
        category = classify_element(elem["tags"])
        categories[category]["deleted"].append(elem)

    # Categorize modified elements
    for mod in modified:
        elem = mod["element"]
        category = classify_element(elem["tags"])
        categories[category]["modified"].append(mod)

    return categories


def format_change(elem, change_type, verbose=False):
    """Format a single change for display."""
    summary = get_element_summary(elem)
    elem_key = get_element_key(elem)
    location = ""
    if elem["type"] == "node" and elem["lat"] and elem["lon"]:
        location = f" at {elem['lat']}, {elem['lon']}"

    if change_type == "added":
        return f"  [+1] Added: {summary}{location} ({elem_key})"
    elif change_type == "deleted":
        return f"  [-1] Deleted: {summary}{location} ({elem_key})"
    elif change_type == "modified":
        return f"  [~1] Modified: {summary}{location} ({elem_key})"


def format_modified_detail(mod, verbose=False):
    """Format detailed changes for a modified element."""
    lines = []
    for change in mod["tag_changes"]:
        old_val = change["old"] if change["old"] is not None else "(none)"
        new_val = change["new"] if change["new"] is not None else "(none)"
        lines.append(f"    {change['key']}: {old_val} → {new_val}")

    if verbose:
        # Add full tag details
        tags = get_tag_dict(mod["element"])
        lines.append("    All tags:")
        for k, v in sorted(tags.items()):
            lines.append(f"      {k}: {v}")

    return "\n".join(lines)


def format_text_output(categories, total_changes, added_count, deleted_count, modified_count, limit=50):
    """Format the changelog as human-readable text."""
    lines = [
        "🗺️ osm-diff changelog",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    category_names = {
        "road": ("🛣️ ROAD CHANGES", "road"),
        "building": ("🏢 BUILDING CHANGES", "building"),
        "poi": ("🏷️ POI CHANGES", "poi"),
        "nature": ("🌳 NATURE CHANGES", "nature"),
        "infrastructure": ("🏗️ INFRASTRUCTURE CHANGES", "infrastructure"),
        "generic": ("📍 GENERIC CHANGES", "generic"),
    }

    for cat_key, (cat_name, _) in category_names.items():
        cat_data = categories[cat_key]
        total = (len(cat_data["added"]) + len(cat_data["deleted"]) +
                len(cat_data["modified"]))

        if total == 0:
            continue

        lines.append(f"  {cat_name} ({total})")

        # Added elements
        for i, elem in enumerate(cat_data["added"][:limit]):
            lines.append(format_change(elem, "added"))

        # Deleted elements
        for i, elem in enumerate(cat_data["deleted"][:limit]):
            lines.append(format_change(elem, "deleted"))

        # Modified elements
        for i, mod in enumerate(cat_data["modified"][:limit]):
            elem = mod["element"]
            lines.append(format_change(elem, "modified"))
            lines.append(format_modified_detail(mod))

        # Show if there are more changes
        shown = min(total, limit)
        if total > limit:
            lines.append(f"    ... and {total - limit} more changes")

        lines.append("")

    # Summary
    lines.append(f"📊 Summary: {total_changes} changes ({added_count} added, {deleted_count} deleted, {modified_count} modified)")

    return "\n".join(lines)


def format_json_output(categories, total_changes, added_count, deleted_count, modified_count, limit=50):
    """Format the changelog as JSON."""
    output = {
        "summary": {
            "total": total_changes,
            "added": added_count,
            "deleted": deleted_count,
            "modified": modified_count,
        },
        "categories": {}
    }

    category_names = {
        "road": "road",
        "building": "building",
        "poi": "poi",
        "nature": "nature",
        "infrastructure": "infrastructure",
        "generic": "generic",
    }

    for cat_key, cat_name in category_names.items():
        cat_data = categories[cat_key]
        total = (len(cat_data["added"]) + len(cat_data["deleted"]) +
                len(cat_data["modified"]))

        if total == 0:
            continue

        output["categories"][cat_name] = {
            "total": total,
            "added": [
                {
                    "type": elem["type"],
                    "id": elem["id"],
                    "summary": get_element_summary(elem),
                    "lat": elem.get("lat"),
                    "lon": elem.get("lon"),
                    "tags": get_tag_dict(elem),
                }
                for elem in cat_data["added"][:limit]
            ],
            "deleted": [
                {
                    "type": elem["type"],
                    "id": elem["id"],
                    "summary": get_element_summary(elem),
                    "lat": elem.get("lat"),
                    "lon": elem.get("lon"),
                    "tags": get_tag_dict(elem),
                }
                for elem in cat_data["deleted"][:limit]
            ],
            "modified": [
                {
                    "type": mod["element"]["type"],
                    "id": mod["element"]["id"],
                    "summary": get_element_summary(mod["element"]),
                    "lat": mod["element"].get("lat"),
                    "lon": mod["element"].get("lon"),
                    "changes": mod["tag_changes"],
                }
                for mod in cat_data["modified"][:limit]
            ],
        }

    return json.dumps(output, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Generate human-readable changelogs from OpenStreetMap XML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  osm-diff --old old.osm --new new.osm
  osm-diff --old changes.osc
  osm-diff --old old.osm --new new.osm --output changelog.txt
  osm-diff --old old.osm --new new.osm --json --output changelog.json
        """
    )

    parser.add_argument("--old", required=True, help="Old .osm/.osc file (required)")
    parser.add_argument("--new", help="New .osm/.osc file (optional - if omitted, treat --old as diff/osc file)")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--verbose", action="store_true", help="Show full tag details")
    parser.add_argument("--limit", type=int, default=50, help="Max entries per category (default: 50)")

    args = parser.parse_args()

    try:
        # Parse files
        if args.new:
            old_elements = parse_osm_file(args.old)
            new_elements = parse_osm_file(args.new)
            added, deleted, modified = compute_changes(old_elements, new_elements)
        else:
            # Treat --old as a diff/osc file
            elements = parse_osm_file(args.old)
            added, deleted, modified = process_osc_actions(elements)

        # Categorize changes
        categories = categorize_changes(added, deleted, modified)

        # Calculate totals
        total_changes = len(added) + len(deleted) + len(modified)
        added_count = len(added)
        deleted_count = len(deleted)
        modified_count = len(modified)

        # Format output
        if args.json:
            output = format_json_output(categories, total_changes, added_count,
                                       deleted_count, modified_count, args.limit)
        else:
            output = format_text_output(categories, total_changes, added_count,
                                       deleted_count, modified_count, args.limit)

        # Write output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
                f.write('\n')
            print(f"Changelog written to {args.output}")
        else:
            print(output)

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except ET.ParseError as e:
        print(f"Error: Invalid XML - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()