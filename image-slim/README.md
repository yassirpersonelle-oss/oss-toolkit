# image-slim

**Your Docker images are probably 2-5x bigger than they need to be.**

image-slim analyzes your Dockerfile and reports which packages can be removed in the same layer to reduce image size by 100-500MB.

## Why does image size matter?

| Problem | Impact |
|---------|--------|
| **Deploy speed** | Larger images take longer to pull, push, and start — slowing down CI/CD |
| **Security attack surface** | Every installed package is a potential vulnerability to scan and patch |
| **Storage costs** | GBs of unused packages stored in registries, caches, and on disk |

## Installation

```bash
# Clone or download image-slim.py
chmod +x image-slim.py

# Run directly with Python 3
python image-slim.py --help
```

## Usage

```bash
# Basic analysis (looks for ./Dockerfile)
python image-slim.py

# Analyze a specific Dockerfile
python image-slim.py -f Dockerfile.prod

# JSON output for scripting
python image-slim.py --json

# Verbose mode with layer breakdown
python image-slim.py --verbose

# Auto-generate an optimized Dockerfile
python image-slim.py --suggest
```

## What each check does

### 1. Build-Time Packages
Packages like `gcc`, `make`, `cmake`, `python3-dev`, `curl`, `git` are commonly installed but only needed to compile or fetch dependencies during build. If they're not in the final `FROM` layer, they're wasted space.

**Savings**: 20-200MB

### 2. Unnecessary Packages
Packages like `man-db`, `vim`, `less`, `nano` are rarely needed inside a container. They add size without purpose.

**Savings**: 5-30MB

### 3. Layer Optimization
If `apt-get install` and `apt-get clean` are in separate `RUN` commands, combining them into one layer avoids storing the intermediate state. Each `RUN` creates a new layer, so splitting cleanup doesn't save space.

**Savings**: 50-200MB

### 4. Missing Cache Clear
After `apt-get install`, package lists remain in `/var/lib/apt/lists/`. Forgetting `rm -rf /var/lib/apt/lists/*` wastes 30-100MB.

**Savings**: 30-100MB

### 5. Multi-Stage Potential
If your Dockerfile compiles code (detects `make`, `cargo build`, `go build`, etc.), the compiler and build tools stay in the image even though they're only needed at build time. A multi-stage build separates the build environment from the runtime image.

**Savings**: 100-500MB

## How to apply suggestions

### Remove build-time packages
```dockerfile
# Before
RUN apt-get update && apt-get install -y gcc g++ make python3-dev

# After: install in build stage only
FROM python:3.11 AS builder
RUN apt-get update && apt-get install -y gcc g++ make python3-dev
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
```

### Combine layers with cache clearing
```dockerfile
# Before (wastes space)
RUN apt-get update && apt-get install -y curl
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# After (single layer)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
```

### Use multi-stage builds
```dockerfile
# Before: compiler in final image
RUN apt-get install -y gcc make
RUN make && make install

# After: build separately, copy binary
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY . .
RUN go build -o myapp

FROM alpine:3.18
COPY --from=builder /app/myapp /usr/local/bin/
```

## Supported package managers

| Manager | Commands detected |
|---------|------------------|
| apt | `apt-get install`, `apt install` |
| apk | `apk add` |
| yum/dnf | `yum install`, `dnf install` |
| pip | `pip install` |
| npm | `npm install`, `npm ci` |
| cargo | `cargo install`, `cargo build` |
| go | `go install`, `go build` |

## License

MIT
