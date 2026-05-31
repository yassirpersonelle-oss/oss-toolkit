#!/usr/bin/env python3
"""
image-dim: Fix CLS by adding missing width/height attributes to <img> tags.

Scans Astro/MD/MDX/HTML files for <img> tags, downloads images,
reads real dimensions, and backfills missing width/height attributes.
"""

import argparse
import io
import os
import re
import struct
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple, Optional

# Regex to find <img ...> tags (non-greedy)
IMG_TAG_RE = re.compile(r'<img\b[^>]*?>', re.IGNORECASE | re.DOTALL)
# Regex to extract src attribute
SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)
# Regex to check width/height attributes
WIDTH_RE = re.compile(r'\bwidth\s*=', re.IGNORECASE)
HEIGHT_RE = re.compile(r'\bheight\s*=', re.IGNORECASE)

# Supported file extensions
DEFAULT_EXTENSIONS = {'.astro', '.md', '.mdx', '.html'}


def get_png_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Read PNG dimensions from IHDR chunk (bytes 16-23)."""
    if len(data) < 24:
        return None
    # PNG signature: 137 80 78 71 13 10 26 10
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    width = struct.unpack('>I', data[16:20])[0]
    height = struct.unpack('>I', data[20:24])[0]
    return width, height


def get_jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Parse JPEG SOF0/SOF2 marker for dimensions."""
    i = 0
    length = len(data)
    while i < length - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # SOF markers
        if marker in (0xC0, 0xC1, 0xC2):
            if i + 9 < length:
                height = struct.unpack('>H', data[i + 5:i + 7])[0]
                width = struct.unpack('>H', data[i + 7:i + 9])[0]
                return width, height
            return None
        # Skip variable-length markers
        if marker == 0xD9 or marker == 0xDA:
            break
        if 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 3 < length:
            seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
            i += 2 + seg_len
        else:
            break
    return None


