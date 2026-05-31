#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_BLUE = "\033[94m"
ANSI_MAGENTA = "\033[95m"
ANSI_CYAN = "\033[96m"
ANSI_WHITE = "\033[97m"
ANSI_DIM = "\033[2m"


LANGUAGE_PATTERNS = {
    "python": [
        re.compile(r'File\s+"[^"]*",\s*line\s+\d+,\s*in\s+\w+'),
        re.compile(r"Traceback\s*\(most recent call last\)"),
        re.compile(r"\w+Error:"),
    ],
    "javascript": [
        re.compile(r"at\s+\w+\s+\(.*?:\d+:\d+\)"),
        re.compile(r"at\s+.*?\(.*?:\d+:\d+\)"),
        re.compile(r"Error:\s"),
    ],
    "java": [
        re.compile(r"at\s+[\w.]+\.\w+\([\w.]+\.java:\d+\)"),
        re.compile(r"Exception in thread"),
    ],
    "rust": [
        re.compile(r"thread\s+'[^']+'\s+panicked?\s+at\s+"),
        re.compile(r"at\s+[^:]+:\d+:\d+"),
    ],
    "go": [
        re.compile(r"goroutine\s+\d+.*\[running\]"),
        re.compile(r"runtime\.main\(\)"),
        re.compile(r"\.go:\d+\s+\+0x"),
    ],
    "dotnet": [
        re.compile(r"at\s+[\w.]+\.\w+\(\)\s+in\s+.*?:\w+"),
        re.compile(r"System\.\w+Exception"),
    ],
    "ruby": [
        re.compile(r"from\s+.*?:\d+:in\s+'[^']*'"),
        re.compile(r"<main>'"),
    ],
    "php": [
        re.compile(r"#\d+\s+.*?\(.*?\):\s+\w+"),
        re.compile(r"Stack trace:"),
    ],
}


def detect_language(text):
    scores = {}
    for lang, patterns in LANGUAGE_PATTERNS.items():
        score = 0
        for pat in patterns:
            score += len(pat.findall(text))
        if score > 0:
            scores[lang] = score
    if not scores:
        return "unknown"
    return max(scores, key=scores.get)


def parse_stack_trace(text, lang):
    if lang == "unknown":
        lang = detect_language(text)
    text = text.strip()

    frames = []
    error_type = ""
    error_message = ""
    raw_lines = text.split("\n")

    if lang == "python":
        return _parse_python(text, raw_lines, frames, error_type, error_message)
    elif lang == "javascript":
        return _parse_javascript(text, raw_lines, frames, error_type, error_message)
    elif lang == "java":
        return _parse_java(text, raw_lines, frames, error_type, error_message)
    elif lang == "rust":
        return _parse_rust(text, raw_lines, frames, error_type, error_message)
    elif lang == "go":
        return _parse_go(text, raw_lines, frames, error_type, error_message)
    elif lang == "dotnet":
        return _parse_dotnet(text, raw_lines, frames, error_type, error_message)
    elif lang == "ruby":
        return _parse_ruby(text, raw_lines, frames, error_type, error_message)
    elif lang == "php":
        return _parse_php(text, raw_lines, frames, error_type, error_message)
    else:
        return {
            "language": lang,
            "error_type": "",
            "error_message": "",
            "frames": [],
            "root_cause_frame": None,
        }


