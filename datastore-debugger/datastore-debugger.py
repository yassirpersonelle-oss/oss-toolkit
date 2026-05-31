#!/usr/bin/env python3
"""DataStore Debugger - Local Roblox DataStore Simulator for Luau Developers.

Simulates DataStoreService, DataStore, OrderedDataStore APIs locally with
transaction history, conflict replay, schema validation, and chaos testing.
"""

import argparse
import json
import os
import random
import re
import shlex
import sys
import time
import traceback
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

DEFAULT_STORE_PATH = "datastore.json"
DEFAULT_PORT = 8765
MAX_VERSIONS = 10
CHAOS_RATE = 0.30
BOARD = "\u2501"


class VersionHistory:
    def __init__(self, max_versions=MAX_VERSIONS):
        self.max_versions = max_versions
        self.versions = {}
        self.next_version = {}

    def record(self, key, value):
        if key not in self.versions:
            self.versions[key] = []
            self.next_version[key] = 1
        ver = self.next_version[key]
        entry = {
            "version": ver,
            "value": json.loads(json.dumps(value)),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.versions[key].append(entry)
        if len(self.versions[key]) > self.max_versions:
            self.versions[key] = self.versions[key][-self.max_versions:]
        self.next_version[key] = ver + 1
        return ver

    def get_version(self, key, version):
        if key not in self.versions:
            return None
        for v in self.versions[key]:
            if v["version"] == version:
                return v
        return None

    def list_versions(self, key, sort_direction="descending", min_date=None, max_date=None, page_size=None):
        if key not in self.versions:
            return []
        result = []
        for v in self.versions[key]:
            ts = datetime.fromisoformat(v["timestamp"])
            if min_date and ts < min_date:
                continue
            if max_date and ts > max_date:
                continue
            result.append(v)
        if sort_direction == "ascending":
            result = sorted(result, key=lambda x: x["version"])
        else:
            result = sorted(result, key=lambda x: x["version"], reverse=True)
        if page_size:
            result = result[:page_size]
        return result

    def to_dict(self):
        return {
            "max_versions": self.max_versions,
            "versions": self.versions,
            "next_version": self.next_version,
        }

    @classmethod
    def from_dict(cls, d):
        vh = cls(max_versions=d.get("max_versions", MAX_VERSIONS))
        vh.versions = {k: v for k, v in d.get("versions", {}).items()}
        vh.next_version = {k: v for k, v in d.get("next_version", {}).items()}
        return vh


class TransactionLog:
    def __init__(self):
        self.transactions = []

    def add(self, operation, key, status, detail="", value=None):
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "time": time.time(),
            "operation": operation,
            "key": key,
            "status": status,
            "detail": detail,
            "value": value,
        }
        self.transactions.append(entry)
        return entry

    def recent(self, n=100):
        return self.transactions[-n:]

    def all(self):
        return self.transactions

    def to_list(self):
        return self.transactions

    @classmethod
    def from_list(cls, lst):
        tl = cls()
        tl.transactions = lst
        return tl


class RateLimiter:
    def __init__(self):
        self.buckets = {}
        self.max_writes = 60
        self.max_reads = 300
        self.window = 60

    def _get_bucket(self, datastore_name):
        if datastore_name not in self.buckets:
            self.buckets[datastore_name] = {"writes": [], "reads": []}
        return self.buckets[datastore_name]

    def _clean(self, lst):
        cutoff = time.time() - self.window
        return [t for t in lst if t > cutoff]

    def check_write(self, datastore_name):
        bucket = self._get_bucket(datastore_name)
        bucket["writes"] = self._clean(bucket["writes"])
        if len(bucket["writes"]) >= self.max_writes:
            return False, "Rate limit exceeded: too many writes"
        bucket["writes"].append(time.time())
        return True, ""

    def check_read(self, datastore_name):
        bucket = self._get_bucket(datastore_name)
        bucket["reads"] = self._clean(bucket["reads"])
        if len(bucket["reads"]) >= self.max_reads:
            return False, "Rate limit exceeded: too many reads"
        bucket["reads"].append(time.time())
        return True, ""

    def reset(self):
        self.buckets = {}


class SchemaValidator:
    def __init__(self):
        self.schemas = {}

    def set_schema(self, key, schema):
        self.schemas[key] = schema

    def validate(self, key, value):
        if key not in self.schemas:
            return True, ""
        schema = self.schemas[key]
        errors = []
        for field, expected_type in schema.items():
            if field not in value:
                errors.append(f"missing field '{field}'")
                continue
            actual = value[field]
            if expected_type == "number" and not isinstance(actual, (int, float)):
                errors.append(f"field '{field}' expected number, got {type(actual).__name__}")
            elif expected_type == "string" and not isinstance(actual, str):
                errors.append(f"field '{field}' expected string, got {type(actual).__name__}")
            elif expected_type == "boolean" and not isinstance(actual, bool):
                errors.append(f"field '{field}' expected boolean, got {type(actual).__name__}")
            elif expected_type == "table" and not isinstance(actual, dict):
                errors.append(f"field '{field}' expected table, got {type(actual).__name__}")
        if errors:
            return False, "; ".join(errors)
        return True, ""


