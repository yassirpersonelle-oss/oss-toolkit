#!/usr/bin/env python3
"""Roblox Animation Keyframe Compressor — reduce .rbxm animation size while preserving visual fidelity."""

import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

# ── Quaternion helpers (pure Python, no deps) ─────────────────────────────────

def quat_from_rotation_matrix(m):
    """Convert 3x3 rotation matrix to unit quaternion (w, x, y, z)."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        w = 0.25 * s
        x = (m[2][1] - m[1][2]) / s
        y = (m[0][2] - m[2][0]) / s
        z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        w = (m[2][1] - m[1][2]) / s
        x = 0.25 * s
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = 0.25 * s
        z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = 0.25 * s
    return (w, x, y, z)


def quat_angle_between(q1, q2):
    """Angular distance in radians between two unit quaternions."""
    dot = q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3]
    dot = max(-1.0, min(1.0, dot))
    return 2.0 * math.acos(abs(dot))


def quat_slerp(q1, q2, t):
    """Spherical linear interpolation between two unit quaternions."""
    dot = q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3]
    if dot < 0:
        q2 = (-q2[0], -q2[1], -q2[2], -q2[3])
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        result = tuple(q1[i] + t * (q2[i] - q1[i]) for i in range(4))
        mag = math.sqrt(sum(v * v for v in result))
        return tuple(v / mag for v in result)
    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    s0 = math.sin((1 - t) * theta_0) / sin_theta_0
    s1 = math.sin(t * theta_0) / sin_theta_0
    return tuple(s0 * q1[i] + s1 * q2[i] for i in range(4))

# ── CFrame parsing ────────────────────────────────────────────────────────────

def parse_cframe(cframe_elem):
    """Parse CoordinateFrame element into position (x,y,z) and 3x3 rotation matrix."""
    text = (cframe_elem.text or "").strip()
    values = []
    if text:
        values = [float(v) for v in text.split()]
    elif len(cframe_elem) > 0:
        values = [float(cframe_elem[0].text or "0")]
        for child in cframe_elem[1:]:
            values.append(float(child.text or "0"))
    else:
        return (0, 0, 0), [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    if len(values) >= 12:
        pos = (values[3], values[7], values[11])
        rot = [
            [values[0], values[1], values[2]],
            [values[4], values[5], values[6]],
            [values[8], values[9], values[10]],
        ]
    elif len(values) >= 7:
        pos = (values[0], values[1], values[2])
        qx, qy, qz, qw = values[3], values[4], values[5], values[6]
        rot = quat_to_matrix((qw, qx, qy, qz))
    elif len(values) >= 3:
        pos = (values[0], values[1], values[2])
        rot = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    else:
        pos = (0, 0, 0)
        rot = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    return pos, rot


def quat_to_matrix(q):
    """Convert quaternion (w,x,y,z) to 3x3 rotation matrix."""
    w, x, y, z = q
    return [
        [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * w * z, 2 * x * z + 2 * w * y],
        [2 * x * y + 2 * w * z, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * w * x],
        [2 * x * z - 2 * w * y, 2 * y * z + 2 * w * x, 1 - 2 * x * x - 2 * y * y],
    ]


def position_distance(p1, p2):
    """Euclidean distance between two 3D positions."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)


def lerp(a, b, t):
    """Linear interpolation between two scalars or tuples."""
    if isinstance(a, (int, float)):
        return a + (b - a) * t
    return tuple(ai + (bi - ai) * t for ai, bi in zip(a, b))


def easing_names():
    """Known Roblox easing direction/style enumeration values."""
    return {
        "0": "Linear",
        "1": "Constant",
        "2": "Elastic",
        "3": "Cubic",
        "4": "Bounce",
    }

# ── XML parsing ───────────────────────────────────────────────────────────────

ROBLOX_NS = "http://www.roblox.com/roblox.xsd"

def _ns(tag):
    return f"{{{ROBLOX_NS}}}{tag}"