def _parse_python(text, raw_lines, frames, error_type, error_message):
    lang = "python"
    pat_frame = re.compile(r'File\s+"([^"]+)",\s*line\s+(\d+)(?:,\s*in\s+(\w+))?')
    pat_errtype = re.compile(r"^(\w+Error|Exception|Error):\s*(.*)", re.MULTILINE)

    for m in pat_frame.finditer(text):
        frames.append({
            "file": m.group(1),
            "line": int(m.group(2)),
            "function": m.group(3) or "<module>",
            "internal": _is_internal_python(m.group(1)),
        })

    em = pat_errtype.search(text)
    if em:
        error_type = em.group(1)
        error_message = em.group(2).strip()

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_javascript(text, raw_lines, frames, error_type, error_message):
    lang = "javascript"
    pat_frame = re.compile(r"at\s+(?:\w+\s+)?(?:async\s+)?(.*?)\s*\(?(.*?):(\d+):(\d+)\)?")
    pat_err = re.compile(r"^(\w+Error):\s*(.*)", re.MULTILINE)

    for line in raw_lines:
        line = line.strip()
        m = pat_frame.search(line)
        if m:
            func = m.group(1).strip() if m.group(1).strip() else "<anonymous>"
            filepath = m.group(2)
            frames.append({
                "file": filepath,
                "line": int(m.group(3)),
                "col": int(m.group(4)),
                "function": func,
                "internal": _is_internal_js(filepath),
            })

    em = pat_err.search(text)
    if em:
        error_type = em.group(1)
        error_message = em.group(2).strip()
    else:
        em2 = re.search(r"^(Uncaught\s+)?(\w+Error):\s*(.*)", text, re.MULTILINE)
        if em2:
            error_type = em2.group(2)
            error_message = em2.group(3).strip()

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_java(text, raw_lines, frames, error_type, error_message):
    lang = "java"
    pat_frame = re.compile(r"at\s+([\w.$]+)\.(\w+)\(([\w.]+\.java):(\d+)\)")
    pat_err = re.compile(r"^([\w.]+Exception|Error):\s*(.*)", re.MULTILINE)
    pat_thread = re.compile(r"Exception in thread")

    for m in pat_frame.finditer(text):
        pkg = m.group(1)
        func = f"{pkg}.{m.group(2)}"
        frames.append({
            "file": m.group(3),
            "line": int(m.group(4)),
            "function": func,
            "internal": _is_internal_java(m.group(3)),
        })

    em = pat_err.search(text)
    if em:
        error_type = em.group(1)
        error_message = em.group(2).strip()
    if not error_type:
        for line in raw_lines:
            if "Exception" in line or "Error" in line:
                em2 = re.search(r'(?:Exception in thread "[^"]*"\s*)?([\w.$]+(?:\.[A-Z]\w*)*(?:Exception|Error))(?::\s*(.*))?', line)
                if em2:
                    error_type = em2.group(1)
                    error_message = (em2.group(2) or "").strip()
                    break

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_rust(text, raw_lines, frames, error_type, error_message):
    lang = "rust"
    pat_frame = re.compile(r"at\s+([^:]+):(\d+):(\d+)")
    pat_panic = re.compile(r"thread\s+'([^']+)'\s+panicked?\s+at\s+'([^']*)'")

    pm = pat_panic.search(text)
    if pm:
        error_type = "panic"
        error_message = pm.group(2)
    else:
        em = re.search(r"^(error|Error|panicked?):\s*(.*)", text, re.MULTILINE | re.IGNORECASE)
        if em:
            error_type = em.group(1)
            error_message = em.group(2).strip()

    for m in pat_frame.finditer(text):
        frames.append({
            "file": m.group(1),
            "line": int(m.group(2)),
            "col": int(m.group(3)),
            "function": "",
            "internal": _is_internal_rust(m.group(1)),
        })

    pat_func = re.compile(r"^\d+:\s*(.+?)\s*at", re.MULTILINE)
    for i, line in enumerate(raw_lines):
        mf = pat_func.match(line)
        if mf and i < len(frames):
            frames[i]["function"] = mf.group(1).strip()

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_go(text, raw_lines, frames, error_type, error_message):
    lang = "go"
    pat_frame = re.compile(r"([^/\s]+(?:/[^\s]+)*)\.go:(\d+)")

    pat_goroutine = re.compile(r"goroutine\s+\d+.*\[running\]:")
    lines = raw_lines[:]
    recording = False
    for line in lines:
        if pat_goroutine.search(line):
            recording = True
            continue
        errm = re.search(r"^(panic|runtime error|fatal error):\s*(.*)", line, re.IGNORECASE)
        if errm and line.strip():
            error_type = errm.group(1)
            error_message = errm.group(2).strip()
            recording = True
            continue

    if not error_type:
        em = re.search(r"^(panic|runtime error|fatal error):\s*(.*)", text, re.MULTILINE | re.IGNORECASE)
        if em:
            error_type = em.group(1)
            error_message = em.group(2).strip()
    if not error_type:
        em = re.search(r"^([\w.]+Error|Exception):\s*(.*)", text, re.MULTILINE)
        if em:
            error_type = em.group(1)
            error_message = em.group(2).strip()

    for m in pat_frame.finditer(text):
        frames.append({
            "file": m.group(1) + ".go",
            "line": int(m.group(2)),
            "function": "",
            "internal": _is_internal_go(m.group(1)),
        })

    pat_func_go = re.compile(r"^([\w.()*\[\]]+)\(.*?\)", re.MULTILINE)
    for i, line in enumerate(raw_lines):
        mf = pat_func_go.match(line.strip())
        if mf and i < len(frames):
            frames[i]["function"] = mf.group(1).strip()

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_dotnet(text, raw_lines, frames, error_type, error_message):
    lang = "dotnet"
    pat_frame = re.compile(r"at\s+([\w.<>+]+)\.(\w+)\(.*?\)\s+in\s+([^:]+):line\s+(\d+)")
    pat_err = re.compile(r"^(System\.\w+Exception|Exception):\s*(.*)", re.MULTILINE)

    for m in pat_frame.finditer(text):
        ns = m.group(1)
        method = m.group(2)
        frames.append({
            "file": m.group(3),
            "line": int(m.group(4)),
            "function": f"{ns}.{method}",
            "internal": _is_internal_dotnet(m.group(3)),
        })

    em = pat_err.search(text)
    if em:
        error_type = em.group(1)
        error_message = em.group(2).strip()

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_ruby(text, raw_lines, frames, error_type, error_message):
    lang = "ruby"
    pat_frame = re.compile(r"from\s+([^:]+):(\d+):in\s+'([^']*)'")
    pat_err = re.compile(r"^([\w:]+Error|Exception):\s*(.*)", re.MULTILINE)

    for m in pat_frame.finditer(text):
        frames.append({
            "file": m.group(1),
            "line": int(m.group(2)),
            "function": m.group(3),
            "internal": _is_internal_ruby(m.group(1)),
        })

    em = pat_err.search(text)
    if em:
        error_type = em.group(1)
        error_message = em.group(2).strip()

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _parse_php(text, raw_lines, frames, error_type, error_message):
    lang = "php"
    pat_frame = re.compile(r"#\d+\s+([^:]+)\((\d+)\):\s+([^(]+)\(.*?\)")
    pat_err = re.compile(r"^(PHP\s+)?(Fatal error|Warning|Notice|Parse error):\s*(.*)", re.MULTILINE)

    for m in pat_frame.finditer(text):
        frames.append({
            "file": m.group(1),
            "line": int(m.group(2)),
            "function": m.group(3).strip(),
            "internal": _is_internal_php(m.group(1)),
        })

    em = pat_err.search(text)
    if em:
        error_type = em.group(2) if em.group(2) else ""
        error_message = em.group(3).strip() if em.group(3) else ""

    root = _find_root_cause(frames)
    return {
        "language": lang,
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "root_cause_frame": root,
    }