def get_gif_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Read GIF width/height at bytes 6-9."""
    if len(data) < 10:
        return None
    # GIF87a or GIF89a
    if data[:3] != b'GIF':
        return None
    width = struct.unpack('<H', data[6:8])[0]
    height = struct.unpack('<H', data[8:10])[0]
    return width, height


def get_webp_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Parse WebP VP8/VP8L/VP8X chunk for dimensions."""
    if len(data) < 30:
        return None
    # RIFF....WEBP
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return None
    chunk = data[12:16]
    if chunk == b'VP8 ':
        # Simple VP8
        if len(data) < 30:
            return None
        width = struct.unpack('<H', data[26:28])[0] & 0x3FFF
        height = struct.unpack('<H', data[28:30])[0] & 0x3FFF
        return width, height
    elif chunk == b'VP8L':
        # Lossless VP8L
        if len(data) < 25:
            return None
        bits = struct.unpack('<I', data[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    elif chunk == b'VP8X':
        # Extended VP8X
        if len(data) < 30:
            return None
        width = struct.unpack('<I', data[24:28])[0] + 1
        height = struct.unpack('<I', data[27:31])[0] + 1
        return width, height
    return None


def get_svg_dimensions_from_data(data: bytes) -> Optional[Tuple[int, int]]:
    """Try to extract width/height or viewBox from SVG content."""
    try:
        text = data.decode('utf-8', errors='ignore')
    except Exception:
        return None
    # Look for width/height attributes
    width_match = re.search(r'width=["\']([^"\']+)["\']', text, re.IGNORECASE)
    height_match = re.search(r'height=["\']([^"\']+)["\']', text, re.IGNORECASE)
    if width_match and height_match:
        try:
            w = float(width_match.group(1).replace('px', '').replace('pt', '').replace('em', ''))
            h = float(height_match.group(1).replace('px', '').replace('pt', '').replace('em', ''))
            return int(w), int(h)
        except ValueError:
            pass
    # viewBox
    vb_match = re.search(r'viewBox=["\']([^"\']+)["\']', text, re.IGNORECASE)
    if vb_match:
        parts = vb_match.group(1).split()
        if len(parts) == 4:
            try:
                x, y, w, h = map(float, parts)
                return int(w), int(h)
            except ValueError:
                pass
    return None


def get_avif_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Parse AVIF 'ispe' box for dimensions."""
    # Simple parser: look for 'ispe' box in ftyp/moov structures
    # This is a simplified approach; full AVIF parsing is complex
    i = 0
    length = len(data)
    while i < length - 8:
        box_len = struct.unpack('>I', data[i:i+4])[0]
        box_type = data[i+4:i+8]
        if box_len < 8:
            break
        if box_type == b'ispe' and i + 20 <= length:
            # ispe box: width (4 bytes) and height (4 bytes) after version
            width = struct.unpack('>I', data[i+12:i+16])[0]
            height = struct.unpack('>I', data[i+16:i+20])[0]
            return width, height
        i += box_len
    return None


def get_image_dimensions_from_data(data: bytes, ext: str) -> Optional[Tuple[int, int]]:
    """Get dimensions from raw image data based on extension."""
    ext = ext.lower()
    if ext == '.png':
        return get_png_dimensions(data)
    elif ext in ('.jpg', '.jpeg'):
        return get_jpeg_dimensions(data)
    elif ext == '.gif':
        return get_gif_dimensions(data)
    elif ext == '.webp':
        return get_webp_dimensions(data)
    elif ext in ('.svg',):
        return get_svg_dimensions_from_data(data)
    elif ext == '.avif':
        return get_avif_dimensions(data)
    return None


def get_image_dimensions_from_file(file_path: str, ext: str) -> Optional[Tuple[int, int]]:
    """Read file and get dimensions."""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        return get_image_dimensions_from_data(data, ext)
    except Exception:
        return None


def get_image_dimensions_from_url(url: str, ext: str) -> Optional[Tuple[int, int]]:
    """Download image from URL and get dimensions."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = response.read()
        return get_image_dimensions_from_data(data, ext)
    except Exception:
        return None


def resolve_image_path(src: str, base_dir: str) -> Optional[str]:
    """Resolve relative image path to absolute path."""
    if src.startswith(('http://', 'https://')):
        return None  # Remote URL
    # Remove any query params or fragments
    clean = src.split('?')[0].split('#')[0]
    # If starts with /, treat as absolute from project root?
    # For simplicity, assume relative to base_dir
    candidate = os.path.join(base_dir, clean)
    if os.path.isfile(candidate):
        return candidate
    return None


def get_extension_for_image(src: str) -> str:
    """Extract file extension from src URL/path."""
    clean = src.split('?')[0].split('#')[0]
    _, ext = os.path.splitext(clean)
    return ext.lower() if ext else '.jpg'  # default to jpg if no extension


def scan_file(file_path: str, dry_run: bool, verbose: bool) -> Tuple[int, int, int]:
    """
    Scan a single file for <img> tags and backfill missing dimensions.
    Returns (images_found, backfilled, skipped).
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        if verbose:
            print(f"  Error reading {file_path}: {e}", file=sys.stderr)
        return 0, 0, 0

    matches = list(IMG_TAG_RE.finditer(content))
    if not matches:
        return 0, 0, 0

    base_dir = os.path.dirname(file_path)
    images_found = 0
    backfilled = 0
    skipped = 0
    new_content = content

    for match in matches:
        tag = match.group(0)
        images_found += 1

        # Skip if already has width and height
        if WIDTH_RE.search(tag) and HEIGHT_RE.search(tag):
            skipped += 1
            if verbose:
                print(f"  Skipping tag with dimensions: {tag[:80]}...")
            continue

        # Extract src
        src_match = SRC_RE.search(tag)
        if not src_match:
            skipped += 1
            if verbose:
                print(f"  No src found in tag: {tag[:80]}...")
            continue

        src = src_match.group(1)
        ext = get_extension_for_image(src)
        dimensions = None

        # Try local file
        local_path = resolve_image_path(src, base_dir)
        if local_path:
            if verbose:
                print(f"  Reading local file: {local_path}")
            dimensions = get_image_dimensions_from_file(local_path, ext)
        else:
            # Remote URL
            if src.startswith(('http://', 'https://')):
                if verbose:
                    print(f"  Downloading remote URL: {src}")
                dimensions = get_image_dimensions_from_url(src, ext)

        if dimensions is None:
            skipped += 1
            if verbose:
                print(f"  Could not determine dimensions for: {src}")
            continue

        width, height = dimensions
        if width <= 0 or height <= 0:
            skipped += 1
            if verbose:
                print(f"  Invalid dimensions for: {src}")
            continue

        # Build new tag with width and height
        new_tag = tag
        if not WIDTH_RE.search(new_tag):
            # Insert width before closing > or after src
            new_tag = re.sub(r'(?=\/?>)', f' width="{width}"', new_tag, count=1)
        if not HEIGHT_RE.search(new_tag):
            new_tag = re.sub(r'(?=\/?>)', f' height="{height}"', new_tag, count=1)

        if not dry_run:
            new_content = new_content.replace(tag, new_tag, 1)

        backfilled += 1
        if verbose:
            print(f"  Backfilled {src}: {width}x{height}")

    if not dry_run and backfilled > 0:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception as e:
            print(f"Error writing {file_path}: {e}", file=sys.stderr)

    return images_found, backfilled, skipped


def main():
    parser = argparse.ArgumentParser(
        description='Fix CLS by adding missing width/height to <img> tags.'
    )
    parser.add_argument(
        '--path', default='.', help='Directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--extensions', default=','.join(DEFAULT_EXTENSIONS),
        help='Comma-separated file extensions (default: .astro,.md,.mdx,.html)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would change without modifying files'
    )
    parser.add_argument(
        '--output', '-o', help='Write report to file'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Verbose output'
    )
    args = parser.parse_args()

    scan_dir = os.path.abspath(args.path)
    if not os.path.isdir(scan_dir):
        print(f"Error: {scan_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    extensions = set()
    for ext in args.extensions.split(','):
        ext = ext.strip()
        if ext and not ext.startswith('.'):
            ext = '.' + ext
        extensions.add(ext.lower())

    if args.verbose:
        print(f"Scanning {scan_dir} for extensions: {', '.join(sorted(extensions))}")
        if args.dry_run:
            print("Dry-run mode: no files will be modified")

    # Collect files
    files_to_scan = []
    for root, dirs, files in os.walk(scan_dir):
        for fname in files:
            _, ext = os.path.splitext(fname)
            if ext.lower() in extensions:
                files_to_scan.append(os.path.join(root, fname))

    total_files = len(files_to_scan)
    total_images = 0
    total_backfilled = 0
    total_skipped = 0

    for fpath in files_to_scan:
        if args.verbose:
            print(f"Scanning {fpath}...")
        imgs, back, skip = scan_file(fpath, args.dry_run, args.verbose)
        total_images += imgs
        total_backfilled += back
        total_skipped += skip

    summary = (
        f"Scanned {total_files} files, found {total_images} images, "
        f"backfilled {total_backfilled} missing dimensions, "
        f"skipped {total_skipped} (already set)"
    )
    print(summary)

    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(summary + '\n')
            if args.verbose:
                print(f"Report written to {args.output}")
        except Exception as e:
            print(f"Error writing report: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()