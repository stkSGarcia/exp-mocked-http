#!/usr/bin/env python3
"""YAML-driven HTTP mock server."""

import base64
import hashlib
import hmac as _hmac
import html
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import yaml
from jinja2 import Environment, StrictUndefined

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_LOG_LEVELS = {
    "debug": logging.DEBUG, "info": logging.INFO,
    "warn": logging.WARNING, "error": logging.ERROR,
}

TEMPLATES_DIR = os.environ.get("HM_TEMPLATES_DIR", "./templates")
HTTP_PORT     = int(os.environ.get("HM_HTTP_PORT", "9999"))
HTTP_HOST     = os.environ.get("HM_HTTP_HOST", "0.0.0.0")
_LOG_LEVEL    = _LOG_LEVELS.get(os.environ.get("HM_LOG_LEVEL", "info").lower(), logging.INFO)
REDIS_TYPE    = os.environ.get("HM_REDIS_TYPE", "memory")
REDIS_URL     = os.environ.get("HM_REDIS_URL", "redis://redis:6379")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"level": record.levelname.lower(), "message": record.getMessage()}
        if hasattr(record, "_extra"):
            entry.update(record._extra)
        return json.dumps(entry)


_logger = logging.getLogger("hmock")
_logger.setLevel(_LOG_LEVEL)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_JsonFormatter())
_logger.addHandler(_sh)


def _log(level: int, msg: str, **fields):
    if _logger.isEnabledFor(level):
        record = _logger.makeRecord(_logger.name, level, "", 0, msg, (), None)
        if fields:
            record._extra = fields
        _logger.handle(record)

# ---------------------------------------------------------------------------
# HeaderMap
# ---------------------------------------------------------------------------

class HeaderMap:
    def __init__(self, headers: dict):
        self._h = {k.lower(): v for k, v in headers.items()}

    def Get(self, name: str) -> str:
        return self._h.get(name.lower(), "")

# ---------------------------------------------------------------------------
# gJsonPath helper
# ---------------------------------------------------------------------------

def _gjson_path(expr: str, data: str) -> str:
    if not data:
        return ""
    parsed = json.loads(data)  # raises on invalid JSON
    parts = expr.split(".")
    node = parsed
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == "#":
            # count
            if isinstance(node, list):
                return str(len(node))
            return ""
        if i + 1 < len(parts) and part == "#":
            pass  # handled above
        # array wildcard: current part is "#" already handled; check next is a field
        if part == "#" and i + 1 < len(parts):
            field = parts[i + 1]
            if isinstance(node, list):
                return "\n".join(str(item.get(field, "")) if isinstance(item, dict) else "" for item in node)
            return ""
        if isinstance(node, list):
            if part.isdigit():
                idx = int(part)
                if idx >= len(node):
                    return ""
                node = node[idx]
            else:
                return ""
        elif isinstance(node, dict):
            node = node.get(part)
            if node is None:
                return ""
        else:
            return ""
        i += 1
    if isinstance(node, (dict, list)):
        return json.dumps(node)
    return str(node) if node is not None else ""


def _gjson_path_safe(expr: str, data: str) -> str:
    """Wrapper that handles the '#.field' wildcard split across two parts."""
    if not data:
        return ""
    parts = expr.split(".")
    # detect wildcard pattern: <prefix>.#.<field> or just #.<field>
    for i, part in enumerate(parts):
        if part == "#" and i + 1 < len(parts):
            # navigate to the list at parts[:i], then collect fields
            parsed = json.loads(data)
            node = parsed
            for p in parts[:i]:
                if isinstance(node, list):
                    node = node[int(p)] if p.isdigit() else None
                elif isinstance(node, dict):
                    node = node.get(p)
                if node is None:
                    return ""
            field = parts[i + 1]
            if isinstance(node, list):
                vals = []
                for item in node:
                    if isinstance(item, dict) and field in item:
                        vals.append(str(item[field]))
                    elif isinstance(item, dict):
                        vals.append("")
                return "\n".join(vals)
            return ""
    return _gjson_path(expr, data)

# ---------------------------------------------------------------------------
# Redis Backend
# ---------------------------------------------------------------------------

def _make_redis_client():
    if REDIS_TYPE == "redis":
        import redis as _redis_lib
        return _redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
    import fakeredis
    return fakeredis.FakeRedis(decode_responses=True)


_REDIS = _make_redis_client()