def _is_internal_python(filepath):
    internal_dirs = [
        "lib/python", "site-packages", "dist-packages",
        "lib/python3", "Lib/", "python3.",
    ]
    fp = filepath.replace("\\", "/")
    for d in internal_dirs:
        if d in fp:
            return True
    return False


def _is_internal_js(filepath):
    internal = ["node_modules", "internal/", "<anonymous>", "native"]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _is_internal_java(filepath):
    internal = ["java/", "javax/", "sun/", "jdk/", "com/sun/"]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _is_internal_rust(filepath):
    internal = ["rustc", "library/std", "src/libcore", "src/liballoc", "<source>"]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _is_internal_go(filepath):
    internal = ["runtime/", "sync/", "fmt.", "os.", "io.", "net/", "internal/", "reflect."]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _is_internal_dotnet(filepath):
    internal = ["System", "Microsoft.", "netstandard", "NuGet"]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _is_internal_ruby(filepath):
    internal = ["gems/", "ruby/", "lib/ruby", "/usr/lib/ruby"]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _is_internal_php(filepath):
    internal = ["vendor/", "php/", "pear/"]
    fp = filepath.replace("\\", "/")
    for d in internal:
        if d in fp:
            return True
    return False


def _find_root_cause(frames):
    user_frames = [f for f in frames if not f.get("internal")]
    if user_frames:
        return user_frames[-1]
    if frames:
        return frames[-1]
    return None


