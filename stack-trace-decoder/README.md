# Stack Trace Decoder

> **Maintainers: stop copy-pasting stack traces into Google.**

A Python CLI that takes a stack trace from any language and explains it in plain English: what went wrong, likely root cause, and how to fix it. Reduces low-quality bug reports for maintainers.

## Usage

```bash
# From stdin
cat trace.txt | python stack-trace-decoder.py --verbose

# Direct trace string
python stack-trace-decoder.py --trace 'TypeError: X is not a function\n    at foo (app.js:10:5)'

# From a file
python stack-trace-decoder.py --file trace.txt

# Specify language explicitly
python stack-trace-decoder.py --lang rust --file panic.txt

# Show surrounding code (if files exist locally)
python stack-trace-decoder.py --code --file trace.txt

# JSON output for programmatic use
cat trace.txt | python stack-trace-decoder.py --format json
```

## Options

| Flag | Description |
|---|---|
| `--trace` | Stack trace as a string argument |
| `--file` | Path to file containing the stack trace |
| `--lang`, `--language` | Hint language (auto-detect otherwise) |
| `--verbose` | Show full call stack with internal/library frames |
| `--format` | Output format: `text` (default) or `json` |
| `--code` | Show surrounding source code (3 lines context) |

## Supported Languages

- **Python** — `File "...", line X, in function`, `Traceback`
- **JavaScript** — `at function (file:line:col)`, `Error:`
- **Java** — `at package.Class.method(File.java:line)`
- **Rust** — `thread 'main' panicked at`, `at file:line:col`
- **Go** — `goroutine X [running]`, `main.go:line`
- **C# / .NET** — `at Namespace.Class.Method() in file:line`
- **Ruby** — `from file:line:in 'method'`
- **PHP** — `Stack trace:`, `#X file(line): function`

## Example: Python Trace

```
$ cat <<'EOF' | python stack-trace-decoder.py
Traceback (most recent call last):
  File "/home/user/app.py", line 15, in main
    result = process_data(data)
  File "/home/user/app.py", line 8, in process_data
    return data["key"] + 1
KeyError: 'key'
EOF
```

## Example: JavaScript Trace

```
$ cat <<'EOF' | python stack-trace-decoder.py --verbose
TypeError: user.getName is not a function
    at Object.<anonymous> (app.js:15:22)
    at Module._compile (internal/modules/cjs/loader.js:1063:30)
    at Object.Module._extensions (internal/modules/cjs/loader.js:1092:10)
EOF
```

## Example: Rust Panic

```
$ cat <<'EOF' | python stack-trace-decoder.py --lang rust
thread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5', src/main.rs:10:17
    at src/main.rs:10:17
EOF
```

## JSON Output

```json
{
  "language": "python",
  "error_type": "KeyError",
  "error_message": "'key'",
  "frames": [...],
  "root_cause_frame": {
    "file": "/home/user/app.py",
    "line": 8,
    "function": "process_data",
    "internal": false
  },
  "explanation": "..."
}
```

## How it works

1. **Auto-detects** the language from the trace format
2. **Parses** error type, message, and stack frames
3. **Identifies** the root cause frame (deepest user-code frame)
4. **Matches** against common error patterns (20+ known types)
5. **Generates** a plain-English explanation with actionable fix steps

## License

MIT