def find_children(parent, class_name):
    """Find all child Item elements with a given class."""
    found = []
    for item in parent.findall(f".//{_ns('Item')}"):
        if item.get("class") == class_name:
            found.append(item)
    return found


def find_direct_children(parent, class_name=None):
    """Find direct-child Item elements, optionally filtered by class."""
    items = []
    for item in parent:
        stripped = item.tag.split("}")[-1] if "}" in item.tag else item.tag
        if stripped == "Item":
            if class_name is None or item.get("class") == class_name:
                items.append(item)
    return items


def get_property_value(prop_elem):
    """Extract the text content of a property element."""
    if prop_elem is None:
        return None
    text = (prop_elem.text or "").strip()
    if text:
        return text
    for child in prop_elem:
        text = (child.text or "").strip()
        if text:
            return text
    return ""


def parse_pose(pose_elem):
    """Parse a Pose element into (bone_name, position, rotation_quat, easing_direction, easing_style)."""
    props = {}
    for prop in pose_elem:
        stripped = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
        name = prop.get("name", "")
        props[name] = prop

    bone_name = get_property_value(props.get("Name", None))
    if not bone_name:
        return None

    cframe = props.get("CFrame", None)
    if cframe is not None:
        pos, rot_matrix = parse_cframe(cframe)
    else:
        pos = (0, 0, 0)
        rot_matrix = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    rot_quat = quat_from_rotation_matrix(rot_matrix)
    
    easing_direction = get_property_value(props.get("EasingDirection", None)) or "0"
    easing_style = get_property_value(props.get("EasingStyle", None)) or "0"
    weight = float(get_property_value(props.get("Weight", None)) or "1.0")

    return {
        "bone": bone_name,
        "position": pos,
        "rotation": rot_quat,
        "easing_direction": easing_direction,
        "easing_style": easing_style,
        "weight": weight,
    }