def colorize(text, color):
    return f"{color}{text}{ANSI_RESET}"


def generate_explanation(parsed, verbose, show_code):
    lang = parsed["language"]
    err_type = parsed["error_type"]
    err_msg = parsed["error_message"]
    frames = parsed["frames"]
    root = parsed["root_cause_frame"]

    lines = []
    lines.append("")
    lines.append(colorize("## What went wrong", ANSI_BOLD + ANSI_RED))
    if err_type:
        lines.append(f"  {colorize(err_type, ANSI_YELLOW)}{': ' + err_msg if err_msg else ''}")
        lines.append("")
        desc = _describe_error(err_type, err_msg, lang)
        lines.append(f"  {desc}")

    lines.append("")
    lines.append(colorize("## Where it happened", ANSI_BOLD + ANSI_CYAN))
    if root:
        loc = f"  {root['file']}:{root['line']}"
        if root.get("function"):
            loc += f" in {root['function']}()"
        lines.append(loc)
        if show_code and os.path.isfile(root["file"]):
            context = _read_code_context(root["file"], root["line"], 3)
            if context:
                lines.append("")
                lines.append(colorize("  Code context:", ANSI_DIM))
                lines.append(context)
    else:
        lines.append("  (No stack frames parsed)")

    if frames and verbose:
        lines.append("")
        lines.append(colorize("## Full call stack", ANSI_BOLD + ANSI_BLUE))
        for i, f in enumerate(frames):
            marker = "  >> " if f is root else "     "
            internal_tag = colorize(" [internal]", ANSI_DIM) if f.get("internal") else ""
            loc = f"{marker}{f['file']}:{f['line']}"
            if f.get("function"):
                loc += f" in {f['function']}()"
            lines.append(loc + internal_tag)

    lines.append("")
    lines.append(colorize("## Likely cause", ANSI_BOLD + ANSI_MAGENTA))
    cause = _likely_cause(err_type, err_msg, lang)
    lines.append(f"  {cause}")

    lines.append("")
    lines.append(colorize("## How to fix", ANSI_BOLD + ANSI_GREEN))
    fix = _how_to_fix(err_type, err_msg, lang)
    for step in fix:
        lines.append(f"  {step}")

    lines.append("")
    return "\n".join(lines)


