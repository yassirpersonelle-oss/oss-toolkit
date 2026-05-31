# pristine

Strip comments, debug logs, and unnecessary whitespace from source code before pasting into ChatGPT/Claude. Saves LLM tokens by removing noise.

## Install

```bash
chmod +x pristine.py
# Optional: symlink into PATH
ln -s "$PWD/pristine.py" ~/local/bin/pristine
```

## Usage

```bash
pristine.py file.py                    # auto-detect language from extension
cat file.js | pristine.py --lang js    # pipe from stdin
pristine.py --lang rust < main.rs      # redirect from file
pristine.py --verbose file.go          # show token savings
```

## Options

| Flag | Description |
|------|-------------|
| `--lang`, `--language` | Force language (auto-detected from file extension when omitted) |
| `--verbose`, `-v` | Print token savings stats to stderr |
| `--help` | Show help message |

## Supported Languages

| Language | Extensions |
|----------|------------|
| Python | `.py` |
| JavaScript / TypeScript | `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs` |
| Rust | `.rs` |
| Go | `.go` |
| Java | `.java` |
| C / C++ | `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` |
| HTML | `.html`, `.htm`, `.xhtml` |
| CSS | `.css`, `.scss`, `.less`, `.sass` |
| Shell / Bash | `.sh`, `.bash`, `.zsh`, `.ksh`, `.fish` |
| YAML | `.yaml`, `.yml` |
| Ruby | `.rb` |
| PHP | `.php`, `.phtml` |

## Verbose Example

```bash
$ pristine.py --verbose example.py
Language: Python
Original: 2840 chars
Pristine: 1432 chars
Removed:  1408 chars
Saved:    ~1056 tokens
Reduction: 49.6%
```

## What Gets Stripped

- **Single-line comments**: `#`, `//`, `--`
- **Multi-line comments**: `/* */`, `""" """`, `''' '''`, `<!-- -->`, `=begin =end`
- **Debug statements**: `print()`, `console.log()`, `echo`, `println!`, `fmt.Println`, `printf`, `puts`, `var_dump`, `debugger`, `alert()`, `byebug`, `binding.pry`, and others common per language
- **Trailing whitespace** on every line
- **Redundant blank lines** (multiple blank lines collapsed to one)

No external dependencies — stdlib only.
