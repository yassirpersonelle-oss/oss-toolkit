#!/usr/bin/env python3
"""
rbx-asset-audit — Analyze Roblox place/model files (.rbxl/.rbxm) or asset
directories to find bloated assets that inflate your game's download size.
"""

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from io import BytesIO

IMG_EMOJI = "\U0001F5BC"
AUDIO_EMOJI = "\U0001F3B5"
ANIM_EMOJI = "\U0001F3C3"
MESH_EMOJI = "\U0001F3D7"
SCRIPT_EMOJI = "\U0001F4DD"
UNKNOWN_EMOJI = "\U0001F5DC"


def parse_args():
    p = argparse.ArgumentParser(
        description="rbx-asset-audit — Find bloated Roblox assets",
    )
    p.add_argument(
        "--path", required=True,
        help="Path to .rbxl, .rbxmx, .rbxm file or directory of assets",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON output")
    p.add_argument("--verbose", action="store_true", help="Show all items")
    p.add_argument(
        "--threshold", type=float, default=5.0,
        help="Minimum file size in MB to flag (default: 5)",
    )
    p.add_argument(
        "--unused", action="store_true",
        help="Scan scripts for references and report potentially unused assets",
    )
    p.add_argument(
        "--duplicates", action="store_true",
        help="Find duplicate assets by content hash",
    )
    p.add_argument(
        "--output", "-o", default=None,
        help="Write report to file instead of stdout",
    )
    return p.parse_args()


# ── Image helpers ──────────────────────────────────────────────────────

def _read_be_u16(data, off):
    return struct.unpack(">H", data[off : off + 2])[0]

def _read_le_u16(data, off):
    return struct.unpack("<H", data[off : off + 2])[0]

def _read_be_u32(data, off):
    return struct.unpack(">I", data[off : off + 4])[0]

def _read_le_u32(data, off):
    return struct.unpack("<I", data[off : off + 4])[0]


def png_dims(path):
    with open(path, "rb") as f:
        header = f.read(8)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    with open(path, "rb") as f:
        f.seek(16)
        w = _read_be_u32(f.read(4), 0)
        h = _read_be_u32(f.read(4), 0)
    return w, h


def jpg_dims(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        return None, None
    pos = 2
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        pos += 2
        if marker in (0xD8, 0xD9):
            continue
        if marker in (0xC0, 0xC2):
            if pos + 7 > len(data):
                break
            h = (data[pos + 3] << 8) | data[pos + 4]
            w = (data[pos + 5] << 8) | data[pos + 6]
            return w, h
        if pos + 2 > len(data):
            break
        seg_len = (data[pos] << 8) | data[pos + 1]
        pos += seg_len
    return None, None


def bmp_dims(path):
    with open(path, "rb") as f:
        data = f.read(26)
    if data[:2] != b"BM":
        return None, None
    w = _read_le_u32(data, 18)
    h = _read_le_u32(data, 22)
    return w, h


def tga_dims(path):
    with open(path, "rb") as f:
        data = f.read(18)
    if len(data) < 18:
        return None, None
    w = _read_le_u16(data, 12)
    h = _read_le_u16(data, 14)
    return w, h


def image_dims(path):
    ext = os.path.splitext(path)[1].lower()
    funcs = {".png": png_dims, ".jpg": jpg_dims, ".jpeg": jpg_dims,
             ".bmp": bmp_dims, ".tga": tga_dims}
    fn = funcs.get(ext)
    if fn:
        return fn(path)
    return None, None


# ── Audio helpers ──────────────────────────────────────────────────────

def _find_sync(data, sync, start=0):
    pos = data.find(sync, start)
    if pos == -1:
        return pos, 0
    return pos, 0


def mp3_duration(path, size):
    """Estimate MP3 duration from first valid MPEG frame header."""
    try:
        with open(path, "rb") as f:
            data = f.read(128 * 1024)
    except OSError:
        return None

    bitrates = {
        1: {1: 32, 2: 64, 3: 96, 4: 128, 5: 160, 6: 192, 7: 224, 8: 256,
            9: 288, 10: 320, 11: 352, 12: 384, 13: 416, 14: 448},
        2: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64,
            9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
        3: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64,
            9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
    }
    samplerates = {0: 44100, 1: 48000, 2: 32000}
    if size <= 0:
        return None

    pos = 0
    while pos < len(data) - 4:
        if data[pos] == 0xFF and (data[pos + 1] & 0xE0) == 0xE0:
            b = data[pos + 1], data[pos + 2], data[pos + 3]
            if (b[0] & 0x06) >> 1 != 0:
                pos += 1
                continue
            version = (b[0] & 0x18) >> 3
            layer = (b[0] & 0x06) >> 1
            bitrate_idx = (b[1] & 0xF0) >> 4
            samp_idx = (b[0] & 0x0C) >> 2
            if version == 3:
                version = 1
            elif version == 2:
                version = 2
            elif version == 0:
                version = 3
            else:
                pos += 1
                continue
            br = bitrates.get(layer, {}).get(bitrate_idx, 0)
            if br == 0:
                pos += 1
                continue
            sr = samplerates.get(samp_idx, 44100)
            if layer == 3 and version == 1:
                frame_size = 144 * br * 1000 // sr
            elif layer == 3 and version in (2, 3):
                frame_size = 72 * br * 1000 // sr
            elif layer == 2:
                frame_size = 144 * br * 1000 // sr
            else:
                frame_size = (12 * br * 1000 // sr + 4) & ~3
            if frame_size <= 0:
                pos += 1
                continue
            samples_per_frame = 1152 if version == 1 else 576
            duration = (size / (frame_size or 1)) * samples_per_frame / (sr or 1)
            return duration
        pos += 1
    return None


def wav_duration(path):
    try:
        with open(path, "rb") as f:
            header = f.read(44)
        if len(header) < 44:
            return None
        if header[:4] != b"RIFF":
            return None
        byte_rate = _read_le_u32(header, 28)
        data_size = _read_le_u32(header, 40)
        if byte_rate == 0:
            return None
        return data_size / byte_rate
    except OSError:
        return None


def ogg_duration(path, size):
    try:
        with open(path, "rb") as f:
            data = f.read(min(size, 2 * 1024 * 1024))
    except OSError:
        return None
    if data[:4] != b"OggS":
        return None
    pos = 0
    granule = 0
    while pos < len(data) - 27:
        if data[pos : pos + 4] != b"OggS":
            break
        granule = _read_le_u32(data, pos + 6) | (_read_le_u32(data, pos + 10) << 32)
        seg_count = data[pos + 26]
        seg_end = pos + 27 + seg_count
        if seg_end > len(data):
            break
        total = sum(data[pos + 27 + i] for i in range(seg_count))
        pos = seg_end + total
    pos = 0
    while pos < len(data) - 56:
        if data[pos : pos + 4] != b"OggS":
            break
        header_type = data[pos + 5]
        seg_count = data[pos + 26]
        seg_end = pos + 27 + seg_count
        if seg_end > len(data):
            break
        sizes = [data[pos + 27 + i] for i in range(seg_count)]
        pkt_start = seg_end
        for sz in sizes:
            pkt_data = data[pkt_start : pkt_start + sz]
            if header_type & 2 and sz >= 7 and pkt_data[:7] == b"\x01vorbis":
                sr_pos = pkt_start + 12
                if sr_pos + 3 < len(data):
                    sr = _read_le_u32(data, sr_pos)
                    if granule and sr:
                        return granule / sr
                return None
            pkt_start += sz
        pos = seg_end + sum(sizes)
    return None


def audio_duration(path, size):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        return mp3_duration(path, size)
    elif ext == ".wav":
        return wav_duration(path)
    elif ext == ".ogg":
        return ogg_duration(path, size)
    return None


# ── Mesh helpers ───────────────────────────────────────────────────────

def obj_vertex_count(path):
    count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("v "):
                    count += 1
    except OSError:
        return 0
    return count


def fbx_vertex_count(path):
    count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
        for m in re.finditer(r"\bVertices:\s*\*?(\d+)\s*\*?\{[^}]*a:", data):
            # FBX vertex data block — count doubles/triples
            block = data[m.end() : data.find("}", m.end())]
            if block.strip():
                count += sum(1 for v in re.findall(r"[-]?\d+\.\d+", block)) // 3
    except OSError:
        return 0
    return count


def mesh_vertex_count(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        return obj_vertex_count(path)
    elif ext == ".fbx":
        return fbx_vertex_count(path)
    return 0


# ── Roblox XML parsing ─────────────────────────────────────────────────

def _decompress_if_binary(path):
    """Detect and decompress Roblox binary format using the marker bytes."""
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
    except OSError:
        return path
    if magic[:6] == b"<roblo":
        return path
    if magic[:4] == b"PK\x03\x04":
        from zipfile import ZipFile
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
        with ZipFile(path) as zf, open(tmp.name, "wb") as outf:
            names = [n for n in zf.namelist() if n.lower().endswith((".rbxlx", ".rbxmx", ".xml"))]
            if names:
                outf.write(zf.read(names[0]))
            elif zf.namelist():
                outf.write(zf.read(zf.namelist()[0]))
        return tmp.name
    return path


def parse_roblox_xml(path):
    """Walk Roblox XML instance tree, return a list of findings."""
    path = _decompress_if_binary(path)
    findings = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        if "<roblox" in open(path, "rb").read(200).decode("latin-1", errors="ignore").lower():
            return findings
        return findings

    class_counts = defaultdict(int)
    script_sizes = []
    content_urls = []
    huge_meshes = []
    embedded_sizes = []

    instance_map = {}

    def walk(elem, depth=0):
        class_name = elem.get("class", "")
        referent = elem.get("referent", "")
        if class_name:
            class_counts[class_name] += 1
        if referent:
            instance_map[referent] = elem

        for child in elem:
            tag_lower = child.tag.lower() if hasattr(child, "tag") else ""

            if tag_lower == "properties":
                # Check for embedded data
                for prop in child:
                    pname = prop.get("name", "")
                    if pname in ("Data", "data", "EmbeddedData"):
                        text = prop.text or ""
                        # Base64-encoded embedded data
                        if text and len(text) > 40:
                            try:
                                decoded = text.encode("ascii")
                            except UnicodeEncodeError:
                                decoded = b""
                            if decoded:
                                import base64
                                try:
                                    raw = base64.b64decode(text)
                                    embedded_sizes.append({
                                        "class": class_name,
                                        "name": elem.get("name", "?"),
                                        "size": len(raw),
                                    })
                                except Exception:
                                    pass
                    if pname in ("Content", "content", "Texture", "TextureId", "MeshId"):
                        text = prop.text or ""
                        if text.startswith("rbxassetid://") or text.startswith("http"):
                            content_urls.append({
                                "class": class_name,
                                "name": elem.get("name", "?"),
                                "url": text,
                            })

            elif tag_lower == "item":
                walk(child, depth + 1)

        # MeshPart triangle count
        props_elem = elem.find("Properties")
        if props_elem is not None and class_name in ("MeshPart", "Part", "UnionOperation"):
            for prop in props_elem:
                pname = prop.get("name", "")
                if pname in ("PhysicsData", "InitialSize", "TriangleCount"):
                    text = prop.text or ""
                    try:
                        val = int(text)
                        if val > 10000:
                            huge_meshes.append({
                                "class": class_name,
                                "name": elem.get("name", "?"),
                                "triangles": val,
                            })
                    except ValueError:
                        pass

        # Script sizes
        if class_name in ("Script", "LocalScript", "ModuleScript"):
            props_elem = elem.find("Properties")
            if props_elem is not None:
                for prop in props_elem:
                    if prop.get("name") == "Source":
                        src = prop.text or ""
                        line_count = len(src.splitlines())
                        if line_count > 100:
                            script_sizes.append({
                                "class": class_name,
                                "name": elem.get("name", "?"),
                                "lines": line_count,
                                "size": len(src.encode("utf-8")),
                            })
                        break

    walk(root)

    return {
        "class_counts": dict(class_counts),
        "script_sizes": sorted(script_sizes, key=lambda x: -x["size"]),
        "content_urls": content_urls,
        "huge_meshes": huge_meshes,
        "embedded_sizes": embedded_sizes,
    }


# ── Directory scanning ─────────────────────────────────────────────────

def scan_directory(root_dir, threshold_bytes):
    """Walk directory and categorize every file."""
    categories = {
        "images": [],
        "audio": [],
        "animations": [],
        "meshes": [],
        "scripts": [],
        "unknown": [],
    }
    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tga"}
    audio_exts = {".mp3", ".ogg", ".wav"}
    anim_exts = {".rbxm"}
    mesh_exts = {".obj", ".fbx"}
    script_exts = {".lua", ".luau"}

    total_count = 0
    total_bytes = 0
    script_paths = []

    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            abspath = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            try:
                size = os.path.getsize(abspath)
            except OSError:
                continue

            total_count += 1
            total_bytes += size
            relpath = os.path.relpath(abspath, root_dir)
            entry = {"name": fn, "path": relpath, "size": size}

            if ext in image_exts:
                w, h = image_dims(abspath)
                entry["width"] = w
                entry["height"] = h
                entry["oversized"] = (w or 0) > 2048 or (h or 0) > 2048
                categories["images"].append(entry)
            elif ext in audio_exts:
                dur = audio_duration(abspath, size)
                entry["duration"] = dur
                entry["too_long"] = dur is not None and dur > 300
                categories["audio"].append(entry)
            elif ext in anim_exts:
                entry["anim_type"] = "rbxm"
                categories["animations"].append(entry)
            elif ext in mesh_exts:
                verts = mesh_vertex_count(abspath)
                entry["vertices"] = verts
                entry["huge"] = verts > 50000
                categories["meshes"].append(entry)
            elif ext in script_exts:
                try:
                    with open(abspath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
                except OSError:
                    lines = 0
                    content = ""
                entry["lines"] = lines
                entry["too_long"] = lines > 10000
                categories["scripts"].append(entry)
                script_paths.append(abspath)
            else:
                categories["unknown"].append(entry)

    for cat in categories.values():
        cat.sort(key=lambda x: -x["size"])

    return {
        "total_count": total_count,
        "total_bytes": total_bytes,
        "categories": categories,
        "script_paths": script_paths,
    }


# ── Unused asset detection ─────────────────────────────────────────────

def find_unused_assets(scan_result, root_dir):
    """Cross-reference script references against disk assets."""
    asset_refs = set()
    script_paths = scan_result.get("script_paths", [])

    for sp in script_paths:
        try:
            with open(sp, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue
        for m in re.finditer(r"rbxassetid://(\d+)", content):
            asset_refs.add(m.group(1))
        for m in re.finditer(r'["\']([^"\']+\.(?:png|jpg|jpeg|bmp|tga|mp3|ogg|wav|obj|fbx|rbxm|rbxmx|otf|ttf))["\']', content, re.IGNORECASE):
            asset_refs.add(m.group(1).lower())
        for m in re.finditer(r'asset://(\S+)["\']', content):
            asset_refs.add(m.group(1).lower())
        for m in re.finditer(r'rbxasset://(\S+)["\']', content):
            asset_refs.add(m.group(1).lower())

    on_disk = set()
    disk_name_set = set()
    all_assets = []
    for cat_name in ("images", "audio", "animations", "meshes", "unknown"):
        for entry in scan_result["categories"].get(cat_name, []):
            rp = entry["path"].replace("\\", "/").lower()
            on_disk.add(rp)
            disk_name_set.add(os.path.basename(rp).lower())
            all_assets.append(entry)
    for entry in scan_result["categories"].get("scripts", []):
        rp = entry["path"].replace("\\", "/").lower()
        on_disk.add(rp)
        all_assets.append(entry)

    potentially_unused = []
    for entry in all_assets:
        rp = entry["path"].replace("\\", "/").lower()
        bn = os.path.basename(rp).lower()
        # Check if any reference roughly matches
        found = False
        for ref in asset_refs:
            rl = ref.lower().replace("\\", "/")
            if rl in rp or rl in bn or bn in rl:
                found = True
                break
        if not found:
            potentially_unused.append(entry)

    potentially_unused.sort(key=lambda x: -x["size"])
    return potentially_unused


# ── Duplicate detection ────────────────────────────────────────────────

def find_duplicates(root_dir):
    """Group files by content hash."""
    hash_map = defaultdict(list)
    total_waste = 0

    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            abspath = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(abspath)
            except OSError:
                continue
            if size < 1024:
                continue
            try:
                with open(abspath, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                h = None
            if h:
                rel = os.path.relpath(abspath, root_dir)
                hash_map[h].append({"path": rel, "size": size})

    dup_groups = []
    for h, entries in hash_map.items():
        if len(entries) > 1:
            entries.sort(key=lambda x: -x["size"])
            wasted = sum(e["size"] for e in entries[1:])
            total_waste += wasted
            dup_groups.append({
                "hash": h[:12],
                "files": entries,
                "wasted": wasted,
            })

    dup_groups.sort(key=lambda x: -x["wasted"])
    return dup_groups, total_waste


# ── Output ─────────────────────────────────────────────────────────────

def format_size(b):
    if b >= 1_000_000_000:
        return f"{b / 1_000_000_000:.1f}GB"
    elif b >= 1_000_000:
        return f"{b / 1_000_000:.1f}MB"
    elif b >= 1_000:
        return f"{b / 1_000:.1f}KB"
    return f"{b}B"


def format_duration(seconds):
    if seconds is None:
        return "?"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def format_report(args, scan_result, unused, duplicates, dup_waste, xml_findings=None):
    lines = []
    root = os.path.basename(os.path.abspath(args.path)) or args.path

    lines.append(f"\U0001F3D7  rbx-asset-audit \u2014 {root}/")
    lines.append("\u2501" * 40)
    lines.append("")

    total_count = scan_result["total_count"]
    total_bytes = scan_result["total_bytes"]
    cats = scan_result["categories"]

    threshold_bytes = int(args.threshold * 1_000_000)
    critical = []
    warnings = []

    for entry in cats["images"]:
        if entry["size"] >= threshold_bytes or entry.get("oversized"):
            critical.append(("image", entry))

    for entry in cats["audio"]:
        if entry["size"] >= threshold_bytes or entry.get("too_long"):
            critical.append(("audio", entry))

    for entry in cats["animations"]:
        if entry["size"] >= threshold_bytes:
            critical.append(("anim", entry))

    for entry in cats["meshes"]:
        if entry["size"] >= threshold_bytes or entry.get("huge"):
            critical.append(("mesh", entry))

    for entry in cats["scripts"]:
        if entry["size"] >= threshold_bytes or entry.get("too_long"):
            critical.append(("script", entry))

    for entry in cats["unknown"]:
        if entry["size"] >= threshold_bytes:
            warnings.append(("unknown", entry))

    critical.sort(key=lambda x: -x[1]["size"])
    warnings.sort(key=lambda x: -x[1]["size"])

    critical_mb = sum(e[1]["size"] for e in critical) / 1_000_000

    lines.append(f"  \U0001F4CA Total assets: {total_count} ({format_size(total_bytes)})")
    lines.append(f"  \U0001F534 Critical: {len(critical)} bloat items ({critical_mb:.0f}MB)")
    lines.append(f"  \U0001F7E1 Warning: {len(warnings)} items to review")
    lines.append("")

    if critical:
        lines.append(f"  \U0001F534 CRITICAL BLOCKERS ({len(critical)})")
        for typ, entry in critical[:30]:
            detail = ""
            if typ == "image":
                w = entry.get("width", "?")
                h = entry.get("height", "?")
                detail = f"\u2014 {w}x{h}px"
                if entry.get("oversized"):
                    detail += " (recommend <2048px)"
            elif typ == "audio":
                dur = entry.get("duration")
                detail = f"\u2014 {format_duration(dur)} long"
                if entry.get("too_long"):
                    detail += " (recommend <5 min)"
            elif typ == "mesh":
                v = entry.get("vertices", 0)
                detail = f"\u2014 {v} vertices"
                if entry.get("huge"):
                    detail += " (recommend <50K)"
            elif typ == "script":
                lc = entry.get("lines", 0)
                detail = f"\u2014 {lc} lines"
                if entry.get("too_long"):
                    detail += " (recommend <10K lines)"
            lines.append(f"     {entry['path']}    {format_size(entry['size'])}  {detail}")
        lines.append("")

    if warnings:
        lines.append(f"  \U0001F7E1 TO REVIEW ({len(warnings)})")
        for typ, entry in warnings[:20]:
            lines.append(f"     {entry['path']}    {format_size(entry['size'])}")
        lines.append("")

    if args.unused and unused is not None:
        lines.append(f"  \u26AA POTENTIALLY UNUSED ({len(unused)})")
        for entry in unused[:15]:
            lines.append(f"     {entry['path']}    {format_size(entry['size'])}  \u2014 not referenced in any script")
        lines.append("")

    if args.duplicates and duplicates is not None:
        pairs = sum(len(d["files"]) for d in duplicates) - len(duplicates)
        lines.append(f"  \U0001F5D1  DUPLICATES ({len(duplicates)} groups, {pairs} pairs, {format_size(dup_waste)} wasted)")
        for dg in duplicates[:10]:
            names = [f["path"] for f in dg["files"]]
            lines.append(f"     {' = '.join(names[:3])} (identical, {format_size(dg['files'][0]['size'])})")
        lines.append("")

    savings = critical_mb + (dup_waste / 1_000_000 if args.duplicates else 0)
    lines.append(f"  \U0001F4A1 Recommended savings: {savings:.0f}MB (fix all critical)")
    lines.append("")

    # Size distribution
    dist = {}
    dist[f"{IMG_EMOJI} Images"] = sum(e["size"] for e in cats["images"])
    dist[f"{AUDIO_EMOJI} Audio"] = sum(e["size"] for e in cats["audio"])
    dist[f"{ANIM_EMOJI} Animations"] = sum(e["size"] for e in cats["animations"])
    dist[f"{MESH_EMOJI} Meshes"] = sum(e["size"] for e in cats["meshes"])
    dist[f"{SCRIPT_EMOJI} Scripts"] = sum(e["size"] for e in cats["scripts"])
    dist[f"{UNKNOWN_EMOJI} Other"] = sum(e["size"] for e in cats["unknown"])

    lines.append("  \U0001F4CA Size distribution:")
    max_bar = 20
    main_culprit = max(dist, key=dist.get) if dist else None
    for label, bs in sorted(dist.items(), key=lambda x: -x[1]):
        pct = (bs / total_bytes * 100) if total_bytes else 0
        bar_len = int(pct / 100 * max_bar)
        bar = "\u2588" * max(1, bar_len)
        flag = " \u2190 INVESTIGATE" if label == main_culprit and pct > 50 else ""
        lines.append(f"     {bar} {label}: {format_size(bs)} ({pct:.0f}%){flag}")

    if xml_findings:
        lines.append("")
        lines.append("  \U0001F3D7  Roblox XML findings:")
        cc = xml_findings.get("class_counts", {})
        if cc:
            top_classes = sorted(cc.items(), key=lambda x: -x[1])[:10]
            lines.append("     Top instance classes:")
            for cls, cnt in top_classes:
                lines.append(f"       {cls}: {cnt}")
            huge_part_classes = ["Part", "WedgePart", "CornerWedgePart", "MeshPart"]
            part_count = sum(cc.get(c, 0) for c in huge_part_classes)
            if part_count > 2000:
                lines.append(f"     \u26A0  {part_count} Parts \u2014 consider reducing part count")
        script_sizes = xml_findings.get("script_sizes", [])
        if script_sizes:
            lines.append("     Large scripts in XML:")
            for ss in script_sizes[:10]:
                lines.append(f"       {ss['name']} ({ss['class']}): {ss['lines']} lines, {format_size(ss['size'])}")
        huge_ms = xml_findings.get("huge_meshes", [])
        if huge_ms:
            lines.append("     Meshes with high triangle counts:")
            for m in huge_ms[:10]:
                lines.append(f"       {m['name']} ({m['class']}): {m['triangles']} triangles")
        embeds = xml_findings.get("embedded_sizes", [])
        if embeds:
            total_embed = sum(e["size"] for e in embeds)
            lines.append(f"     Embedded assets: {len(embeds)} items ({format_size(total_embed)})")
        urls = xml_findings.get("content_urls", [])
        if urls:
            lines.append(f"     External asset references: {len(urls)}")

    return "\n".join(lines)


def json_report(args, scan_result, unused, duplicates, dup_waste, xml_findings=None):
    report = {
        "path": args.path,
        "threshold_mb": args.threshold,
        "total_assets": scan_result["total_count"],
        "total_bytes": scan_result["total_bytes"],
        "total_size": format_size(scan_result["total_bytes"]),
        "categories": {},
    }
    for cat_name, entries in scan_result["categories"].items():
        report["categories"][cat_name] = {
            "count": len(entries),
            "total_bytes": sum(e["size"] for e in entries),
            "total_size": format_size(sum(e["size"] for e in entries)),
            "items": entries,
        }
    if unused is not None:
        report["potentially_unused"] = [e for e in unused]
    if duplicates is not None:
        report["duplicates"] = {
            "groups": len(duplicates),
            "wasted_bytes": dup_waste,
            "wasted_size": format_size(dup_waste),
            "groups_detail": duplicates,
        }
    if xml_findings:
        report["xml_findings"] = xml_findings
    return json.dumps(report, indent=2, default=str)


# ── Main ────────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = parse_args()

    path = os.path.abspath(args.path)
    if not os.path.exists(path):
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    is_roblox_file = os.path.isfile(path) and os.path.splitext(path)[1].lower() in (
        ".rbxl", ".rbxlx", ".rbxm", ".rbxmx"
    )
    is_dir = os.path.isdir(path)

    if not is_roblox_file and not is_dir:
        print(
            f"Error: --path must be a .rbxl/.rbxlx/.rbxm/.rbxmx file or a directory",
            file=sys.stderr,
        )
        sys.exit(1)

    scan_result = None
    xml_findings = None
    unused = None
    duplicates = None
    dup_waste = 0

    if is_dir:
        threshold_bytes = int(args.threshold * 1_000_000)
        scan_result = scan_directory(path, threshold_bytes)
        if args.unused:
            unused = find_unused_assets(scan_result, path)
        if args.duplicates:
            duplicates, dup_waste = find_duplicates(path)
    elif is_roblox_file:
        xml_findings = parse_roblox_xml(path)
        scan_result = {
            "total_count": 0,
            "total_bytes": os.path.getsize(path),
            "categories": {k: [] for k in ("images", "audio", "animations", "meshes", "scripts", "unknown")},
            "script_paths": [],
        }

    if args.json:
        output = json_report(args, scan_result, unused, duplicates, dup_waste, xml_findings)
    else:
        output = format_report(args, scan_result, unused, duplicates, dup_waste, xml_findings)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