COMMON_PATTERNS = [
    ("module", "ModuleNotFoundError|ImportError", None,
     "You're trying to import a module that isn't installed or doesn't exist in your Python path.",
     ["1. Check that the module name is spelled correctly",
      "2. If it's a third-party package, install it: pip install <module>",
      "3. If it's your own module, ensure it's in the same directory or adjust PYTHONPATH"]),
    ("typeerror_not_function", "TypeError:?.*is not a function|TypeError:?.*is not callable", None,
     "You're calling something that isn't a function. The value you're trying to invoke as a function is actually a different type (e.g., int, NoneType, dict).",
     ["1. Check the variable you're calling — verify it's a function, not a different type",
      "2. Print the type of the variable before calling: print(type(var))",
      "3. Ensure you haven't reassigned the function name to a different value"]),
    ("nullpointer", "NullPointerException|NullPointer", None,
     "You're trying to access a property or method on a null/None value. The object reference is null — it was never initialized or was explicitly set to null.",
     ["1. Trace back where the object was created — ensure it is initialized before use",
      "2. Add a null check before accessing properties: if (obj != null)",
      "3. Use Optional or @Nullable annotations to make null-safety explicit"]),
    ("nil_pointer_go", "panic:? runtime error:? invalid memory address|nil pointer dereference", "go",
     "Nil pointer dereference in Go. Your code tried to access a field or method on a pointer that is nil (was never initialized with & or new).",
     ["1. Check that the pointer was properly initialized: use & or new()",
      "2. Check for places where a function might return nil instead of a valid pointer",
      "3. Add a nil check: if ptr == nil { return errors.New(...) }"]),
    ("undefined_var", "ReferenceError|NameError.*not defined|undefined", None,
     "You're trying to use a variable or identifier that doesn't exist in the current scope. It may be misspelled, out of scope, or never declared.",
     ["1. Check the spelling of the variable name",
      "2. Make sure the variable is in scope (declared in this function/block)",
      "3. If using an import, check that the imported name is correct"]),
    ("syntax_error", "SyntaxError|Parse error", None,
     "There's a syntax error in your code — a typo or structural problem that prevents parsing. The interpreter can't understand the file.",
     ["1. Look at the indicated line for missing punctuation (parens, brackets, colons)",
      "2. Check for mismatched quotes or strings spanning multiple lines",
      "3. Use a linter to catch syntax issues early"]),
    ("index_out_of_bounds", "IndexError|IndexOutOfBoundsException|ArrayIndexOutOfBounds", None,
     "You're trying to access an index that doesn't exist in a list, array, or string. This means the index is >= the length or negative.",
     ["1. Check the length of the collection before accessing: if index < len(arr)",
      "2. Ensure your loop logic doesn't go past the end of the array",
      "3. Use .get() or try/except for safe access"]),
    ("key_error", "KeyError", None,
     "You're trying to access a dictionary key that doesn't exist. The key you used is not present in the dict.",
     ["1. Check if the key exists before accessing: if key in my_dict:",
      "2. Use .get() with a default: my_dict.get(key, default)",
      "3. Make sure the key is spelled exactly as it appears in the dict"]),
    ("division_zero", "ZeroDivisionError|DivideByZeroException|Division by zero", None,
     "You're dividing a number by zero. Division by zero is undefined and raises an error.",
     ["1. Check the divisor before dividing: if divisor != 0:",
      "2. Add a try/except or guard clause before the division",
      "3. Validate user input that could be zero"]),
    ("attribute_error", "AttributeError", None,
     "You're trying to access an attribute or method that doesn't exist on the object. The object doesn't have what you're asking for.",
     ["1. Check the object's type: print(type(obj))",
      "2. List available attributes: print(dir(obj))",
      "3. Make sure you're using the right object — you may have accidentally assigned the wrong type"]),
    ("value_error", "ValueError", None,
     "A function received an argument with the right type but an inappropriate value. The value is valid in type but invalid in context.",
     ["1. Check the value you're passing — it needs to be valid for the function's expectations",
      "2. Convert or sanitize the input before passing it to the function",
      "3. Read the function's documentation to understand valid input ranges"]),
    ("type_error_mismatch", "TypeError:?.*must be|TypeError:?.*expected|TypeError:?.*got", None,
     "You're passing an argument of the wrong type to a function. The function expected one type but received another.",
     ["1. Check the types of all arguments: print(type(arg1), type(arg2))",
      "2. Convert the value to the expected type (e.g., int(x), str(y))",
      "3. Read the function signature to understand what types it expects"]),
    ("file_not_found", "FileNotFoundError|FileNotFoundException|ENOENT", None,
     "Your code is trying to open or access a file that doesn't exist at the given path.",
     ["1. Double-check the file path — it may be misspelled or relative to the wrong directory",
      "2. Use os.path.exists(path) to check if the file exists before opening",
      "3. Consider using pathlib or os.path.join for robust path construction"]),
    ("permission_denied", "PermissionDenied|PermissionError|EACCES", None,
     "Your code doesn't have the required permissions to access the file or resource.",
     ["1. Check the file permissions: ls -la or icacls on Windows",
      "2. Run with appropriate privileges if needed",
      "3. Change file permissions: chmod (Unix) or adjust ACL (Windows)"]),
    ("connection_refused", "ConnectionRefusedError|connection refused|ECONNREFUSED", None,
     "Your code tried to connect to a server that is not running or not accepting connections at that address/port.",
     ["1. Ensure the server is running: check with systemctl or Task Manager",
      "2. Verify the host and port are correct",
      "3. Check for firewalls blocking the connection"]),
    ("timeout", "TimeoutError|timeout|TimedOut", None,
     "An operation took too long and timed out. The server or resource didn't respond within the expected time.",
     ["1. Check if the server/service is overloaded or down",
      "2. Increase the timeout if appropriate",
      "3. Add retry logic with exponential backoff"]),
    ("json_decode", "JSONDecodeError|json.decoder|JSON parse error|Unexpected token", None,
     "Your code is trying to parse a string as JSON, but the string is not valid JSON.",
     ["1. Print the raw string before parsing to see what you're actually getting",
      "2. Use a JSON validator (e.g., jq or jsonlint.com) to find the syntax issue",
      "3. Check that the API you're calling returned JSON and not an error page"]),
    ("panic_rust", "panic", "rust",
     "Your Rust program panicked — this is an unrecoverable error caused by an unexpected state. The panic message gives details about what went wrong.",
     ["1. Read the panic message carefully — it often includes the exact assertion that failed",
      "2. Use .unwrap() only when you're sure the Result/Option is Some/Ok — prefer pattern matching or ? operator",
      "3. Use expect('message') to provide context when panicking"]),
    ("goroutine_panic", "panic", "go",
     "A goroutine in your Go program panicked. An unrecoverable error occurred in a concurrent function.",
     ["1. Check the panic message for details on what went wrong",
      "2. Use defer/recover to handle panics gracefully in goroutines",
      "3. Ensure channels and mutexes are used correctly to avoid race conditions"]),
    ("exception_dotnet", "System\\.\\w+Exception", "dotnet",
     "A .NET exception was thrown. The exception type and message indicate what went wrong.",
     ["1. Check the exception message and inner exception for details",
      "2. Add a try/catch block around the failing code",
      "3. Use a debugger or logging to get more context"]),
    ("ruby_no_method", "NoMethodError", None,
     "You're trying to call a method that doesn't exist on the object. This is Ruby's version of 'undefined method'.",
     ["1. Check the object's class: obj.class",
      "2. List available methods: obj.methods",
      "3. Make sure the object is the type you expect — it may be nil"]),
    ("php_type_error", "TypeError|Type Error", "php",
     "A PHP type error occurred. PHP 7+ has strict type hints that must match.",
     ["1. Check the type hints in the function signature",
      "2. Ensure you're passing the right types (int, string, array, etc.)",
      "3. Declare strict_types=1 at the top of the file"]),
]