def parse_animation(filepath):
    """Parse a .rbxm animation file into a structured representation."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    kfs_items = root.findall(f".//{_ns('Item')}")
    keyframe_sequence = None
    for item in kfs_items:
        if item.get("class") == "KeyframeSequence":
            keyframe_sequence = item
            break

    if keyframe_sequence is None:
        raise ValueError(f"No KeyframeSequence found in {filepath}")

    keyframes_raw = find_direct_children(keyframe_sequence, "Keyframe")
    if not keyframes_raw:
        keyframes_raw = []
        for item in root.iter():
            if item.get("class") == "Keyframe":
                keyframes_raw.append(item)

    keyframes = []
    for kf in keyframes_raw:
        time = 0.0
        poses = []
        for prop in kf:
            stripped = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
            if prop.get("name") == "Time" and stripped != "Item":
                time = float(get_property_value(prop))
            if stripped == "Item" and prop.get("class") == "Pose":
                pose = parse_pose(prop)
                if pose:
                    poses.append(pose)

        if poses:
            keyframes.append({"time": time, "poses": poses})

    keyframes.sort(key=lambda k: k["time"])

    all_bones = set()
    for kf in keyframes:
        for pose in kf["poses"]:
            all_bones.add(pose["bone"])

    duration = keyframes[-1]["time"] if keyframes else 0

    return {
        "filepath": filepath,
        "tree": tree,
        "root": root,
        "keyframe_sequence": keyframe_sequence,
        "keyframes": keyframes,
        "bones": sorted(all_bones),
        "duration": duration,
    }

# ── Compression passes ────────────────────────────────────────────────────────

def pose_for_bone(keyframe, bone_name):
    """Get the pose for a specific bone in a keyframe, or None if not present."""
    for pose in keyframe["poses"]:
        if pose["bone"] == bone_name:
            return pose
    return None


def detect_static_bones(anim, tol_angle_deg, tol_position):
    """Find bones that are static (never move) across the entire animation."""
    static_bones = set()
    tol_angle = math.radians(tol_angle_deg)

    for bone in anim["bones"]:
        poses_data = []
        for kf in anim["keyframes"]:
            pose = pose_for_bone(kf, bone)
            if pose:
                poses_data.append((kf, pose))

        if len(poses_data) < 2:
            continue

        first_pose = poses_data[0][1]
        is_static = True
        for kf, pose in poses_data[1:]:
            ang_diff = quat_angle_between(first_pose["rotation"], pose["rotation"])
            pos_diff = position_distance(first_pose["position"], pose["position"])
            if ang_diff > tol_angle or pos_diff > tol_position:
                is_static = False
                break

        if is_static:
            static_bones.add(bone)

    return static_bones


def compress_static_bones(anim, static_bones):
    """Remove all but the first keyframe for static bones."""
    removed = 0
    for bone in static_bones:
        counts = 0
        kept_first = False
        for kf in anim["keyframes"]:
            new_poses = []
            for pose in kf["poses"]:
                if pose["bone"] == bone:
                    if not kept_first:
                        new_poses.append(pose)
                        kept_first = True
                    else:
                        removed += 1
                        continue
                else:
                    new_poses.append(pose)
            kf["poses"] = new_poses
            if kept_first and len(new_poses) == 0:
                pass
    return removed


def compress_redundant_keyframes(anim, tol_angle_deg, tol_position, target_ratio):
    """Remove keyframes where the pose change is within tolerance of the previous frame."""
    tol_angle = math.radians(tol_angle_deg)
    removed_indices = set()
    per_bone_removed = {b: 0 for b in anim["bones"]}

    for bone in anim["bones"]:
        kf_indices = []
        for i, kf in enumerate(anim["keyframes"]):
            if pose_for_bone(kf, bone):
                kf_indices.append(i)

        if len(kf_indices) < 3:
            continue

        for j in range(1, len(kf_indices) - 1):
            i_prev = kf_indices[j - 1]
            i_curr = kf_indices[j]
            i_next = kf_indices[j + 1]

            p_prev = pose_for_bone(anim["keyframes"][i_prev], bone)
            p_curr = pose_for_bone(anim["keyframes"][i_curr], bone)
            p_next = pose_for_bone(anim["keyframes"][i_next], bone)

            if not (p_prev and p_curr and p_next):
                continue

            ang_prev_to_curr = quat_angle_between(p_prev["rotation"], p_curr["rotation"])
            pos_prev_to_curr = position_distance(p_prev["position"], p_curr["position"])

            if ang_prev_to_curr <= tol_angle and pos_prev_to_curr <= tol_position:
                all_still = all(
                    ang_prev_to_curr <= tol_angle and pos_prev_to_curr <= tol_position
                )
                if all_still:
                    removed_indices.add(i_curr)
                    per_bone_removed[bone] += 1

    return removed_indices, per_bone_removed


def compress_linear_sequences(anim, tol_angle_deg, tol_position):
    """Detect and remove keyframes that are linearly interpolated from neighbors."""
    tol_angle = math.radians(tol_angle_deg)
    removed_indices = set()
    per_bone_removed = {b: 0 for b in anim["bones"]}

    for bone in anim["bones"]:
        kf_indices = []
        for i, kf in enumerate(anim["keyframes"]):
            if pose_for_bone(kf, bone):
                kf_indices.append(i)

        if len(kf_indices) < 3:
            continue

        for j in range(1, len(kf_indices) - 1):
            i_prev = kf_indices[j - 1]
            i_curr = kf_indices[j]
            i_next = kf_indices[j + 1]

            kf_prev = anim["keyframes"][i_prev]
            kf_curr = anim["keyframes"][i_curr]
            kf_next = anim["keyframes"][i_next]

            p_prev = pose_for_bone(kf_prev, bone)
            p_curr = pose_for_bone(kf_curr, bone)
            p_next = pose_for_bone(kf_next, bone)

            if not (p_prev and p_curr and p_next):
                continue

            t_range = kf_next["time"] - kf_prev["time"]
            if t_range < 1e-6:
                continue
            t = (kf_curr["time"] - kf_prev["time"]) / t_range

            interp_pos = lerp(p_prev["position"], p_next["position"], t)
            interp_rot = quat_slerp(p_prev["rotation"], p_next["rotation"], t)

            pos_error = position_distance(p_curr["position"], interp_pos)
            ang_error = quat_angle_between(p_curr["rotation"], interp_rot)

            if ang_error <= tol_angle and pos_error <= tol_position:
                removed_indices.add(i_curr)
                per_bone_removed[bone] += 1

    return removed_indices, per_bone_removed


def compress_easing(anim):
    """Simplify InOut easing to single direction if curve is near-linear."""
    changes = 0
    for kf in anim["keyframes"]:
        for pose in kf["poses"]:
            ed = pose.get("easing_direction", "0")
            es = pose.get("easing_style", "0")
            if ed == "2" and es in ("0", "1"):
                pose["easing_direction"] = "0"
                changes += 1
    return changes


def compress_empty_keyframes(anim):
    """Remove keyframes that have no poses left."""
    to_keep = []
    removed = 0
    for kf in anim["keyframes"]:
        if len(kf["poses"]) > 0:
            to_keep.append(kf)
        else:
            removed += 1
    anim["keyframes"] = to_keep
    return removed


# ── Output helper ─────────────────────────────────────────────────────────────

def count_total_keyframes(keyframes):
    return sum(len(kf["poses"]) for kf in keyframes)


def clone_animation(anim):
    """Deep copy the animation structure for dry-run comparison."""
    return deepcopy(anim)


# ── XML writing ───────────────────────────────────────────────────────────────

def pose_to_xml_element(pose):
    """Convert a pose dict back to an XML Item element."""
    xf = pose["rotation"]
    pos = pose["position"]
    w, x, y, z = xf

    m = quat_to_matrix((w, x, y, z))
    cframe_values = (
        f"{m[0][0]} {m[0][1]} {m[0][2]} "
        f"{pos[0]} {m[1][0]} {m[1][1]} {m[1][2]} "
        f"{pos[1]} {m[2][0]} {m[2][1]} {m[2][2]} "
        f"{pos[2]}"
    )

    item = ET.Element(_ns("Item"), {"class": "Pose"})
    props = ET.SubElement(item, _ns("Properties"))

    name_el = ET.SubElement(props, _ns("string"), {"name": "Name"})
    name_el.text = pose["bone"]

    cf_el = ET.SubElement(props, _ns("CoordinateFrame"), {"name": "CFrame"})
    cf_el.text = cframe_values

    ed_el = ET.SubElement(props, _ns("int"), {"name": "EasingDirection"})
    ed_el.text = pose.get("easing_direction", "0")

    es_el = ET.SubElement(props, _ns("int"), {"name": "EasingStyle"})
    es_el.text = pose.get("easing_style", "0")

    weight_el = ET.SubElement(props, _ns("float"), {"name": "Weight"})
    weight_el.text = str(pose.get("weight", 1.0))

    return item


def write_compressed_animation(anim, output_path):
    """Write the compressed animation to a new .rbxm file."""
    kfs_elem = anim["keyframe_sequence"]
    existing_children = list(find_direct_children(kfs_elem, "Keyframe"))
    for child in existing_children:
        kfs_elem.remove(child)

    for kf in anim["keyframes"]:
        kf_item = ET.SubElement(kfs_elem, _ns("Item"), {"class": "Keyframe"})
        props = ET.SubElement(kf_item, _ns("Properties"))
        time_el = ET.SubElement(props, _ns("double"), {"name": "Time"})
        time_el.text = str(kf["time"])
        for pose in kf["poses"]:
            pose_el = pose_to_xml_element(pose)
            kf_item.append(pose_el)

    tree = anim["tree"]
    xml_str = ET.tostring(tree.getroot(), encoding="unicode")

    declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
    if not xml_str.startswith("<?xml"):
        xml_str = declaration + xml_str

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)


# ── Statistics / reporting ────────────────────────────────────────────────────

def compute_per_bone_stats(original_anim, compressed_anim):
    """Compare original vs compressed at per-bone level."""
    orig_counts = {b: 0 for b in original_anim["bones"]}
    comp_counts = {b: 0 for b in original_anim["bones"]}

    for kf in original_anim["keyframes"]:
        for pose in kf["poses"]:
            orig_counts[pose["bone"]] = orig_counts.get(pose["bone"], 0) + 1

    for kf in compressed_anim["keyframes"]:
        for pose in kf["poses"]:
            comp_counts[pose["bone"]] = comp_counts.get(pose["bone"], 0) + 1

    stats = {}
    for bone in original_anim["bones"]:
        o = orig_counts.get(bone, 0)
        c = comp_counts.get(bone, 0)
        pct = (1 - c / o) * 100 if o > 0 else 0
        stats[bone] = {"original": o, "compressed": c, "reduction": pct}
    return stats


def max_deviation(original_anim, compressed_anim, tol_angle_deg):
    """Estimate max angular deviation by replaying both animation curves."""
    max_ang = 0.0
    max_pos = 0.0
    for bone in original_anim["bones"]:
        orig_frames = []
        comp_frames = []
        for kf in original_anim["keyframes"]:
            p = pose_for_bone(kf, bone)
            if p:
                orig_frames.append((kf["time"], p))
        for kf in compressed_anim["keyframes"]:
            p = pose_for_bone(kf, bone)
            if p:
                comp_frames.append((kf["time"], p))

        if len(orig_frames) >= 2 and len(comp_frames) >= 2:
            for t in [kf["time"] for kf in original_anim["keyframes"]]:
                orig_pose = _interpolate_pose_at(orig_frames, t)
                comp_pose = _interpolate_pose_at(comp_frames, t)
                if orig_pose and comp_pose:
                    ang = quat_angle_between(orig_pose["rotation"], comp_pose["rotation"])
                    pos = position_distance(orig_pose["position"], comp_pose["position"])
                    max_ang = max(max_ang, ang)
                    max_pos = max(max_pos, pos)

    return math.degrees(max_ang), max_pos


def _interpolate_pose_at(frames, time):
    """Sample a pose at a given time from keyframed data."""
    if not frames:
        return None
    if time <= frames[0][0]:
        return frames[0][1]
    if time >= frames[-1][0]:
        return frames[-1][1]
    for i in range(len(frames) - 1):
        t0, p0 = frames[i]
        t1, p1 = frames[i + 1]
        if t0 <= time <= t1:
            if t1 - t0 < 1e-9:
                return p0
            alpha = (time - t0) / (t1 - t0)
            return {
                "position": lerp(p0["position"], p1["position"], alpha),
                "rotation": quat_slerp(p0["rotation"], p1["rotation"], alpha),
            }
    return frames[-1][1]


def classify_bone_behavior(original_anim, bone, static_bones):
    """Give a human-readable tag for a bone's movement pattern."""
    if bone in static_bones:
        return "static"
    poses = []
    for kf in original_anim["keyframes"]:
        p = pose_for_bone(kf, bone)
        if p:
            poses.append(p)
    if len(poses) < 2:
        return "static"
    first = poses[0]
    total_rot = 0
    total_pos = 0
    for p in poses:
        total_rot += quat_angle_between(first["rotation"], p["rotation"])
        total_pos += position_distance(first["position"], p["position"])
    if total_rot < math.radians(2) and total_pos < 0.02 and len(poses) > 5:
        return "mostly static"
    if total_rot > math.radians(90) or total_pos > 2:
        return "complex movement"
    if total_rot > math.radians(20) or total_pos > 0.5:
        return "moderate movement"
    return "limited movement"