def _redis_do(cmd: str, *args) -> str:
    result = _REDIS.execute_command(cmd.upper(), *[str(a) for a in args])
    if result is None:
        return ""
    if isinstance(result, bool):
        return "OK" if result else "0"
    if isinstance(result, (int, float)):
        return str(result)
    if isinstance(result, bytes):
        return result.decode("utf-8")
    if isinstance(result, list):
        return ";;".join(
            "" if v is None else (v.decode("utf-8") if isinstance(v, bytes) else str(v))
            for v in result
        )
    if isinstance(result, dict):
        parts: list[str] = []
        for k, v in result.items():
            parts.append(k.decode("utf-8") if isinstance(k, bytes) else str(k))
            parts.append("" if v is None else (v.decode("utf-8") if isinstance(v, bytes) else str(v)))
        return ";;".join(parts)
    return str(result)


# ---------------------------------------------------------------------------
# Template Engine
# ---------------------------------------------------------------------------

def _make_jinja_env() -> Environment:
    from jsonpath_ng import parse as _jp_parse
    from lxml import etree as _etree

    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True)

    def _json_path(expr: str, data: str) -> str:
        if not data:
            return ""
        parsed = json.loads(data)
        matches = _jp_parse(expr).find(parsed)
        if not matches:
            return ""
        v = matches[0].value
        return json.dumps(v) if isinstance(v, (dict, list)) else str(v)

    def _xml_path(expr: str, data: str) -> str:
        if not data:
            return ""
        root = _etree.fromstring(data.encode())
        results = root.xpath(expr)
        if not results:
            return ""
        node = results[0]
        if isinstance(node, str):
            return node
        return node.text or ""

    def _regex_find_all_submatch(pattern: str, s: str) -> list:
        m = re.search(pattern, s)
        if not m:
            return []
        return [m.group(0)] + list(m.groups(""))

    def _regex_find_first_submatch(pattern: str, s: str) -> str:
        m = re.search(pattern, s)
        if not m or not m.lastindex:
            return ""
        return m.group(1)

    extras = {
        # Comparison
        "eq":  lambda a, b: a == b,
        "ne":  lambda a, b: a != b,
        "lt":  lambda a, b: a < b,
        "gt":  lambda a, b: a > b,
        "le":  lambda a, b: a <= b,
        "ge":  lambda a, b: a >= b,
        # Logic
        "and": lambda a, b: a and b,
        "or":  lambda a, b: a or b,
        "not": lambda a: not a,
        # Output
        "print":   str,
        "printf":  lambda fmt, *args: fmt % args,
        "println": lambda s: str(s) + "\n",
        # Encoding
        "html":     lambda s: s,
        "js":       lambda s: json.dumps(str(s)),
        "urlquery": lambda s: s,
        # Collections
        "len":   len,
        "index": lambda seq, i: seq[i],
        "call":  lambda f, *args: f(*args),
        # String
        "contains":  lambda s, sub: sub in str(s),
        "hasPrefix": lambda s, prefix: str(s).startswith(prefix),
        "hasSuffix": lambda s, suffix: str(s).endswith(suffix),
        "replace":   lambda s, old, new: str(s).replace(old, new),
        "trim":      lambda s, chars=None: str(s).strip(chars),
        "upper":     lambda s: str(s).upper(),
        "lower":     lambda s: str(s).lower(),
        "title":     lambda s: str(s).title(),
        "split":     lambda s, sep: str(s).split(sep),
        "splitList": lambda sep, s: str(s).split(sep),
        "join":      lambda lst, sep="": sep.join(str(x) for x in lst),
        "repeat":    lambda s, n: str(s) * int(n),
        "nospace":   lambda s: str(s).replace(" ", ""),
        "toString":  str,
        # Comparison helpers
        "default":  lambda val, d="": val if val else d,
        "empty":    lambda val: not bool(val),
        "coalesce": lambda *args: next((a for a in args if a), args[-1] if args else ""),
        "ternary":  lambda cond, t, f: t if cond else f,
        # Encoding
        "b64enc": lambda s: base64.b64encode(str(s).encode()).decode(),
        "b64dec": lambda s: base64.b64decode(str(s).encode()).decode(),
        # Environment
        "env": lambda name: os.environ.get(name, ""),
        # Math
        "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b,
        "mul": lambda a, b: a * b,
        "div": lambda a, b: a / b,
        "mod": lambda a, b: a % b,
        "max": max,
        "min": min,
        # UUID
        "uuidv4": lambda: str(uuid.uuid4()),
        "uuidv5": lambda data: str(uuid.uuid5(uuid.NAMESPACE_OID, str(data))),
        # JSON / XML querying
        "jsonPath":  _json_path,
        "gJsonPath": _gjson_path_safe,
        "xmlPath":   _xml_path,
        # Regex
        "regexFindAllSubmatch":   _regex_find_all_submatch,
        "regexFindFirstSubmatch": _regex_find_first_submatch,
        # Crypto
        "hmacSHA256": lambda secret, data: _hmac.new(
            str(secret).encode(), str(data).encode(), hashlib.sha256
        ).hexdigest(),
        # Misc
        "isLastIndex":     lambda index, array: int(index) == len(array) - 1,
        "htmlEscapeString": lambda s: html.escape(str(s), quote=True),
        # Redis
        "redisDo": _redis_do,
    }
    env.globals.update(extras)
    env.filters.update(extras)
    return env


