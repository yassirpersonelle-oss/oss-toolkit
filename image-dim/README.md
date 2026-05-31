# image-dim

Fix CLS with one command.

## What is CLS?

Cumulative Layout Shift (CLS) is a Core Web Vital that measures unexpected layout shifts during page loading. When images lack explicit `width` and `height` attributes, browsers cannot reserve space for them until they load, causing content to jump around — a poor user experience that hurts SEO rankings.

## Usage

```bash
python image-dim.py --path src/
```

### Options

- `--path` : Directory to scan (default: current directory)
- `--extensions` : Comma-separated file extensions (default: `.astro,.md,.mdx,.html`)
- `--dry-run` : Show what would change without modifying files
- `--output`, `-o` : Write summary report to a file
- `--verbose` : Verbose output

### Examples

Scan current directory:
```bash
python image-dim.py
```

Dry-run to preview changes:
```bash
python image-dim.py --path src/ --dry-run --verbose
```

Write report to file:
```bash
python image-dim.py --path src/ -o report.txt
```

## Supported Formats

| Image Format | Detection Method |
|--------------|------------------|
| PNG          | IHDR chunk (bytes 16-23) |
| JPEG         | SOF0/SOF2 marker |
| GIF          | Header bytes 6-9 |
| WebP         | VP8/VP8L/VP8X chunk |
| SVG          | `width`/`height` attributes or `viewBox` |
| AVIF         | `ispe` box |

## How It Works

1. Scans matching files for `<img>` tags
2. Extracts the `src` attribute
3. Skips tags that already have `width` and `height`
4. For local files: reads the image header directly
5. For remote URLs: downloads to a temporary file and reads dimensions
6. Adds `width="X"` and `height="Y"` attributes to the tag
7. Modifies files in-place (unless `--dry-run`)

## Requirements

- Python 3.7+
- No external dependencies (stdlib only)