# ── Main pipeline ─────────────────────────────────────────────────────────────

def compress_animation(anim, args):
    """Run the full compression pipeline, returning compressed anim and stats."""
    orig_total = count_total_keyframes(anim["keyframes"])

    static_bones = detect_static_bones(anim, args.tolerance, args.tolerance_position)
    static_removed = compress_static_bones(anim, static_bones)
    empty_removed_1 = compress_empty_keyframes(anim)

    redundant_indices, redundant_per_bone = compress_redundant_keyframes(
        anim, args.tolerance, args.tolerance_position, args.target_ratio
    )

    linear_indices, linear_per_bone = compress_linear_sequences(
        anim, args.tolerance, args.tolerance_position
    )

    all_removed = redundant_indices | linear_indices
    kept_keyframes = [kf for i, kf in enumerate(anim["keyframes"]) if i not in all_removed]
    anim["keyframes"] = kept_keyframes

    empty_removed_2 = compress_empty_keyframes(anim)
    easing_changes = compress_easing(anim)

    comp_total = count_total_keyframes(anim["keyframes"])

    per_bone_combined = {b: 0 for b in anim["bones"]}
    for b in anim["bones"]:
        per_bone_combined[b] = redundant_per_bone.get(b, 0) + linear_per_bone.get(b, 0)

    return {
        "static_bones": static_bones,
        "static_removed": static_removed,
        "redundant_removed": len(redundant_indices),
        "linear_removed": len(linear_indices),
        "total_removed_keyframes": len(all_removed),
        "empty_keyframes_removed": empty_removed_1 + empty_removed_2,
        "easing_changes": easing_changes,
        "original_total": orig_total,
        "compressed_total": comp_total,
        "per_bone_combined": per_bone_combined,
    }