_JINJA = _make_jinja_env()
_BLOCK_RE = re.compile(r"\{\{-?.*?-?\}\}", re.DOTALL)
_CTX_VAR_RE = re.compile(r"(?<![.\w])\.(HTTP\w+)")


def _preprocess(s: str) -> str:
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\t", " ")
    stack: list[str] = []

    def transform(m: re.Match) -> str:
        raw = m.group(0)
        left  = "{{-" if raw.startswith("{{-") else "{{"
        right = "-}}" if raw.endswith("-}}") else "}}"
        inner = raw[len(left):-len(right)]

        # Strip leading dot from HTTP* context vars: .HTTPHeader -> HTTPHeader
        inner = _CTX_VAR_RE.sub(r"\1", inner)

        # .Method "a" "b" -> .Method("a", "b")
        inner = re.sub(
            r"\.(\w+)((?:\s+\"[^\"]*\")+)",
            lambda x: f'.{x.group(1)}(' + ", ".join(re.findall(r'"[^"]*"', x.group(2))) + ")",
            inner,
        )
        # | func "a" "b" -> | func("a", "b")
        inner = re.sub(
            r"(\|\s*\w+)((?:\s+\"[^\"]*\")+)",
            lambda x: x.group(1) + "(" + ", ".join(re.findall(r'"[^"]*"', x.group(2))) + ")",
            inner,
        )
        # backtick raw strings
        inner = re.sub(r"`([^`]*)`", r'"\1"', inner)

        t = inner.strip()
        if t == "else":
            return "{%- else -%}"
        if t == "end":
            block_type = stack.pop() if stack else "if"
            return f"{{%- end{block_type} -%}}"
        if t.startswith("if "):
            stack.append("if")
            return "{%- if " + t[3:].strip() + " -%}"
        if t.startswith("range "):
            stack.append("for")
            rng = re.sub(r"\$(\w+)", r"\1", t[6:].strip())
            rng = re.sub(r"\s*:=\s*", " in ", rng, count=1)
            return "{%- for " + rng + " -%}"
        if t.startswith("$") and ":=" in t:
            lhs, _, rhs = t.partition(":=")
            return "{%- set " + lhs.strip().lstrip("$") + " = " + rhs.strip() + " -%}"

        return left + inner + right

    return _BLOCK_RE.sub(transform, s)


def render(template_str: str, context: dict) -> tuple[str, Optional[Exception]]:
    try:
        tmpl = _JINJA.from_string(_preprocess(template_str))
        return tmpl.render(**context), None
    except Exception as exc:
        return "", exc

# ---------------------------------------------------------------------------
# Duration Parsing
# ---------------------------------------------------------------------------

