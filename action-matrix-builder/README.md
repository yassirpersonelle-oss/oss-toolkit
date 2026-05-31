# action-matrix-builder

Stop copy-pasting build matrix YAML. Define a simplified config and generate a full GitHub Actions matrix workflow with caching, artifacts, and multiplatform support.

## Example Config

```yaml
# matrix.yml
language: python
versions:
  - "3.11"
  - "3.12"
  - "3.13"
os:
  - ubuntu-latest
  - windows-latest
  - macos-latest
test_command: pytest
install_command: pip install -e ".[dev]"
cache: pip
artifact: true
```

## Usage

```bash
# Generate workflow from matrix.yml
python action-matrix-builder.py

# Use a custom config file
python action-matrix-builder.py --config my-config.yml

# Write to a custom location
python action-matrix-builder.py --output .github/workflows/ci.yml

# Validate config without generating
python action-matrix-builder.py --validate
```

## Generated Workflow

The tool generates a complete GitHub Actions workflow with:

- Checkout step
- Language runtime setup (Python, Node, Go, Rust)
- Cache step (pip, npm, go, cargo)
- Install dependencies
- Run tests
- Upload test artifacts

## Supported Languages & Cache Strategies

| Language | Setup Action     | Cache Key | Cache Path        |
|----------|------------------|-----------|-------------------|
| python   | setup-python@v5  | pip       | ~/.cache/pip      |
| node     | setup-node@v4    | npm       | ~/.npm            |
| go       | setup-go@v5      | go        | ~/.cache/go       |
| rust     | actions-rs/toolchain@v1 | cargo | ~/.cargo/registry |