def process_file(filepath, args, json_report):
    """Process a single .rbxm file."""
    basename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(basename)[0]

    try:
        anim = parse_animation(filepath)
    except Exception as e:
        print(f"  ⚠️  Failed to parse {basename}: {e}")
        if json_report is not None:
            json_report["errors"].append({"file": filepath, "error": str(e)})
        return

    original_total = count_total_keyframes(anim["keyframes"])
    original_anim = clone_animation(anim)

    stats = compress_animation(anim, args)
    compressed_total = stats["compressed_total"]
    reduction_pct = (1 - compressed_total / original_total * 100) if original_total > 0 else 0
    reduction_ratio = (compressed_total / original_total) if original_total > 0 else 1.0

    print(f"🎬 Animation Compressor — {basename}")
    print("━" * 55)
    print(f"  📊 Original: {original_total} keyframes, {len(anim['bones'])} bones, {anim['duration']:.1f} seconds")
    print(f"  🗜️  Compressed: {compressed_total} keyframes ({reduction_pct:.1f}% reduction)")
    print()

    if args.verbose:
        per_bone = compute_per_bone_stats(original_anim, anim)
        behavior_tags = {b: classify_bone_behavior(original_anim, b, stats["static_bones"]) for b in anim["bones"]}
        print("  🦴 Per-bone savings:")
        for bone in anim["bones"]:
            s = per_bone[bone]
            tag = behavior_tags.get(bone, "")
            tag_str = f" — {tag}" if tag else ""
            if s["original"] > s["compressed"]:
                print(f"     {bone}:  {s['original']}→{s['compressed']} ({s['reduction']:.0f}%){tag_str}")
            else:
                print(f"     {bone}:  {s['original']}→{s['compressed']} (0%){tag_str}")
        print()

    max_ang_dev, max_pos_dev = max_deviation(original_anim, anim, args.tolerance)
    fidelity = max(0.0, 100.0 - max_ang_dev * 0.5)
    print(f"  ✅ Visual fidelity: {fidelity:.1f}% preserved (max deviation {max_ang_dev:.2f}°)")
    print()

    if not args.dry_run:
        out_dir = args.output
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{name_no_ext}_compressed.rbxm")
        write_compressed_animation(anim, out_path)
        orig_size = os.path.getsize(filepath)
        comp_size = os.path.getsize(out_path)
        print(f"  📁 Saved: {os.path.basename(out_path)} ({comp_size//1024}KB vs {orig_size//1024}KB original)")
    else:
        print(f"  🔍 Dry-run: {stats['total_removed_keyframes']} keyframes removable, {stats['static_removed']} static bone entries removed")

    print()

    if json_report is not None:
        json_report["files"].append({
            "file": filepath,
            "original_keyframes": original_total,
            "compressed_keyframes": compressed_total,
            "reduction_percent": round(reduction_pct, 1),
            "reduction_ratio": round(reduction_ratio, 3),
            "bones": len(anim["bones"]),
            "duration": anim["duration"],
            "static_bones_removed": len(stats["static_bones"]),
            "redundant_keyframes_removed": stats["redundant_removed"],
            "linear_keyframes_removed": stats["linear_removed"],
            "max_angle_deviation": round(max_ang_dev, 3),
            "max_position_deviation": round(max_pos_dev, 4),
            "per_bone": {
                b: {
                    "original": compute_per_bone_stats(original_anim, anim)[b]["original"],
                    "compressed": compute_per_bone_stats(original_anim, anim)[b]["compressed"],
                    "reduction": round(compute_per_bone_stats(original_anim, anim)[b]["reduction"], 1),
                }
                for b in anim["bones"]
            } if args.verbose else {},
        })


