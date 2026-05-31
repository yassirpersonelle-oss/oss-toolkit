# MCP Discover

**Turn any repo into an MCP server in one command.**

`mcp-discover` scans a codebase and auto-generates [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server configuration files from the project's functions and API endpoints. Makes any OSS tool MCP-compatible without manual configuration.

## Why MCP Matters

The Model Context Protocol is trending as the standard way for AI agents (Claude Code, Copilot, Cursor, etc.) to interact with external tools. Instead of each agent requiring custom integrations, MCP provides a universal protocol:

- **AI agents need tool access** — every function, CLI command, or API endpoint is a potential MCP tool
- **Zero manual config** — point, scan, and your entire codebase becomes an MCP server
- **Works with any language** — Python, JavaScript, TypeScript, Rust, Go

## Installation

```bash
# Just the script — no dependencies (stdlib only)
curl -O https://raw.githubusercontent.com/your-org/mcp-discover/main/mcp-discover.py
chmod +x mcp-discover.py
```

## Usage

```bash
# Scan current directory, write to .mcp/
python mcp-discover.py

# Scan a specific project
python mcp-discover.py --path /path/to/project

# Output to a custom directory
python mcp-discover.py -o ./mcp-config/

# Custom server name
python mcp-discover.py --name my-tools --path ./my-project

# Force a language (skip auto-detection)
python mcp-discover.py --lang rust --path ./my-rust-project

# Print config to stdout (pipe to file or clipboard)
python mcp-discover.py --stdout

# Pipe directly into Claude Desktop config
python mcp-discover.py --stdout --path ./my-api > ~/.config/claude/claude_desktop_config.json
```

## Output

```
.mcp/
├── mcp.json          # Full MCP server config (claude_desktop_config.json style)
└── tools/
    ├── create_user.json    # Individual tool definition
    ├── delete_post.json
    └── search_items.json
```

### `mcp.json` structure

```json
{
  "mcpServers": {
    "project-name": {
      "command": "python",
      "args": ["-m", "project_name"],
      "env": {},
      "disabled": false,
      "autoApprove": [],
      "tools": [
        {
          "name": "get_user",
          "description": "Fetch a user by ID from the database",
          "inputSchema": {
            "type": "object",
            "properties": {
              "user_id": { "type": "integer", "description": "" }
            },
            "required": ["user_id"]
          }
        }
      ]
    }
  }
}
```

Drop the `mcp.json` contents into your `claude_desktop_config.json` or use it with any MCP client.

## Supported Patterns

### Python
| Pattern | Detected |
|---|---|
| Module-level `def function()` | ✅ |
| Type-annotated params `def fn(x: str, y: int)` | ✅ |
| Flask `@app.route()` | ✅ |
| FastAPI `@router.get()`, `@app.post()` | ✅ |
| Click `@click.command()` | ✅ |
| Typer `@app.command()` | ✅ |
| `async def` functions | ✅ |
| Docstrings as descriptions | ✅ |
| `if __name__ == "__main__"` entry points | ✅ |

### JavaScript / TypeScript
| Pattern | Detected |
|---|---|
| `export function` | ✅ |
| `export const fn = () =>` | ✅ |
| `exports.fn = function()` | ✅ |
| `module.exports` | ✅ |
| Express `app.get()`, `app.post()` | ✅ |
| Fastify `router.get()` | ✅ |
| JSDoc `/** ... */` comments | ✅ |

### Rust
| Pattern | Detected |
|---|---|
| `pub fn` in `lib.rs` / `main.rs` | ✅ |
| Type parameters (i32, String, bool, Vec) | ✅ |
| `/// doc comments` | ✅ |

### Go
| Pattern | Detected |
|---|---|
| Exported `func FunctionName()` | ✅ |
| Methods `func (r *T) Method()` | ✅ |
| Type inference (int, string, bool) | ✅ |
| `// line comments` as descriptions | ✅ |

## Adding to Claude Desktop

1. Run `python mcp-discover.py --path /path/to/your/project --stdout`
2. Copy the output JSON
3. Merge it into your `claude_desktop_config.json` under the `mcpServers` key

Example with `jq`:

```bash
python mcp-discover.py --stdout --path ./my-api | jq '.mcpServers' > /tmp/mcp-servers.json
# Then manually merge into your config
```

## License

MIT