_UNIT_SECS = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(s: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(ns|us|ms|s|m|h)", s.strip())
    if not m:
        raise ValueError(f"invalid duration {s!r}: expected number + ns/us/ms/s/m/h")
    return float(m.group(1)) * _UNIT_SECS[m.group(2)]

# ---------------------------------------------------------------------------
# YAML Loading & Validation
# ---------------------------------------------------------------------------

def _validate_behavior(b: object, source: str, templates_dir: str = "") -> dict:
    if not isinstance(b, dict):
        raise ValueError(f"{source}: expected a mapping, got {type(b).__name__}")
    key = b.get("key")
    if not key or not str(key).strip():
        raise ValueError(f"{source}: behavior has missing or empty 'key'")
    b.setdefault("kind", "Behavior")
    actions = b.get("actions") or []
    n_reply = sum(1 for a in actions if isinstance(a, dict) and "reply_http" in a)
    if n_reply > 1:
        raise ValueError(f"{source}: behavior {key!r} has {n_reply} reply_http actions (max 1)")
    for action in actions:
        if isinstance(action, dict) and "sleep" in action:
            parse_duration(str(action["sleep"].get("duration", "")))
        if isinstance(action, dict) and "reply_http" in action:
            cfg = action["reply_http"]
            bff = str(cfg.get("body_from_file") or "").strip()
            if bff and templates_dir:
                safe_root = os.path.realpath(templates_dir)
                resolved = os.path.realpath(os.path.join(templates_dir, bff))
                if not resolved.startswith(safe_root + os.sep) and resolved != safe_root:
                    raise ValueError(
                        f"{source}: behavior {key!r} body_from_file {bff!r} escapes templates dir"
                    )
                with open(resolved) as fh:
                    cfg["_body_snapshot"] = fh.read()
            elif bff and not templates_dir:
                raise ValueError(
                    f"{source}: behavior {key!r} body_from_file requires templates_dir to be set"
                )
        if isinstance(action, dict) and "send_http" in action:
            cfg = action["send_http"]
            bff = str(cfg.get("body_from_file") or "").strip()
            if bff and templates_dir:
                safe_root = os.path.realpath(templates_dir)
                resolved  = os.path.realpath(os.path.join(templates_dir, bff))
                if not resolved.startswith(safe_root + os.sep) and resolved != safe_root:
                    raise ValueError(
                        f"{source}: behavior {key!r} send_http body_from_file {bff!r} escapes templates dir"
                    )
                with open(resolved) as fh:
                    cfg["_body_snapshot"] = fh.read()
            elif bff and not templates_dir:
                raise ValueError(
                    f"{source}: behavior {key!r} send_http body_from_file requires templates_dir to be set"
                )
    return b


def load_behaviors(templates_dir: str) -> list[dict]:
    all_items: list[dict] = []
    for root, dirs, files in os.walk(templates_dir):
        dirs.sort()
        for fname in sorted(files):
            if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath) as f:
                data = yaml.safe_load(f)
            if data is None:
                continue
            if not isinstance(data, list):
                raise ValueError(f"{fpath}: top-level must be a list")
            for item in data:
                all_items.append(_validate_behavior(item, fpath, templates_dir))

    # Merge with last-key-wins
    key_index: dict[str, int] = {}
    merged: list[dict] = []
    for b in all_items:
        key = str(b["key"])
        if key in key_index:
            _log(logging.WARNING, "duplicate key overrides earlier definition", key=key)
            merged[key_index[key]] = b
        else:
            key_index[key] = len(merged)
            merged.append(b)

    for b in merged:
        http = (b.get("expect") or {}).get("http") or {}
        path_str = http.get("path")
        b["_pattern"] = _compile_path(path_str) if path_str else None

    return merged

# ---------------------------------------------------------------------------
# Path Matching
# ---------------------------------------------------------------------------

def _compile_path(path: str) -> re.Pattern:
    segments = []
    for part in path.split("/"):
        if part.startswith(":"):
            segments.append(f"(?P<{part[1:]}>[^/]+)")
        else:
            segments.append(re.escape(part))
    return re.compile("^" + "/".join(segments) + "$")


def match_path(pattern: re.Pattern, path: str) -> Optional[dict]:
    m = pattern.match(path.split("?", 1)[0])
    return m.groupdict() if m is not None else None

# ---------------------------------------------------------------------------
# Request Context
# ---------------------------------------------------------------------------

def build_context(method: str, path: str, query: str, headers: dict, body: str) -> dict:
    return {
        "HTTPHeader":      HeaderMap(headers),
        "HTTPBody":        body,
        "HTTPPath":        path + ("?" + query if query else ""),
        "HTTPQueryString": query,
    }

# ---------------------------------------------------------------------------
# Behavior Matching
# ---------------------------------------------------------------------------

def find_behavior(
    behaviors: list[dict],
    method: str,
    path: str,
    context: dict,
) -> tuple[Optional[dict], dict]:
    for b in behaviors:
        http     = (b.get("expect") or {}).get("http") or {}
        b_method = str(http.get("method", "")).upper()
        if b_method and b_method != method.upper():
            continue

        pattern = b.get("_pattern")
        if pattern is not None:
            params = match_path(pattern, path)
            if params is None:
                continue
        else:
            params = {}

        condition = str((b.get("expect") or {}).get("condition") or "").strip()
        if condition:
            rendered, err = render(condition, context)
            if err:
                _log(logging.DEBUG, "condition render error", key=b["key"], error=str(err))
                continue
            if rendered.strip().lower() != "true":
                continue

        return b, params

    return None, {}

