# mcp-discover

> **One command turns any codebase into an MCP server.**
>
> Point at any project — Python, TypeScript, Rust, Go — and get a working
> MCP server config + wrapper with auto-detected functions, type schemas,
> and entry points. Zero manual configuration.

## Why this exists

AI coding agents (Claude Code, Cursor, Copilot, OpenCode) all speak MCP.
But **nobody wants to write MCP config by hand**. Every OSS library has
functions ready to become tools — mcp-discover finds them automatically.

## Quick Start

```bash
# Install
pip install mcp-discover

# Scan your project, generate config + working server
cd your-project/
mcp-discover

# Output directly to stdout for Claude Desktop
mcp-discover --format claude --stdout | pbcopy  # macOS
mcp-discover --format claude --stdout | clip     # Windows

# Interactive mode — pick which functions become tools
mcp-discover --interactive
```

## How It Works

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  Your Codebase   │ ───► │  mcp-discover    │ ───► │  MCP Config +       │
│                  │      │                  │      │  Working Server     │
│  ├── src/        │      │  • AST parsing   │      │                     │
│  │   ├── api.py  │      │  • Type mapping  │      │  ├── .mcp/          │
│  │   └── db.py   │      │  • Route detect  │      │  │   └── mcp.json   │
│  └── tests/      │      │  • Entry detect  │      │  └── tools/*.json   │
└─────────────────┘      └──────────────────┘      └─────────────────────┘
```

### Input → Output

**Input** (your existing code):
```python
def get_user(user_id: int, include_posts: bool = False) -> dict:
    """Fetch a user by ID, optionally including their posts."""
    ...
```

**Output** (generated MCP tool definition):
```json
{
  "name": "get_user",
  "description": "Fetch a user by ID, optionally including their posts.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "user_id": { "type": "integer", "description": "" },
      "include_posts": { "type": "boolean", "description": "" }
    },
    "required": ["user_id"]
  }
}
```

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Auto-discovery** | Finds all functions, routes, CLI commands across 5 languages |
| 🧠 **Type-aware** | Maps Python/TS/Rust/Go types to JSON Schema automatically |
| 🗂️ **Entry point detection** | Reads package.json, pyproject.toml, Cargo.toml for correct commands |
| 📝 **Docstring parsing** | Extracts descriptions from docstrings, JSDoc, /// comments |
| 🖥️ **Interactive mode** | Select which functions to expose, rename tools on the fly |
| 🔌 **Claude Desktop ready** | Drop-in output format for Claude Desktop, Cursor, OpenCode |
| 🚀 **Server generation** | `--generate-server` creates a working stdio MCP server wrapper |
| 🎯 **Zero dependencies** | Stdlib only — pip install with no extra packages |

## Usage

```
mcp-discover [OPTIONS]

Options:
  --path PATH          Project root directory (default: .)
  --output, -o PATH    Output directory (default: .mcp/)
  --name NAME          Server name (default: directory name)
  --lang LANGUAGE      Force language (python|javascript|typescript|rust|go)
  --format FORMAT      Output format: mcp (default), claude, cursor
  --generate-server    Also generate a working MCP server wrapper
  --interactive, -i    Select which functions become tools
  --exclude PATTERN    Exclude functions matching regex (repeatable)
  --show-all           Include test and internal functions
  --stdout             Print to stdout instead of writing files
  --help               Show help
```

### Language Support

| Language | Detection | Route Support | Type Mapping |
|----------|-----------|---------------|-------------|
| Python | AST | Flask, FastAPI, Click, Typer | ✅ Full |
| TypeScript | Regex + AST | Express, Fastify, NestJS | ✅ Full |
| JavaScript | Regex + AST | Express, Fastify | ✅ Full |
| Rust | Regex | — | ✅ Primitives |
| Go | Regex | — | ✅ Primitives |

### Integrating with Claude Desktop

```bash
# Generate and pipe directly into your Claude config
mcp-discover --path ./my-api --format claude --stdout > ~/.config/claude/claude_desktop_config.json
```

### Integrating with Cursor

```bash
# Cursor expects MCP config at .cursor/mcp.json
mcp-discover --path ./my-api --format cursor
```

## Real-world examples

```bash
# Scan a FastAPI backend
mcp-discover --path api/ --name "user-service" --generate-server

# Interactive: pick only the 5 functions you want
mcp-discover --path ./lib --interactive

# Exclude test and internal functions
mcp-discover --path ./ --exclude "^test_" --exclude "^_"

# Generate Claude Desktop config for a Rust CLI
mcp-discover --lang rust --format claude --stdout
```
