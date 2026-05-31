# UI Scale Optimizer

**Make your Roblox UI work on every device.**

A Python CLI that scans Luau scripts for `UDim2` patterns, flags hardcoded pixel values, and helps you convert them to relative scaling so your UI looks great on phones, tablets, and PCs.

## Why hardcoded pixels break mobile

```
UDim2.new(0, 800, 0, 600)   -- 800x600px sized frame
```

This frame is 800 pixels wide on **every** device:

| Device | Screen width | Frame behavior |
|--------|-------------|----------------|
| PC (1080p) | 1920px | Fits fine, centered with extra space |
| iPad | 768px | Overflows by 32px, clipped offscreen |
| iPhone SE | 375px | Overflows by 425px — entirely offscreen |
| iPhone 14 Pro | 393px | Overflows by 407px — unusable |

**The fix**: use `Scale` (0.0–1.0 = 0%–100% of screen) instead of raw pixels:

```luau
UDim2.new(1, -40, 0.8, -40)  -- fills width minus 40px padding, 80% height
```

## Installation

No dependencies — Python 3.7+ standard library only.

```bash
git clone https://github.com/your-org/ui-scale-optimizer.git
cd ui-scale-optimizer
```

## Usage

```bash
# Basic scan
python ui-scale-optimizer.py --path src/

# JSON output (for CI / tooling)
python ui-scale-optimizer.py --path src/ --json

# Show all findings + fix suggestions
python ui-scale-optimizer.py --path src/ --verbose --fix
```

### Output colors

| Icon | Meaning |
|------|---------|
| 🔴 `HARDCODED OFFSET` | Pure pixels — will break on different screens. **Fix now.** |
| 🟡 `MIXED SCALE` | Scale + large offset — likely tuned for one device. Review. |
| ⚪ `OK` | Scale with small offset (fine for padding). |
| ✅ `GOOD SCALE` | `.fromScale()` or proper mixed — works everywhere. |

## How to interpret results

### 🔴 Hardcoded offset

```luau
ShopFrame.Size = UDim2.new(0, 800, 0, 600)
```

- Scale components are both `0`. The frame is **exactly** 800x600px regardless of screen.
- On a 375px-wide phone, 425px of this frame is offscreen.
- **Fix**: Replace with scale-based sizing.

### 🟡 Mixed scale + large offset

```luau
Frame.Size = UDim2.new(0.5, 0, 0.3, 200)
```

- The Y dimension has a 200px offset on top of 30% scale. On a short screen, this might push the element out of view.
- **Fix**: Absorb the offset into the scale value.

## Fix suggestions guide

### Convert offset to scale

Original:
```luau
UDim2.new(0, 400, 0, 300)    -- 400x300px on 1920x1080
```

Fix — convert pixels to screen fraction (400/1920 ≈ 0.208, 300/1080 ≈ 0.278):
```luau
UDim2.new(0.208, 0, 0.278, 0) -- ~21% width, ~28% height on any screen
```

### Absorb offset into scale

Original:
```luau
UDim2.new(0.5, 0, 0.4, 120)   -- 40% height + 120px
```

Fix — convert 120px to scale (120/1080 ≈ 0.111) and add:
```luau
UDim2.new(0.5, 0, 0.511, 0)   -- ~51% height, fully proportional
```

### Full-width bar with padding

Original:
```luau
UDim2.new(0, 1800, 0, 40)     -- assumes 1920px wide
```

Fix — scale = 1.0 (full width), offset = -padding on each side:
```luau
UDim2.new(1, -120, 0, 40)     -- full width minus 60px padding each side
```

### Use AnchorPoint when centering

When using Scale for centering, set the AnchorPoint:
```luau
Frame.AnchorPoint = Vector2.new(0.5, 0.5)   -- pivot at center
Frame.Size = UDim2.new(0.5, 0, 0.5, 0)      -- 50% screen, centered
```

### Responsive text sizes

```luau
-- Instead of hardcoding:
TextLabel.TextSize = 48     -- too large on small screens

-- Use UIStroke or parent-scaling for proportional text sizing.
```

## Device reference

| Device | Resolution | UIScale factor |
|--------|-----------|----------------|
| iPhone SE | 375 x 667 | ~2.0x |
| iPhone 14 Pro | 393 x 852 | ~3.0x |
| iPad | 768 x 1024 | ~2.0x |
| iPad Pro | 1024 x 1366 | ~2.0x |
| PC (1080p) | 1920 x 1080 | 1.0x (baseline) |
| PC (1440p) | 2560 x 1440 | 1.0x |
| 4K | 3840 x 2160 | 1.0x |

Every offset value you hardcode assumes one of these resolutions. Scale values work on all of them.

## Checks performed

1. **Hardcoded offset only** — `Scale=0` means pure pixels
2. **Large absolute offsets** — offsets > 300px flag assumed screen dimensions
3. **No scale component** — 100% offset = not responsive
4. **Frame sizes** — common hardcoded widths (800, 600, etc.)
5. **Large text** — `TextSize >= 48` without scale consideration
6. **Missing AnchorPoint** — Scale used but anchor defaults to (0,0)
7. **Device overflow preview** — simulates element width/height on 5 device sizes

## License

MIT
