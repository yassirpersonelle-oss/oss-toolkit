# vim-doc-gen

Auto-generate Vim help docs from your Vimscript and Lua plugin source code.

Most Vim plugins have zero documentation because writing vimdoc is painful.
This tool scans your plugin source, extracts function signatures, commands,
autocmds, and configuration options, and produces a ready-to-edit `:help` file.

## Usage

```bash
# Generate docs for a plugin directory
python vim-doc-gen.py --path /path/to/my-plugin

# Custom output file and plugin name
python vim-doc-gen.py --path /path/to/my-plugin -o doc/my-plugin.txt -n "My Plugin"

# Verbose mode shows what was parsed
python vim-doc-gen.py --path /path/to/my-plugin --verbose
```

### Options

| Flag | Description |
|------|-------------|
| `--path` | **(Required)** Path to the plugin directory to scan. |
| `--output`, `-o` | Output file path. Default: `doc/<plugin-name>.txt`. |
| `--plugin-name`, `-n` | Plugin name. Default: derived from the directory name. |
| `--verbose`, `-v` | Print detailed info about what was found during parsing. |

## How Docstrings Are Extracted

The tool uses a simple convention: **comments directly above a declaration
are treated as its documentation.**

### Vimscript

```vim
" This function initializes the plugin and loads config
" from the user's vimrc.
function! myplugin#init(config)
    " ...
endfunction
```

Generates:
```
myplugin#init({config})                   *myplugin#init()*
    This function initializes the plugin and loads config from the user's vimrc.
```

Comments starting with `-` are treated as doc-block markers:

```vim
" - Sets up highlight groups
" - Defines key mappings
function! myplugin#setup()
```

### Lua

```lua
--- This function formats the current buffer using the LSP.
function M.format(opts)
    -- ...
end
```

Both `---` and `--` comments are captured.

## Supported Patterns

### Vimscript (`.vim`)

| Pattern | What It Captures |
|---------|------------------|
| `function! Plugin#Name(args)` | Function name and arguments |
| `command! -nargs=N CmdName` | User command and nargs flag |
| `autocmd Event pattern` | Autocmd event and pattern |
| `let g:option = value` | Global option name and default |
| `" comment above` | Description for the next declaration |

### Lua (`.lua`)

| Pattern | What It Captures |
|---------|------------------|
| `function M.name(args)` | Function name and arguments |
| `vim.api.nvim_create_user_command(...)` | User command name |
| `vim.api.nvim_create_autocmd(...)` | Autocmd event |
| `vim.g.option_name = value` | Global option name and default |
| `---` / `--` comment above | Description for the next declaration |

## Reviewing and Refining Generated Docs

The generated file is a starting point, not a final product. After running
vim-doc-gen:

1. **Open the generated file** in your editor and read through it.
2. **Add prose descriptions** where the auto-extracted comments are sparse.
3. **Add examples** for non-obvious functions or commands.
4. **Remove anything incorrect** — the tool guesses based on proximity, so
   sometimes a comment above a blank line gets attached to the wrong thing.
5. **Add sections** the tool can't generate: requirements, installation,
   known issues, changelog, etc.

The output follows standard vimdoc conventions so `:help` renders it correctly.

## Requirements

- Python 3.7+
- No external dependencies (stdlib only)