def collect_rbxm_files(path):
    """Collect .rbxm files from a file path or directory."""
    if os.path.isfile(path):
        if path.lower().endswith(".rbxm"):
            return [path]
        return []
    files = []
    for root, dirs, filenames in os.walk(path):
        for fn in filenames:
            if fn.lower().endswith(".rbxm"):
                files.append(os.path.join(root, fn))
    return sorted(files)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Roblox Animation Keyframe Compressor — reduce .rbxm animation size",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s -i idle.rbxm\n"
            "  %(prog)s -i animations/ -o compressed/ -t 1.5\n"
            "  %(prog)s -i anim.rbxm --dry-run --verbose\n"
            "  %(prog)s -i anim.rbxm --json report.json\n"
        ),
    )
    parser.add_argument("-i", "--input", required=True, help="Input .rbxm file or directory of animations")
    parser.add_argument("-o", "--output", default="compressed", help="Output directory (default: compressed/)")
    parser.add_argument("-t", "--tolerance", type=float, default=1.0, help="Angle tolerance in degrees (default: 1.0)")
    parser.add_argument("--tolerance-position", type=float, default=0.01, help="Position tolerance in studs (default: 0.01)")
    parser.add_argument("--json", type=str, default=None, help="Output JSON report to file")
    parser.add_argument("--verbose", action="store_true", help="Show detailed per-bone statistics")
    parser.add_argument("--dry-run", action="store_true", help="Preview compression without writing files")
    parser.add_argument("--target-ratio", type=float, default=0.5, help="Compression target ratio (default: 0.5 = 50%% reduction)")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    files = collect_rbxm_files(args.input)
    if not files:
        print(f"❌ No .rbxm files found in: {args.input}")
        sys.exit(1)

    json_report = None
    if args.json:
        json_report = {"files": [], "errors": [], "summary": {}}

    for filepath in files:
        process_file(filepath, args, json_report)

    if json_report and args.json:
        total_orig = sum(f["original_keyframes"] for f in json_report["files"])
        total_comp = sum(f["compressed_keyframes"] for f in json_report["files"])
        json_report["summary"] = {
            "total_files": len(json_report["files"]),
            "total_original_keyframes": total_orig,
            "total_compressed_keyframes": total_comp,
            "overall_reduction_percent": round((1 - total_comp / total_orig) * 100, 1) if total_orig > 0 else 0,
            "errors": len(json_report["errors"]),
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(json_report, f, indent=2, ensure_ascii=False)
        print(f"📋 JSON report saved to: {args.json}")


if __name__ == "__main__":
    main()