# ---------------------------------------------------------------------------
# Action Execution
# ---------------------------------------------------------------------------

def execute_sleep(cfg: dict):
    time.sleep(parse_duration(str(cfg.get("duration", "0s"))))


def execute_reply_http(cfg: dict, context: dict, handler: "MockRequestHandler") -> int:
    status = int(cfg["status_code"])
    raw_headers: dict = dict(cfg.get("headers") or {})
    raw_body: str     = str(cfg.get("body") or "")
    snapshot: str     = str(cfg.get("_body_snapshot") or "")
    effective_body    = snapshot if (snapshot and not raw_body) else raw_body

    body_str, err = render(effective_body, context)
    if err:
        handler.send_error(500, f"body render error: {err}")
        return 500

    headers: dict[str, str] = {}
    for k, v in raw_headers.items():
        rendered_v, err = render(str(v), context)
        if err:
            handler.send_error(500, f"header render error: {err}")
            return 500
        headers[k] = rendered_v

    if not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/json"
    body_bytes = body_str.encode("utf-8")
    headers["Content-Length"] = str(len(body_bytes))

    handler.send_response(status)
    for k, v in headers.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body_bytes)
    return status


def execute_redis(items: list, context: dict):
    for item in (items or []):
        render(str(item), context)


def execute_send_http(cfg: dict, context: dict):
    url_str, err = render(str(cfg.get("url") or ""), context)
    if err:
        _log(logging.DEBUG, "send_http url render error", error=str(err))
        return
    method = str(cfg.get("method") or "GET").upper()
    rendered_headers: dict[str, str] = {}
    for k, v in (cfg.get("headers") or {}).items():
        rv, err = render(str(v), context)
        if err:
            _log(logging.DEBUG, "send_http header render error", key=k, error=str(err))
            return
        rendered_headers[k] = rv
    raw_body = str(cfg.get("body") or "")
    snapshot = str(cfg.get("_body_snapshot") or "")
    effective = snapshot if (snapshot and not raw_body) else raw_body
    body_str, err = render(effective, context)
    if err:
        _log(logging.DEBUG, "send_http body render error", error=str(err))
        return

    def _fire(url=url_str, meth=method, hdrs=rendered_headers, body=body_str):
        try:
            data = body.encode("utf-8") if body else None
            req  = urllib.request.Request(url, data=data, method=meth)
            for k, v in hdrs.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as exc:
            _log(logging.DEBUG, "send_http request failed", url=url, error=str(exc))

    threading.Thread(target=_fire, daemon=True).start()


def execute_actions(actions: list, context: dict, handler: "MockRequestHandler") -> int:
    status = 200
    for action in actions:
        if not isinstance(action, dict):
            continue
        if "sleep" in action:
            execute_sleep(action["sleep"])
        elif "reply_http" in action:
            status = execute_reply_http(action["reply_http"], context, handler)
        elif "redis" in action:
            execute_redis(action["redis"], context)
        elif "send_http" in action:
            execute_send_http(action["send_http"], context)
    return status

# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

_BEHAVIORS: list[dict] = []


class MockRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass

    def _dispatch(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body   = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        path, _, query = (self.path or "/").partition("?")
        headers  = dict(self.headers)
        context  = build_context(self.command, path, query, headers, body)

        behavior, params = find_behavior(_BEHAVIORS, self.command, path, context)
        if params:
            context["HTTPParams"] = params

        if behavior is None:
            not_found = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(not_found)))
            self.end_headers()
            self.wfile.write(not_found)
            status = 404
        else:
            status = execute_actions(behavior.get("actions") or [], context, self)

        _log(
            logging.INFO, "http",
            http_path=self.path,
            http_method=self.command,
            http_host=self.headers.get("Host", ""),
            http_req={"method": self.command, "path": self.path},
            http_res={"status_code": status},
        )

    def __getattr__(self, name: str):
        if name.startswith("do_"):
            return self._dispatch
        raise AttributeError(name)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _BEHAVIORS
    _BEHAVIORS = load_behaviors(TEMPLATES_DIR)
    _log(logging.INFO, f"loaded {len(_BEHAVIORS)} behaviors", templates_dir=TEMPLATES_DIR)
    server = HTTPServer((HTTP_HOST, HTTP_PORT), MockRequestHandler)
    _log(logging.INFO, "listening", host=HTTP_HOST, port=HTTP_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