def _describe_error(err_type, err_msg, lang):
    if not err_type:
        return "No error type detected."
    for _, pattern, lang_match, desc, _ in COMMON_PATTERNS:
        if lang_match and lang != lang_match:
            continue
        if re.search(pattern, err_type + ": " + err_msg, re.IGNORECASE):
            return desc
    return f"An error of type '{err_type}' occurred{f' with message: {err_msg}' if err_msg else ''}."


def _likely_cause(err_type, err_msg, lang):
    if not err_type:
        return "No error type detected. Cannot determine cause."
    for _, pattern, lang_match, _, _ in COMMON_PATTERNS:
        if lang_match and lang != lang_match:
            continue
        if re.search(pattern, err_type + ": " + err_msg, re.IGNORECASE):
            for _, _, _, desc, _ in COMMON_PATTERNS:
                pass
    general = f"The error '{err_type}' was raised{f' with message: {err_msg}' if err_msg else ''}. This is likely a bug in the code at the root cause frame."
    for _, pattern, lang_match, desc, _ in COMMON_PATTERNS:
        if lang_match and lang != lang_match:
            continue
        if re.search(pattern, err_type + ": " + err_msg, re.IGNORECASE):
            return desc
    return general


def _how_to_fix(err_type, err_msg, lang):
    if not err_type:
        return ["No error type detected. Read the stack trace manually and trace the execution path."]
    for _, pattern, lang_match, _, steps in COMMON_PATTERNS:
        if lang_match and lang != lang_match:
            continue
        if re.search(pattern, err_type + ": " + err_msg, re.IGNORECASE):
            return steps
    return [
        f"1. Examine the error type: '{err_type}'",
        f"2. Read the error message carefully{f': {err_msg}' if err_msg else ''}",
        "3. Trace the execution path through the stack frames",
        "4. Add error handling (try/except or match/if) around the failing code",
        "5. Write a test that reproduces the issue",
    ]