class DataStore:

    def __init__(self, name, scope="global", store_path=DEFAULT_STORE_PATH,
                 version_history=None, chaos=False, verbose=False,
                 rate_limiter=None, schema_validator=None, txn_log=None):
        self.name = name
        self.scope = scope
        self.store_path = store_path
        self.data = {}
        self.version_history = version_history or VersionHistory()
        self.chaos = chaos
        self.verbose = verbose
        self.rate_limiter = rate_limiter or RateLimiter()
        self.schema_validator = schema_validator or SchemaValidator()
        self.txn_log = txn_log
        self.conflict_delay = 0.1

    def _full_key(self, key):
        return f"{self.scope}:{self.name}:{key}"

    def _chaos_check(self):
        if self.chaos and random.random() < CHAOS_RATE:
            errors = [
                "Simulated network error",
                "Simulated timeout",
                "Simulated internal server error",
                "Simulated quota exceeded",
            ]
            return random.choice(errors)
        return None

    def get_data(self):
        return dict(self.data)

    def load(self, data, versions_data):
        self.data = data or {}
        self.version_history = VersionHistory.from_dict(versions_data) if versions_data else VersionHistory()

    def SetAsync(self, key, value, user_ids=None, options=None):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("SetAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        ok, msg = self.rate_limiter.check_write(self.name)
        if not ok:
            if self.txn_log:
                self.txn_log.add("SetAsync", key, "error", msg)
            raise RuntimeError(msg)

        ok_schema, msg_schema = self.schema_validator.validate(key, value)
        if not ok_schema:
            if self.txn_log:
                self.txn_log.add("SetAsync", key, "schema_error", msg_schema)
            raise ValueError(f"Schema validation failed: {msg_schema}")

        fkey = self._full_key(key)
        self.data[fkey] = value
        self.version_history.record(fkey, value)
        if self.txn_log:
            self.txn_log.add("SetAsync", key, "ok", value=value)
        if self.verbose:
            print(f"  [debug] SetAsync '{key}' = {json.dumps(value)[:80]}")
        return True

    def GetAsync(self, key):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("GetAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        ok, msg = self.rate_limiter.check_read(self.name)
        if not ok:
            if self.txn_log:
                self.txn_log.add("GetAsync", key, "error", msg)
            raise RuntimeError(msg)

        fkey = self._full_key(key)
        val = self.data.get(fkey)
        if self.txn_log:
            self.txn_log.add("GetAsync", key, "ok", value=val)
        if self.verbose:
            print(f"  [debug] GetAsync '{key}' -> {json.dumps(val)[:80] if val else 'nil'}")
        return val

    def UpdateAsync(self, key, transform_fn):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("UpdateAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        ok, msg = self.rate_limiter.check_write(self.name)
        if not ok:
            if self.txn_log:
                self.txn_log.add("UpdateAsync", key, "error", msg)
            raise RuntimeError(msg)

        fkey = self._full_key(key)
        attempts = 0
        max_attempts = 5

        while attempts < max_attempts:
            attempts += 1
            old_val = self.data.get(fkey)
            new_val = transform_fn(old_val)
            if self.conflict_delay > 0 and random.random() < 0.15 and attempts == 1:
                time.sleep(self.conflict_delay * random.random())
                if self.txn_log:
                    self.txn_log.add("UpdateAsync", key, "conflict",
                                     detail=f"CONFLICT detected (attempt {attempts}), retrying")
                continue
            self.data[fkey] = new_val
            self.version_history.record(fkey, new_val)
            if attempts > 1:
                if self.txn_log:
                    self.txn_log.add("UpdateAsync", key, "ok",
                                     detail=f"retry succeeded on attempt {attempts}",
                                     value=new_val)
            else:
                if self.txn_log:
                    self.txn_log.add("UpdateAsync", key, "ok", value=new_val)
            return new_val

        raise RuntimeError(f"UpdateAsync failed after {max_attempts} attempts")

    def IncrementAsync(self, key, delta=1, user_ids=None, options=None):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("IncrementAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        ok, msg = self.rate_limiter.check_write(self.name)
        if not ok:
            if self.txn_log:
                self.txn_log.add("IncrementAsync", key, "error", msg)
            raise RuntimeError(msg)

        fkey = self._full_key(key)
        current = self.data.get(fkey, 0)
        if not isinstance(current, (int, float)):
            current = 0
        new_val = current + delta
        self.data[fkey] = new_val
        self.version_history.record(fkey, new_val)
        if self.txn_log:
            self.txn_log.add("IncrementAsync", key, "ok", value=new_val,
                             detail=f"{current} + {delta} = {new_val}")
        return new_val

    def RemoveAsync(self, key):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("RemoveAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        ok, msg = self.rate_limiter.check_write(self.name)
        if not ok:
            if self.txn_log:
                self.txn_log.add("RemoveAsync", key, "error", msg)
            raise RuntimeError(msg)

        fkey = self._full_key(key)
        if fkey in self.data:
            del self.data[fkey]
        if self.txn_log:
            self.txn_log.add("RemoveAsync", key, "ok")
        return True

    def ListKeysAsync(self, prefix="", page_size=50, cursor=None):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("ListKeysAsync", prefix, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        ok, msg = self.rate_limiter.check_read(self.name)
        if not ok:
            if self.txn_log:
                self.txn_log.add("ListKeysAsync", prefix, "error", msg)
            raise RuntimeError(msg)

        scope_prefix = f"{self.scope}:{self.name}:"
        matching = sorted([
            k[len(scope_prefix):]
            for k in self.data.keys()
            if k.startswith(scope_prefix) and (not prefix or k[len(scope_prefix):].startswith(prefix))
        ])
        if cursor:
            try:
                idx = matching.index(cursor)
                matching = matching[idx + 1:]
            except ValueError:
                pass
        page = matching[:page_size]
        next_cursor = page[-1] if len(matching) > page_size else None
        result = {"keys": page, "nextCursor": next_cursor}
        if self.txn_log:
            self.txn_log.add("ListKeysAsync", prefix, "ok",
                             detail=f"{len(page)} keys returned")
        return result

    def ListVersionsAsync(self, key, sort_direction="descending", min_date=None,
                          max_date=None, page_size=None):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("ListVersionsAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        fkey = self._full_key(key)
        versions = self.version_history.list_versions(fkey, sort_direction, min_date, max_date, page_size)
        if self.txn_log:
            self.txn_log.add("ListVersionsAsync", key, "ok",
                             detail=f"{len(versions)} versions")
        return versions

    def GetVersionAsync(self, key, version):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("GetVersionAsync", key, "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        fkey = self._full_key(key)
        v = self.version_history.get_version(fkey, version)
        if self.txn_log:
            self.txn_log.add("GetVersionAsync", key, "ok" if v else "not_found",
                             detail=f"version {version}")
        return v["value"] if v else None

    def set_schema(self, schema):
        self.schema_validator.set_schema("global", schema)


class OrderedDataStore(DataStore):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def GetSortedAsync(self, ascending=True, page_size=50, min_value=None, max_value=None):
        err = self._chaos_check()
        if err:
            if self.txn_log:
                self.txn_log.add("GetSortedAsync", "", "error", err)
            raise RuntimeError(f"[CHAOS] {err}")

        scope_prefix = f"{self.scope}:{self.name}:"
        entries = []
        for k, v in self.data.items():
            if k.startswith(scope_prefix):
                short_key = k[len(scope_prefix):]
                try:
                    num_val = float(v) if isinstance(v, (int, float)) else float(v)
                except (TypeError, ValueError):
                    num_val = 0
                if min_value is not None and num_val < min_value:
                    continue
                if max_value is not None and num_val > max_value:
                    continue
                entries.append((short_key, num_val))
        entries.sort(key=lambda x: x[1], reverse=not ascending)
        page = entries[:page_size]
        if self.txn_log:
            self.txn_log.add("GetSortedAsync", "", "ok",
                             detail=f"{len(page)} entries")
        return [{"key": k, "value": v} for k, v in page]


class DataStoreService:
    def __init__(self, store_path=DEFAULT_STORE_PATH, chaos=False, verbose=False):
        self.store_path = store_path
        self.chaos = chaos
        self.verbose = verbose
        self.stores = {}
        self.version_history = VersionHistory()
        self.txn_log = TransactionLog()
        self.rate_limiter = RateLimiter()
        self.schema_validator = SchemaValidator()

    def load(self):
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.version_history = VersionHistory.from_dict(state.get("versions", {}))
                self.txn_log = TransactionLog.from_list(state.get("transactions", []))
                data_map = state.get("data", {})
                for full_name, store_data in data_map.items():
                    store = self.stores.get(full_name)
                    if not store:
                        parts = full_name.split(":", 2)
                        scope = parts[0] if len(parts) > 1 else "global"
                        name = parts[-1]
                        store = DataStore(name=name, scope=scope, store_path=self.store_path,
                                          version_history=self.version_history,
                                          chaos=self.chaos, verbose=self.verbose,
                                          rate_limiter=self.rate_limiter,
                                          schema_validator=self.schema_validator,
                                          txn_log=self.txn_log)
                        self.stores[full_name] = store
                    store.data = store_data
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        state = {
            "versions": self.version_history.to_dict(),
            "transactions": self.txn_log.to_list(),
            "data": {},
        }
        for full_name, store in self.stores.items():
            state["data"][full_name] = store.data
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

    def GetDataStore(self, name, scope="global", options=None):
        full_name = f"{scope}:{name}"
        if full_name not in self.stores:
            store_cls = DataStore
            if options and options.get("ordered", False):
                store_cls = OrderedDataStore
            self.stores[full_name] = store_cls(
                name=name, scope=scope, store_path=self.store_path,
                version_history=self.version_history,
                chaos=self.chaos, verbose=self.verbose,
                rate_limiter=self.rate_limiter,
                schema_validator=self.schema_validator,
                txn_log=self.txn_log,
            )
        return self.stores[full_name]

    def GetOrderedDataStore(self, name, scope="global"):
        full_name = f"{scope}:{name}"
        if full_name not in self.stores:
            self.stores[full_name] = OrderedDataStore(
                name=name, scope=scope, store_path=self.store_path,
                version_history=self.version_history,
                chaos=self.chaos, verbose=self.verbose,
                rate_limiter=self.rate_limiter,
                schema_validator=self.schema_validator,
                txn_log=self.txn_log,
            )
        return self.stores[full_name]

    def all_keys(self):
        keys = set()
        for store in self.stores.values():
            for k in store.data.keys():
                keys.add(k)
        return sorted(keys)

    def key_count(self):
        return sum(len(s.data) for s in self.stores.values())

    def version_count(self):
        return sum(len(v) for v in self.version_history.versions.values())


class LuauScriptParser:
    def __init__(self, service, verbose=False):
        self.service = service
        self.verbose = verbose
        self.variables = {}
        self.operations = 0
        self.succeeded = 0
        self.conflicts = 0
        self.errors = 0

    def _parse_value(self, raw):
        raw = raw.strip()
        if raw == "nil" or raw == "":
            return None
        if raw == "true":
            return True
        if raw == "false":
            return False
        if re.match(r"^-?\d+(\.\d+)?$", raw):
            return float(raw) if "." in raw else int(raw)
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1]
        if raw.startswith("{") and raw.endswith("}"):
            return self._parse_table(raw)
        if raw.startswith("{"):
            return self._parse_table(raw)
        return raw

    def _parse_table(self, raw):
        raw = raw.strip()
        if raw == "{}":
            return {}
        inner = raw[1:-1].strip() if raw.endswith("}") else raw[1:].strip()
        result = {}
        i = 0
        pairs = self._split_table_entries(inner)
        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue
            if "=" in pair:
                m = re.match(r'\[?["\']?(\w+)["\']?\]?\s*=\s*(.+)', pair)
                if m:
                    key = m.group(1)
                    val = self._parse_value(m.group(2))
                    result[key] = val
                    continue
            result[i] = self._parse_value(pair)
            i += 1
        return result

    def _split_table_entries(self, inner):
        entries = []
        depth = 0
        current = ""
        for ch in inner:
            if ch == "{" or ch == "[":
                depth += 1
            elif ch == "}" or ch == "]":
                depth -= 1
            if ch == "," and depth == 0:
                entries.append(current)
                current = ""
            else:
                current += ch
        if current.strip():
            entries.append(current)
        return entries

    def _resolve_var(self, name):
        return self.variables.get(name, name)

    def parse_and_run(self, script_path):
        if not os.path.exists(script_path):
            print(f"  Error: Script not found: {script_path}")
            return

        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("--"):
                continue

            try:
                self._process_line(line_stripped)
            except Exception as e:
                self.errors += 1
                print(f"  Line {line_num}: ERROR - {e}")
                if self.verbose:
                    traceback.print_exc()

    def _process_line(self, line):
        assign_match = re.match(
            r'local\s+(\w+)\s*=\s*(\w+)(?::(\w+)\("([^"]*)"(?:,\s*"([^"]*)")?(?:,\s*\{([^}]*)\})?\))?\s*$',
            line
        )
        if assign_match and assign_match.group(3):
            var_name = assign_match.group(1)
            obj = assign_match.group(2)
            method = assign_match.group(3)
            name = assign_match.group(4)
            scope = assign_match.group(5) or "global"

            if method == "GetDataStore":
                store = self.service.GetDataStore(name, scope)
                self.variables[var_name] = store
                self.operations += 1
                self.succeeded += 1
                if self.verbose:
                    print(f"  [sim] Created DataStore '{name}' as '{var_name}'")
            elif method == "GetOrderedDataStore":
                store = self.service.GetOrderedDataStore(name, scope)
                self.variables[var_name] = store
                self.operations += 1
                self.succeeded += 1
                if self.verbose:
                    print(f"  [sim] Created OrderedDataStore '{name}' as '{var_name}'")
            return

        method_match = re.match(r'(\w+):(\w+)\((.*)\)$', line)
        if method_match:
            var_name = method_match.group(1)
            method = method_match.group(2)
            args_raw = method_match.group(3)
            store = self.variables.get(var_name)
            if not store:
                return

            args = self._parse_args(args_raw)
            self.operations += 1

            try:
                result = self._execute_method(store, method, args, args_raw)
                if result is not None and self.verbose:
                    print(f"  [sim] {method} -> {json.dumps(result)[:80] if not isinstance(result, bool) else result}")
                self.succeeded += 1
            except Exception as e:
                if "CONFLICT" in str(e).upper() or "retry" in str(e).lower():
                    self.conflicts += 1
                    self.succeeded += 1
                else:
                    self.errors += 1
                    raise

    def _parse_args(self, raw):
        raw = raw.strip()
        if not raw:
            return []
        args = []
        depth = 0
        current = ""
        in_string = False
        string_char = None
        i = 0
        while i < len(raw):
            ch = raw[i]
            if in_string:
                current += ch
                if ch == string_char and (i == 0 or raw[i - 1] != "\\"):
                    in_string = False
            elif ch == '"' or ch == "'":
                in_string = True
                string_char = ch
                current += ch
            elif ch == "{" or ch == "[":
                depth += 1
                current += ch
            elif ch == "}" or ch == "]":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += ch
            i += 1
        if current.strip():
            args.append(current.strip())
        return args

    def _execute_method(self, store, method, args, args_raw):
        if method == "SetAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            value = self._parse_value(args[1]) if len(args) > 1 else None
            return store.SetAsync(key, value)

        elif method == "GetAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            return store.GetAsync(key)

        elif method == "UpdateAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            if len(args) > 1 and "function" in args_raw:
                return store.UpdateAsync(key, lambda old: old or 0)
            return store.UpdateAsync(key, lambda old: old)

        elif method == "IncrementAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            delta = self._parse_value(args[1]) if len(args) > 1 else 1
            if isinstance(delta, str):
                try:
                    delta = int(delta)
                except ValueError:
                    delta = 0
            return store.IncrementAsync(key, delta if isinstance(delta, (int, float)) else 1)

        elif method == "RemoveAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            return store.RemoveAsync(key)

        elif method == "ListKeysAsync":
            prefix = self._parse_value(args[0]) if len(args) > 0 else ""
            return store.ListKeysAsync(prefix or "")

        elif method == "ListVersionsAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            return store.ListVersionsAsync(key)

        elif method == "GetVersionAsync":
            key = self._parse_value(args[0]) if len(args) > 0 else None
            version = int(self._parse_value(args[1])) if len(args) > 1 else 1
            return store.GetVersionAsync(key, version)

        elif method == "GetSortedAsync":
            ascending = True
            if len(args) > 0:
                a = self._parse_value(args[0])
                if isinstance(a, bool):
                    ascending = a
            page_size = 50
            if len(args) > 1:
                try:
                    page_size = int(self._parse_value(args[1]))
                except (ValueError, TypeError):
                    pass
            min_val = None
            if len(args) > 2:
                try:
                    min_val = float(self._parse_value(args[2]))
                except (ValueError, TypeError):
                    pass
            max_val = None
            if len(args) > 3:
                try:
                    max_val = float(self._parse_value(args[3]))
                except (ValueError, TypeError):
                    pass
            return store.GetSortedAsync(ascending, page_size, min_val, max_val)

        return None


class WebHandler(BaseHTTPRequestHandler):
    _service = None
    _verbose = False

    def log_message(self, format, *args):
        if WebHandler._verbose:
            super().log_message(format, *args)

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._serve_ui()
        elif path == "/api/transactions":
            svc = WebHandler._service
            self._send_json(svc.txn_log.recent(200))
        elif path == "/api/keys":
            svc = WebHandler._service
            keys = []
            for full_name, store in svc.stores.items():
                for k in store.data:
                    keys.append({"key": k, "store": full_name, "value": store.data[k]})
            self._send_json(keys)
        elif path == "/api/data":
            key = qs.get("key", [None])[0]
            if key:
                svc = WebHandler._service
                for store in svc.stores.values():
                    val = store.data.get(key)
                    if val is not None:
                        self._send_json({"key": key, "value": val})
                        return
                self._send_json({"error": "Key not found"}, 404)
            else:
                self._send_json({"error": "Missing key param"}, 400)
        elif path == "/api/dump":
            svc = WebHandler._service
            dump = {}
            for full_name, store in svc.stores.items():
                dump[full_name] = store.get_data()
            self._send_json(dump)
        elif path == "/api/export":
            svc = WebHandler._service
            state = {
                "versions": svc.version_history.to_dict(),
                "transactions": svc.txn_log.to_list(),
                "data": {n: s.data for n, s in svc.stores.items()},
            }
            filename = qs.get("filename", ["datastore-export.json"])[0]
            body = json.dumps(state, indent=2, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length) if length > 0 else b"{}"

        try:
            body = json.loads(body_raw)
        except json.JSONDecodeError:
            body = {}

        svc = WebHandler._service

        if path == "/api/operation":
            op = body.get("operation")
            store_name = body.get("store", "global:default")
            key = body.get("key", "")
            value = body.get("value")

            try:
                store = svc.GetDataStore(store_name.split(":")[-1], store_name.split(":")[0])
            except Exception:
                store = svc.GetDataStore("default", "global")

            try:
                if op == "set":
                    store.SetAsync(key, value)
                    svc.save()
                    self._send_json({"status": "ok", "key": key})
                elif op == "get":
                    val = store.GetAsync(key)
                    self._send_json({"status": "ok", "key": key, "value": val})
                elif op == "update":
                    new_val = store.UpdateAsync(key, lambda old: {**(old or {}), **(value or {})})
                    svc.save()
                    self._send_json({"status": "ok", "key": key, "value": new_val})
                elif op == "remove":
                    store.RemoveAsync(key)
                    svc.save()
                    self._send_json({"status": "ok", "key": key})
                elif op == "increment":
                    delta = body.get("delta", 1)
                    new_val = store.IncrementAsync(key, delta)
                    svc.save()
                    self._send_json({"status": "ok", "key": key, "value": new_val})
                else:
                    self._send_json({"error": f"Unknown operation: {op}"}, 400)
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)

        elif path == "/api/import":
            svc.version_history = VersionHistory.from_dict(body.get("versions", {}))
            svc.txn_log = TransactionLog.from_list(body.get("transactions", []))
            data_map = body.get("data", {})
            for full_name, store_data in data_map.items():
                store = svc.GetDataStore(full_name.split(":")[-1] if ":" in full_name else full_name,
                                         full_name.split(":")[0] if ":" in full_name else "global")
                store.data = store_data
            svc.save()
            self._send_json({"status": "ok", "message": "Data imported"})

        elif path == "/api/conflict":
            key = body.get("key", "test_conflict")
            store_name = body.get("store", "global:default")
            try:
                store = svc.GetDataStore(store_name.split(":")[-1], store_name.split(":")[0])
            except Exception:
                store = svc.GetDataStore("default", "global")
            store.conflict_delay = 0.5
            time.sleep(store.conflict_delay)
            try:
                new_val = store.UpdateAsync(key, lambda old: old)
                svc.save()
                self._send_json({"status": "ok", "value": new_val})
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)

        elif path == "/api/create-store":
            name = body.get("name", "default")
            scope = body.get("scope", "global")
            ordered = body.get("ordered", False)
            if ordered:
                store = svc.GetOrderedDataStore(name, scope)
            else:
                store = svc.GetDataStore(name, scope)
            self._send_json({"status": "ok", "store": f"{scope}:{name}"})

        else:
            self._send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_ui(self):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DataStore Debugger</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Cascadia Code',Consolas,monospace;background:#0d1117;color:#c9d1d9;padding:16px}
h1{font-size:18px;color:#58a6ff;margin-bottom:4px}
h2{font-size:14px;color:#8b949e;margin:16px 0 8px;border-bottom:1px solid #21262d;padding-bottom:4px}
.panel{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;margin-bottom:12px}
.row{display:flex;gap:12px;flex-wrap:wrap}
.col{flex:1;min-width:280px}
.log-entry{font-size:12px;padding:2px 4px;border-bottom:1px solid #21262d}
.log-entry.ok{color:#3fb950}
.log-entry.error{color:#f85149}
.log-entry.conflict{color:#d2991d}
.txn-time{color:#8b949e;margin-right:8px}
.btn{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:6px 12px;
     border-radius:6px;cursor:pointer;font-family:inherit;font-size:12px}
.btn:hover{background:#30363d;border-color:#8b949e}
.btn.primary{background:#1f6feb;border-color:#1f6feb}
.btn.danger{background:#da3633;border-color:#da3633}
.btn.small{padding:3px 8px;font-size:11px}
input,select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px 8px;
             border-radius:6px;font-family:inherit;font-size:12px;width:100%}
label{font-size:11px;color:#8b949e;display:block;margin:6px 0 2px}
pre{font-size:11px;background:#0d1117;border-radius:4px;padding:8px;overflow:auto;max-height:200px}
#log{max-height:400px;overflow-y:auto}
.card{background:#0d1117;border-radius:4px;padding:8px;margin:4px 0;font-size:12px}
.card .key{color:#58a6ff}
.card .val{color:#7ee787}
.card .meta{color:#8b949e;font-size:10px}
.badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;margin-left:4px}
.badge.ok{background:#1a3b22;color:#3fb950}
.badge.err{background:#3b1a1a;color:#f85149}
.badge.conf{background:#3b2e1a;color:#d2991d}
.stats{display:flex;gap:16px;font-size:12px;margin:8px 0}
.stat{text-align:center}
.stat-val{font-size:18px;color:#58a6ff}
.stat-label{color:#8b949e;font-size:10px}
</style>
</head>
<body>
<h1>&#x1f4be; DataStore Debugger</h1>
<div id="stats" class="stats">
  <div class="stat"><div class="stat-val" id="stat-keys">0</div><div class="stat-label">Keys</div></div>
  <div class="stat"><div class="stat-val" id="stat-ops">0</div><div class="stat-label">Ops</div></div>
  <div class="stat"><div class="stat-val" id="stat-ok">0</div><div class="stat-label">OK</div></div>
  <div class="stat"><div class="stat-val" id="stat-err">0</div><div class="stat-label">Errors</div></div>
</div>

<div class="row">
  <div class="col">
    <div class="panel">
      <h2>&#x2699; Operations</h2>
      <label>DataStore</label>
      <select id="op-store"><option value="global:default">global:default</option></select>
      <label>Key</label>
      <input id="op-key" placeholder="key name">
      <label>Value (JSON)</label>
      <input id="op-value" placeholder='{"field":123}'>
      <label>Delta</label>
      <input id="op-delta" value="1" type="number">
      <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn primary" onclick="doOp('set')">SetAsync</button>
        <button class="btn" onclick="doOp('get')">GetAsync</button>
        <button class="btn" onclick="doOp('update')">UpdateAsync</button>
        <button class="btn" onclick="doOp('increment')">IncrementAsync</button>
        <button class="btn danger" onclick="doOp('remove')">RemoveAsync</button>
      </div>
    </div>

    <div class="panel">
      <h2>&#x26a1; Conflict Simulator</h2>
      <label>Key to test</label>
      <input id="conf-key" value="test-conflict">
      <div style="margin-top:6px">
        <button class="btn danger" onclick="triggerConflict()">Trigger Concurrent UpdateAsync</button>
      </div>
      <div id="conf-result" style="margin-top:8px;font-size:12px"></div>
    </div>

    <div class="panel">
      <h2>&#x1f4e6; Create Store</h2>
      <div style="display:flex;gap:8px;align-items:end">
        <div><label>Scope</label><input id="ns-scope" value="global" style="width:100px"></div>
        <div><label>Name</label><input id="ns-name" value="default" style="width:160px"></div>
        <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px">
          <input type="checkbox" id="ns-ordered" style="width:auto">
          <label style="margin:0">Ordered</label>
        </div>
        <button class="btn primary small" onclick="createStore()">Create</button>
      </div>
    </div>
  </div>

  <div class="col">
    <div class="panel">
      <h2>&#x1f4cb; Transaction Log</h2>
      <div id="log">Loading...</div>
    </div>
  </div>
</div>

<div class="row">
  <div class="col">
    <div class="panel">
      <h2>&#x1f4ca; Data Browser</h2>
      <div style="display:flex;gap:8px;margin-bottom:8px">
        <button class="btn small" onclick="loadKeys()">Refresh</button>
        <button class="btn small" onclick="exportData()">Export</button>
        <button class="btn small" onclick="document.getElementById('import-file').click()">Import</button>
        <input type="file" id="import-file" style="display:none" accept=".json" onchange="importData(event)">
      </div>
      <div id="keys-list">Click Refresh to load</div>
    </div>
  </div>
</div>

<script>
var base = '';
var poll = null;

function api(path, method, body) {
  var opts = {method: method || 'GET', headers: {'Content-Type': 'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  return fetch(base + path, opts).then(function(r) { return r.json(); });
}

function loadLog() {
  api('/api/transactions').then(function(data) {
    var out = '';
    var ok = 0, err = 0, conf = 0;
    (data||[]).slice().reverse().forEach(function(t) {
      var cls = t.status === 'ok' ? 'ok' : (t.status === 'conflict' ? 'conflict' : 'error');
      var icon = t.operation === 'SetAsync' ? '\uD83D\uDCDD' :
                 t.operation === 'GetAsync' ? '\uD83D\uDD0D' :
                 t.operation === 'UpdateAsync' ? '\uD83D\uDD04' :
                 t.operation === 'IncrementAsync' ? '\u2795' :
                 t.operation === 'RemoveAsync' ? '\u274C' : '\u2139\uFE0F';
      out += '<div class="log-entry ' + cls + '">';
      out += '<span class="txn-time">[' + (t.timestamp||'').split('T')[1] + ']</span>';
      out += icon + ' ' + t.operation + ' ' + t.key;
      if (t.detail) out += ' — ' + t.detail;
      if (t.value !== undefined && t.value !== null) {
        out += ' → ' + JSON.stringify(t.value).substring(0, 60);
      }
      if (t.status === 'ok') ok++;
      else if (t.status === 'conflict' || (t.detail||'').toLowerCase().indexOf('conflict')>=0) conf++;
      else err++;
      out += '</div>';
    });
    document.getElementById('log').innerHTML = out || 'No transactions yet';
    document.getElementById('stat-ops').textContent = (data||[]).length;
    document.getElementById('stat-ok').textContent = ok;
    document.getElementById('stat-err').textContent = err;
  });
}

function loadKeys() {
  api('/api/keys').then(function(data) {
    var out = '';
    var stores = {};
    (data||[]).forEach(function(k) { stores[k.store] = (stores[k.store]||0) + 1; });
    var total = 0;
    for (var s in stores) {
      total += stores[s];
      out += '<div style="font-size:11px;color:#8b949e;margin-top:4px">Store: ' + s + ' (' + stores[s] + ' keys)</div>';
    }
    document.getElementById('stat-keys').textContent = total;
    (data||[]).slice(0,50).forEach(function(k) {
      var v = typeof k.value === 'object' ? JSON.stringify(k.value) : k.value;
      out += '<div class="card"><span class="key">' + k.key + '</span> ';
      out += '<span class="val">' + (v||'nil') + '</span>';
      out += ' <span class="meta">[' + k.store + ']</span></div>';
    });
    document.getElementById('keys-list').innerHTML = out || 'No keys stored';
  });
}

function doOp(op) {
  var store = document.getElementById('op-store').value;
  var key = document.getElementById('op-key').value;
  var valRaw = document.getElementById('op-value').value;
  var value = null;
  try { value = JSON.parse(valRaw); } catch(e) { value = valRaw; }
  var body = {operation: op, store: store, key: key, value: value,
              delta: parseInt(document.getElementById('op-delta').value) || 1};
  api('/api/operation', 'POST', body).then(function(r) {
    loadLog(); loadKeys();
  });
  document.getElementById('op-value').value = '';
}

function triggerConflict() {
  var key = document.getElementById('conf-key').value;
  var store = document.getElementById('op-store').value;
  var promises = [];
  for (var i = 0; i < 3; i++) {
    promises.push(api('/api/conflict', 'POST', {key: key, store: store}));
  }
  Promise.all(promises).then(function(r) {
    document.getElementById('conf-result').innerHTML =
      '<span style="color:#3fb950">Simulated ' + r.length + ' concurrent operations. Check log.</span>';
    loadLog(); loadKeys();
  });
}

function createStore() {
  var name = document.getElementById('ns-name').value;
  var scope = document.getElementById('ns-scope').value;
  var ordered = document.getElementById('ns-ordered').checked;
  api('/api/create-store', 'POST', {name: name, scope: scope, ordered: ordered}).then(function(r) {
    var opt = document.createElement('option');
    opt.value = r.store; opt.textContent = r.store;
    document.getElementById('op-store').appendChild(opt);
  });
}

function exportData() {
  window.open(base + '/api/export');
}

function importData(e) {
  var file = e.target.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function(ev) {
    try {
      var data = JSON.parse(ev.target.result);
      api('/api/import', 'POST', data).then(function(r) {
        loadLog(); loadKeys();
      });
    } catch(err) {
      alert('Invalid JSON file');
    }
  };
  reader.readAsText(file);
}

loadLog();
loadKeys();
poll = setInterval(function() { loadLog(); }, 2000);
</script>
</body>
</html>"""
        self._send_html(html)


def format_value(value):
    if value is None:
        return "nil"
    s = json.dumps(value, default=str)
    return s if len(s) <= 60 else s[:57] + "..."

def run_cli(args):
    service = DataStoreService(
        store_path=args.store,
        chaos=args.chaos,
        verbose=args.verbose,
    )
    service.load()

    print(f"\n\U0001f4be DataStore Debugger \u2014 local mode")
    print(f"{BOARD * 40}\n")

    n_keys = service.key_count()
    n_versions = service.version_count()
    print(f"  \U0001f4c2 Store: {args.store} ({n_keys} keys, {n_versions} versions)")

    if args.dump:
        print(f"\n  \U0001f4e6 Data dump:")
        for full_name, store in service.stores.items():
            print(f"\n  [{full_name}]")
            for k, v in store.data.items():
                print(f"    {k} = {format_value(v)}")
        print()
        return

    if args.import_script:
        print(f"\n  Running import script: {args.import_script}\n")
        parser = LuauScriptParser(service, verbose=args.verbose)
        parser.parse_and_run(args.import_script)

        service.save()

        ops = parser.operations
        ok = parser.succeeded
        conflicts = parser.conflicts
        errors = parser.errors

        recent = service.txn_log.recent(ops)
        for txn in recent:
            ts = txn["timestamp"].split("T")[1] if "T" in txn["timestamp"] else txn["timestamp"]
            icon = {
                "SetAsync": "\U0001f4dd", "GetAsync": "\U0001f50d",
                "UpdateAsync": "\U0001f504", "IncrementAsync": "\u2795",
                "RemoveAsync": "\u274c", "ListKeysAsync": "\U0001f4cb",
                "ListVersionsAsync": "\U0001f4dc",
            }.get(txn["operation"], "\u2139\ufe0f")

            status_icon = "\u2713" if txn["status"] == "ok" else (
                "\u26a0\ufe0f" if txn["status"] == "conflict" else "\u2717")
            detail = f" \u2014 {txn['detail']}" if txn.get("detail") else ""
            val_str = ""
            if txn.get("value") is not None:
                val_str = f" \u2192 {format_value(txn['value'])}"

            print(f"  [{ts}] {icon} {txn['operation']:20s} {txn['key']:20s} {val_str} {detail} {status_icon}")

        print(f"\n  \U0001f4ca Summary: {ops} operations, {ok} succeeded, "
              f"{conflicts} conflict{'' if conflicts == 1 else 's'} "
              f"({'(auto-resolved)' if conflicts > 0 else ''}), {errors} error{'' if errors == 1 else 's'}")
        print()
        return

    recent = service.txn_log.recent(20)
    if recent:
        print(f"\n  Recent transactions:")
        for txn in recent:
            ts = txn["timestamp"].split("T")[1] if "T" in txn["timestamp"] else txn["timestamp"]
            icon = {
                "SetAsync": "\U0001f4dd", "GetAsync": "\U0001f50d",
                "UpdateAsync": "\U0001f504", "IncrementAsync": "\u2795",
                "RemoveAsync": "\u274c",
            }.get(txn["operation"], "\u2139\ufe0f")
            status_icon = "\u2713" if txn["status"] == "ok" else "\u2717"
            val_str = f" \u2192 {format_value(txn['value'])}" if txn.get("value") is not None else ""
            print(f"  [{ts}] {icon} {txn['operation']:20s} {txn['key']:20s} {val_str} {status_icon}")

    else:
        print("\n  No transactions recorded. Use --import-script or --web to interact.\n")

    print(f"\n  \U0001f4c2 Store: {args.store} ({service.key_count()} keys loaded)")
    print(f"  \U0001f4dc Versions tracked: {service.version_count()}\n")


def main():
    parser = argparse.ArgumentParser(
        description="DataStore Debugger - Local Roblox DataStore Simulator for Luau Developers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  datastore-debugger.py --import-script test_datastore.luau\n"
               "  datastore-debugger.py --web\n"
               "  datastore-debugger.py --chaos --import-script my_script.luau --verbose\n"
               "  datastore-debugger.py --dump\n",
    )
    parser.add_argument("-s", "--store", default=DEFAULT_STORE_PATH,
                        help=f"Path to JSON data file (default: {DEFAULT_STORE_PATH})")
    parser.add_argument("-w", "--web", action="store_true",
                        help="Start HTTP server with interactive web UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"HTTP server port (default: {DEFAULT_PORT})")
    parser.add_argument("-i", "--import-script",
                        help="Path to a Luau script to simulate against")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose debug output")
    parser.add_argument("--chaos", action="store_true",
                        help="Randomly inject errors (30%% of operations fail)")
    parser.add_argument("--dump", action="store_true",
                        help="Show all stored data and exit")
    args = parser.parse_args()

    if args.web:
        WebHandler._service = DataStoreService(
            store_path=args.store,
            chaos=args.chaos,
            verbose=args.verbose,
        )
        WebHandler._service.load()
        WebHandler._verbose = args.verbose

        port = args.port
        server = HTTPServer(("0.0.0.0", port), WebHandler)
        url = f"http://localhost:{port}"
        print(f"\n\U0001f4be DataStore Debugger \u2014 web UI mode")
        print(f"{BOARD * 40}")
        print(f"\n  \U0001f310 Serving at: {url}")
        print(f"  \U0001f4c2 Store file: {os.path.abspath(args.store)}")
        print(f"  \n  Opening browser...")
        print(f"  Press Ctrl+C to stop\n")

        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n  Shutting down...")
            WebHandler._service.save()
            server.shutdown()
    else:
        run_cli(args)
        if not args.import_script and not args.dump:
            print("  Tip: Use --import-script <file.luau> to simulate operations\n"
                  "       Use --web to launch the interactive web UI\n"
                  "       Use --chaos to inject random errors\n"
                  "       Use --dump to show all data\n")

if __name__ == "__main__":
    main()