def _read_code_context(filepath, line, radius):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception:
        return None

    start = max(0, line - radius - 1)
    end = min(len(all_lines), line + radius)
    out_lines = []
    for i in range(start, end):
        lineno = i + 1
        prefix = ">>>" if lineno == line else "   "
        out_lines.append(f"  {prefix} {lineno:4d}| {all_lines[i].rstrip()}")
    return "\n".join(out_lines)


def output_json(parsed, explanation):
    result = {
        "language": parsed["language"],
        "error_type": parsed["error_type"],
        "error_message": parsed["error_message"],
        "frames": parsed["frames"],
        "root_cause_frame": parsed["root_cause_frame"],
        "explanation": explanation,
    }
    return json.dumps(result, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Decode and explain stack traces in plain English.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--trace", type=str, help="Stack trace string")
    group.add_argument("--file", type=str, help="Path to file containing stack trace")

    parser.add_argument("--lang", "--language", type=str, dest="lang",
                        help="Hint language (python, javascript, java, rust, go, dotnet, ruby, php)")
    parser.add_argument("--verbose", action="store_true", help="Show full call stack")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("--code", action="store_true",
                        help="Show surrounding code context (requires root cause file to exist locally)")

    args = parser.parse_args()

    if args.trace:
        text = args.trace
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("No input provided.", file=sys.stderr)
        sys.exit(1)

    if args.lang:
        lang = args.lang.lower()
        if lang not in LANGUAGE_PATTERNS:
            known = ", ".join(sorted(LANGUAGE_PATTERNS.keys()))
            print(f"Unknown language '{lang}'. Known: {known}", file=sys.stderr)
            sys.exit(1)
    else:
        lang = detect_language(text)
        if lang == "unknown":
            print("Could not auto-detect language. Use --lang to specify.", file=sys.stderr)
            sys.exit(1)

    parsed = parse_stack_trace(text, lang)
    explanation = generate_explanation(parsed, verbose=args.verbose, show_code=args.code)

    if args.format == "json":
        print(output_json(parsed, explanation))
    else:
        print(explanation)


if __name__ == "__main__":
    main()
