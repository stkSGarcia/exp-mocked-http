#!/usr/bin/env python3
"""YAML-driven HTTP mock server."""

from __future__ import annotations

import base64
import copy
import fnmatch
import hashlib
import hmac
import html as html_lib
import json
import logging
import os
import re
import shlex
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from jinja2 import Environment, StrictUndefined


DEFAULT_TEMPLATES_DIR = "./templates"
DEFAULT_TEMPLATES_DIR_HOT_RELOAD = True
DEFAULT_HTTP_PORT = 9999
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_CORS_ENABLED = False
DEFAULT_ADMIN_HTTP_ENABLED = True
DEFAULT_ADMIN_HTTP_PORT = 9998
DEFAULT_ADMIN_HTTP_HOST = "0.0.0.0"
DEFAULT_LOG_LEVEL = "info"
DEFAULT_REDIS_TYPE = "memory"
DEFAULT_REDIS_URL = "redis://redis:6379"
SUPPORTED_REDIS_TYPES = {"memory", "redis"}
OUTBOUND_HTTP_TIMEOUT_SECONDS = 2.0
HOT_RELOAD_INTERVAL_SECONDS = 0.1
INTERNAL_REDIS_PREFIX = "__hmock_internal:"
INTERNAL_TEMPLATES_KEY = f"{INTERNAL_REDIS_PREFIX}templates"
INTERNAL_TEMPLATE_SETS_KEY = f"{INTERNAL_REDIS_PREFIX}template_sets"

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}

_BEHAVIORS: list[dict[str, Any]] = []
_NAMED_TEMPLATES: dict[str, str] = {}
_ACTIVE_DEFINITIONS: list[dict[str, Any]] = []
_RUNTIME_LOCK = threading.RLock()
_MUTATION_LOCK = threading.RLock()
_REQUEST_RUNTIME = threading.local()

KIND_BEHAVIOR = "Behavior"
KIND_TEMPLATE = "Template"
KIND_ABSTRACT_BEHAVIOR = "AbstractBehavior"
SUPPORTED_KINDS = {KIND_BEHAVIOR, KIND_TEMPLATE, KIND_ABSTRACT_BEHAVIOR}
ALLOWED_FIELDS_BY_KIND = {
    KIND_BEHAVIOR: {"key", "kind", "extend", "expect", "actions", "values"},
    KIND_ABSTRACT_BEHAVIOR: {"key", "kind", "expect", "actions", "values"},
    KIND_TEMPLATE: {"key", "kind", "template"},
}


@dataclass(frozen=True)
class Config:
    templates_dir: str = DEFAULT_TEMPLATES_DIR
    templates_dir_hot_reload: bool = DEFAULT_TEMPLATES_DIR_HOT_RELOAD
    http_port: int = DEFAULT_HTTP_PORT
    http_host: str = DEFAULT_HTTP_HOST
    cors_enabled: bool = DEFAULT_CORS_ENABLED
    admin_http_enabled: bool = DEFAULT_ADMIN_HTTP_ENABLED
    admin_http_port: int = DEFAULT_ADMIN_HTTP_PORT
    admin_http_host: str = DEFAULT_ADMIN_HTTP_HOST
    log_level: str = DEFAULT_LOG_LEVEL
    redis_type: str = DEFAULT_REDIS_TYPE
    redis_url: str = DEFAULT_REDIS_URL


@dataclass
class Response:
    status_code: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class RuntimeState:
    definitions: list[dict[str, Any]]
    behaviors: list[dict[str, Any]]
    named_templates: dict[str, str]


class TemplateRenderError(RuntimeError):
    pass


class HeaderMap:
    def __init__(self, headers: dict[str, str]):
        self._headers = {str(k).lower(): str(v) for k, v in headers.items()}

    def Get(self, name: str) -> str:
        return self._headers.get(name.lower(), "")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        extra = getattr(record, "hmock_extra", None)
        if extra:
            entry.update(extra)
        return json.dumps(entry, separators=(",", ":"))


def load_config(env: Optional[dict[str, str]] = None) -> Config:
    env = os.environ if env is None else env
    log_level = env.get("HM_LOG_LEVEL", DEFAULT_LOG_LEVEL).lower()
    if log_level not in LOG_LEVELS:
        log_level = DEFAULT_LOG_LEVEL
    redis_type = env.get("HM_REDIS_TYPE", DEFAULT_REDIS_TYPE).lower()
    if redis_type not in SUPPORTED_REDIS_TYPES:
        raise ValueError(f"HM_REDIS_TYPE must be one of: {', '.join(sorted(SUPPORTED_REDIS_TYPES))}")
    return Config(
        templates_dir=env.get("HM_TEMPLATES_DIR", DEFAULT_TEMPLATES_DIR),
        templates_dir_hot_reload=_parse_bool(
            env.get(
                "HM_TEMPLATES_DIR_HOT_RELOAD",
                str(DEFAULT_TEMPLATES_DIR_HOT_RELOAD),
            ),
            "HM_TEMPLATES_DIR_HOT_RELOAD",
        ),
        http_port=int(env.get("HM_HTTP_PORT", str(DEFAULT_HTTP_PORT))),
        http_host=env.get("HM_HTTP_HOST", DEFAULT_HTTP_HOST),
        cors_enabled=_parse_bool(
            env.get("HM_CORS_ENABLED", str(DEFAULT_CORS_ENABLED)),
            "HM_CORS_ENABLED",
        ),
        admin_http_enabled=_parse_bool(
            env.get("HM_ADMIN_HTTP_ENABLED", str(DEFAULT_ADMIN_HTTP_ENABLED)),
            "HM_ADMIN_HTTP_ENABLED",
        ),
        admin_http_port=int(env.get("HM_ADMIN_HTTP_PORT", str(DEFAULT_ADMIN_HTTP_PORT))),
        admin_http_host=env.get("HM_ADMIN_HTTP_HOST", DEFAULT_ADMIN_HTTP_HOST),
        log_level=log_level,
        redis_type=redis_type,
        redis_url=env.get("HM_REDIS_URL", DEFAULT_REDIS_URL),
    )


def _parse_bool(value: Any, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def setup_logger(level_name: str, stream: Any = None) -> logging.Logger:
    logger = logging.getLogger("hmock")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(LOG_LEVELS.get(level_name.lower(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout if stream is None else stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


LOGGER = setup_logger(os.environ.get("HM_LOG_LEVEL", DEFAULT_LOG_LEVEL))


def log_json(level: str, message: str, **fields: Any) -> None:
    numeric = LOG_LEVELS[level]
    if not LOGGER.isEnabledFor(numeric):
        return
    record = LOGGER.makeRecord(LOGGER.name, numeric, "", 0, message, (), None)
    record.hmock_extra = fields
    LOGGER.handle(record)


class RedisBackend:
    def execute(self, args: list[str]) -> Any:
        raise NotImplementedError


class MemoryRedisBackend(RedisBackend):
    def __init__(self) -> None:
        self._values: dict[str, str | list[str] | dict[str, str]] = {}
        self._lock = threading.RLock()

    def execute(self, args: list[str]) -> Any:
        if not args:
            return ""
        command = args[0].upper()
        with self._lock:
            if command == "SET":
                _require_arity(args, 3)
                self._values[args[1]] = args[2]
                return "OK"
            if command == "GET":
                _require_arity(args, 2)
                value = self._values.get(args[1])
                return value if isinstance(value, str) else ""
            if command == "RPUSH":
                _require_min_arity(args, 3)
                values = self._list_value(args[1])
                values.extend(args[2:])
                return len(values)
            if command == "LPUSH":
                _require_min_arity(args, 3)
                values = self._list_value(args[1])
                for value in args[2:]:
                    values.insert(0, value)
                return len(values)
            if command == "LRANGE":
                _require_arity(args, 4)
                value = self._values.get(args[1])
                if not isinstance(value, list):
                    return []
                return _redis_lrange(value, int(args[2]), int(args[3]))
            if command == "LPOP":
                _require_arity(args, 2)
                value = self._values.get(args[1])
                return value.pop(0) if isinstance(value, list) and value else ""
            if command == "RPOP":
                _require_arity(args, 2)
                value = self._values.get(args[1])
                return value.pop() if isinstance(value, list) and value else ""
            if command == "HSET":
                _require_min_arity(args, 4)
                if len(args[2:]) % 2 != 0:
                    raise ValueError("HSET requires field/value pairs")
                values = self._hash_value(args[1])
                added = 0
                for index in range(2, len(args), 2):
                    field = args[index]
                    if field not in values:
                        added += 1
                    values[field] = args[index + 1]
                return added
            if command == "HGET":
                _require_arity(args, 3)
                value = self._values.get(args[1])
                return value.get(args[2], "") if isinstance(value, dict) else ""
            if command == "HGETALL":
                _require_arity(args, 2)
                value = self._values.get(args[1])
                if not isinstance(value, dict):
                    return []
                result: list[str] = []
                for field, field_value in value.items():
                    result.extend([field, field_value])
                return result
            if command == "HDEL":
                _require_min_arity(args, 3)
                value = self._values.get(args[1])
                if not isinstance(value, dict):
                    return 0
                removed = 0
                for field in args[2:]:
                    if field in value:
                        removed += 1
                        del value[field]
                return removed
            if command == "DEL":
                _require_min_arity(args, 2)
                removed = 0
                for key in args[1:]:
                    if key in self._values:
                        removed += 1
                        del self._values[key]
                return removed
            if command == "EXISTS":
                _require_min_arity(args, 2)
                return sum(1 for key in args[1:] if key in self._values)
            if command == "KEYS":
                _require_arity(args, 2)
                return sorted(key for key in self._values if fnmatch.fnmatch(key, args[1]))
        raise ValueError(f"unsupported Redis command: {command}")

    def _list_value(self, key: str) -> list[str]:
        value = self._values.get(key)
        if value is None:
            values: list[str] = []
            self._values[key] = values
            return values
        if not isinstance(value, list):
            raise ValueError(f"key {key!r} does not contain a list")
        return value

    def _hash_value(self, key: str) -> dict[str, str]:
        value = self._values.get(key)
        if value is None:
            values: dict[str, str] = {}
            self._values[key] = values
            return values
        if not isinstance(value, dict):
            raise ValueError(f"key {key!r} does not contain a hash")
        return value


class ExternalRedisBackend(RedisBackend):
    def __init__(self, url: str, timeout: float = OUTBOUND_HTTP_TIMEOUT_SECONDS) -> None:
        self.url = url
        self.timeout = timeout

    def execute(self, args: list[str]) -> Any:
        parsed = urllib.parse.urlparse(self.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=self.timeout) as sock:
            file = sock.makefile("rb")
            if parsed.password:
                auth_args = ["AUTH", parsed.password]
                if parsed.username:
                    auth_args = ["AUTH", parsed.username, parsed.password]
                self._send(sock, auth_args)
                _read_resp(file)
            if parsed.path and parsed.path != "/":
                db = parsed.path.lstrip("/")
                if db:
                    self._send(sock, ["SELECT", db])
                    _read_resp(file)
            self._send(sock, args)
            return _read_resp(file)

    def _send(self, sock: socket.socket, args: list[str]) -> None:
        sock.sendall(_encode_resp_array(args))


def create_redis_backend(config: Config) -> RedisBackend:
    if config.redis_type == "memory":
        return MemoryRedisBackend()
    if config.redis_type == "redis":
        return ExternalRedisBackend(config.redis_url)
    raise ValueError(f"unsupported Redis backend type: {config.redis_type}")


_REDIS_BACKEND: RedisBackend = MemoryRedisBackend()


def redis_do(command: Any) -> str:
    args = parse_redis_command(str(command))
    _reject_internal_redis_keys(args)
    return format_redis_result(_REDIS_BACKEND.execute(args))


def parse_redis_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"invalid Redis command {command!r}: {exc}") from exc


def format_redis_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ";;".join(format_redis_result(item) for item in value)
    return str(value)


def execute_redis_command(command: str) -> str:
    args = parse_redis_command(command)
    return format_redis_result(_REDIS_BACKEND.execute(args))


def redis_command_keys(args: list[str]) -> list[str]:
    if not args:
        return []
    command = args[0].upper()
    if command in {
        "SET", "GET", "RPUSH", "LPUSH", "LRANGE", "LPOP", "RPOP",
        "HSET", "HGET", "HGETALL", "HDEL", "KEYS",
    }:
        return args[1:2]
    if command in {"DEL", "EXISTS"}:
        return args[1:]
    return []


def _reject_internal_redis_keys(args: list[str]) -> None:
    for key in redis_command_keys(args):
        if key.startswith(INTERNAL_REDIS_PREFIX):
            raise ValueError(f"Redis keyspace {INTERNAL_REDIS_PREFIX}* is reserved")


def render_named_template(name: Any, template_context: Any) -> str:
    key = str(name)
    request_templates = getattr(_REQUEST_RUNTIME, "named_templates", None)
    if request_templates is None:
        with _RUNTIME_LOCK:
            template = _NAMED_TEMPLATES.get(key)
    else:
        template = request_templates.get(key)
    if template is None:
        raise TemplateRenderError(f"unknown template: {key}")
    if isinstance(template_context, dict):
        context = dict(template_context)
    else:
        context = {"Value": template_context}
    return render(template, context)


def _require_arity(args: list[str], expected: int) -> None:
    if len(args) != expected:
        raise ValueError(f"{args[0].upper()} requires {expected - 1} argument(s)")


def _require_min_arity(args: list[str], expected: int) -> None:
    if len(args) < expected:
        raise ValueError(f"{args[0].upper()} requires at least {expected - 1} argument(s)")


def _redis_lrange(values: list[str], start: int, stop: int) -> list[str]:
    length = len(values)
    if start < 0:
        start = length + start
    if stop < 0:
        stop = length + stop
    start = max(start, 0)
    stop = min(stop, length - 1)
    if start > stop or start >= length:
        return []
    return values[start:stop + 1]


def _encode_resp_array(args: list[str]) -> bytes:
    parts = [f"*{len(args)}\r\n".encode("ascii")]
    for arg in args:
        data = str(arg).encode("utf-8")
        parts.append(f"${len(data)}\r\n".encode("ascii"))
        parts.append(data + b"\r\n")
    return b"".join(parts)


def _read_resp(file: Any) -> Any:
    prefix = file.read(1)
    if not prefix:
        raise ValueError("Redis connection closed")
    line = file.readline()
    if prefix == b"+":
        return line[:-2].decode("utf-8")
    if prefix == b"-":
        raise ValueError(line[:-2].decode("utf-8"))
    if prefix == b":":
        return int(line)
    if prefix == b"$":
        length = int(line)
        if length == -1:
            return None
        data = file.read(length)
        file.read(2)
        return data.decode("utf-8")
    if prefix == b"*":
        count = int(line)
        if count == -1:
            return None
        return [_read_resp(file) for _ in range(count)]
    raise ValueError(f"unsupported Redis response prefix: {prefix!r}")


def discover_yaml_files(templates_dir: str) -> list[Path]:
    root = Path(templates_dir)
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )


def _loaded_objects(data: Any, source: Path) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        objects = data
    elif isinstance(data, dict):
        objects = [data]
    else:
        raise ValueError(f"{source}: top-level YAML must be an object or list")
    for obj in objects:
        if not isinstance(obj, dict):
            raise ValueError(f"{source}: each mock definition must be an object")
    return [dict(obj) for obj in objects]


def load_yaml_objects(templates_dir: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for path in discover_yaml_files(templates_dir):
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        objects.extend(_loaded_objects(data, path))
    return objects


def _validate_behavior(
    item: dict[str, Any],
    source: str = "mock",
    templates_dir: Optional[str] = None,
) -> dict[str, Any]:
    definition = _validate_definition(item, source)
    if definition["kind"] != KIND_BEHAVIOR:
        raise ValueError(f"{source}: final behavior must have kind {KIND_BEHAVIOR}")
    behavior = dict(definition)
    behavior["key"] = str(definition["key"])
    behavior["kind"] = KIND_BEHAVIOR
    values = behavior.get("values")
    if values is None:
        behavior["values"] = {}
    elif not isinstance(values, dict):
        raise ValueError(f"{source}: values must be a map")
    actions = behavior.get("actions") or []
    if not isinstance(actions, list):
        raise ValueError(f"{source}: actions must be a list")
    reply_count = sum(1 for action in actions if isinstance(action, dict) and "reply_http" in action)
    if reply_count > 1:
        raise ValueError(f"{source}: behavior {behavior['key']!r} has more than one reply_http action")
    behavior["actions"] = _prepare_actions(actions, templates_dir, source)
    behavior["actions"] = _sort_actions(behavior["actions"])
    expect = behavior.get("expect") or {}
    if not isinstance(expect, dict):
        raise ValueError(f"{source}: expect must be a map")
    http_expect = expect.get("http") or {}
    if not isinstance(http_expect, dict):
        raise ValueError(f"{source}: expect.http must be a map")
    path_pattern = http_expect.get("path")
    behavior["_pattern"] = _compile_path(str(path_pattern)) if path_pattern else None
    return behavior


def _validate_definition(item: dict[str, Any], source: str = "mock") -> dict[str, Any]:
    key = item.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"{source}: key must be a non-empty string")
    kind = str(item.get("kind") or KIND_BEHAVIOR)
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"{source}: kind must be one of: {', '.join(sorted(SUPPORTED_KINDS))}")
    extra_fields = set(item) - ALLOWED_FIELDS_BY_KIND[kind]
    if extra_fields:
        fields = ", ".join(sorted(extra_fields))
        raise ValueError(f"{source}: {kind} does not allow field(s): {fields}")
    definition = dict(item)
    definition["key"] = key
    definition["kind"] = kind
    if kind == KIND_TEMPLATE:
        if not isinstance(definition.get("template"), str):
            raise ValueError(f"{source}: Template requires a template string")
        return definition
    values = definition.get("values")
    if values is not None and not isinstance(values, dict):
        raise ValueError(f"{source}: values must be a map")
    actions = definition.get("actions")
    if actions is not None and not isinstance(actions, list):
        raise ValueError(f"{source}: actions must be a list")
    expect = definition.get("expect")
    if expect is not None and not isinstance(expect, dict):
        raise ValueError(f"{source}: expect must be a map")
    return definition


def _prepare_actions(
    actions: list[Any],
    templates_dir: Optional[str],
    source: str,
) -> list[Any]:
    prepared: list[Any] = []
    for action in actions:
        if not isinstance(action, dict):
            prepared.append(action)
            continue
        prepared_action = dict(action)
        if "reply_http" in prepared_action:
            reply_config = dict(prepared_action.get("reply_http") or {})
            _prepare_body_from_file(reply_config, templates_dir, source)
            _prepare_body_from_binary_file(reply_config, templates_dir, source)
            prepared_action["reply_http"] = reply_config
        if "redis" in prepared_action:
            redis_items = prepared_action.get("redis")
            if not isinstance(redis_items, list) or not all(isinstance(item, str) for item in redis_items):
                raise ValueError(f"{source}: redis action must be an array of template strings")
        if "send_http" in prepared_action:
            send_config = prepared_action.get("send_http")
            if not isinstance(send_config, dict):
                raise ValueError(f"{source}: send_http action must be an object")
            send_config = dict(send_config)
            if not send_config.get("url") or not send_config.get("method"):
                raise ValueError(f"{source}: send_http.url and send_http.method are required")
            headers = send_config.get("headers")
            if headers is not None and not isinstance(headers, dict):
                raise ValueError(f"{source}: send_http.headers must be a string map")
            _prepare_body_from_file(send_config, templates_dir, source)
            _prepare_body_from_binary_file(send_config, templates_dir, source)
            prepared_action["send_http"] = send_config
        prepared.append(prepared_action)
    return prepared


def _sort_actions(actions: list[Any]) -> list[Any]:
    return sorted(actions, key=_action_order)


def _action_order(action: Any) -> int:
    if not isinstance(action, dict):
        return 0
    try:
        return int(action.get("order", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError(f"action order must be an integer: {action.get('order')!r}")


def _prepare_body_from_file(
    config: dict[str, Any],
    templates_dir: Optional[str],
    source: str,
) -> None:
    body_from_file = config.get("body_from_file")
    if body_from_file not in (None, "") and templates_dir is not None:
        config["_body_from_file_content"] = _load_body_from_file(
            templates_dir,
            str(body_from_file),
            source,
        )


def _load_body_from_file(templates_dir: str, relative_path: str, source: str) -> str:
    target = _resolve_body_file(
        templates_dir,
        relative_path,
        source,
        "body_from_file",
    )
    try:
        return target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{source}: cannot read body_from_file {relative_path!r}: {exc}") from exc


def _prepare_body_from_binary_file(
    config: dict[str, Any],
    templates_dir: Optional[str],
    source: str,
) -> None:
    body_from_binary_file = config.get("body_from_binary_file")
    if body_from_binary_file not in (None, "") and templates_dir is not None:
        relative_path = str(body_from_binary_file)
        target = _resolve_body_file(
            templates_dir,
            relative_path,
            source,
            "body_from_binary_file",
        )
        try:
            config["_body_from_binary_file_content"] = target.read_bytes()
        except OSError as exc:
            raise ValueError(
                f"{source}: cannot read body_from_binary_file {relative_path!r}: {exc}"
            ) from exc
        config["_body_from_binary_file_name"] = target.name


def _resolve_body_file(
    templates_dir: str,
    relative_path: str,
    source: str,
    field_name: str,
) -> Path:
    root = Path(templates_dir).resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"{source}: {field_name} must resolve inside HM_TEMPLATES_DIR")
    return target


def compile_runtime(
    items: list[dict[str, Any]],
    templates_dir: Optional[str] = None,
) -> RuntimeState:
    definitions: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for index, item in enumerate(items):
        definition = _validate_definition(item, f"mock {index + 1}")
        key = definition["key"]
        if key in definitions:
            ordered_keys = [existing_key for existing_key in ordered_keys if existing_key != key]
            log_json("warn", "duplicate behavior key override", key=key)
        definitions[key] = definition
        ordered_keys.append(key)

    named_templates = {
        key: str(definitions[key]["template"])
        for key in ordered_keys
        if definitions[key]["kind"] == KIND_TEMPLATE
    }

    resolved: dict[str, dict[str, Any]] = {}

    def resolve(key: str, stack: tuple[str, ...] = ()) -> dict[str, Any]:
        if key in resolved:
            return copy.deepcopy(resolved[key])
        if key in stack:
            cycle = " -> ".join((*stack, key))
            raise ValueError(f"cyclic behavior inheritance: {cycle}")
        definition = definitions[key]
        kind = definition["kind"]
        if kind == KIND_TEMPLATE:
            raise ValueError(f"mock {key!r}: Template cannot be extended")
        merged = copy.deepcopy(definition)
        parent_key = definition.get("extend")
        if parent_key:
            parent = definitions.get(str(parent_key))
            if parent is not None:
                if parent["kind"] == KIND_TEMPLATE:
                    raise ValueError(f"mock {key!r}: Template cannot be used as an inheritance parent")
                merged = _merge_behavior_definitions(
                    resolve(str(parent_key), (*stack, key)),
                    definition,
                )
        resolved[key] = copy.deepcopy(merged)
        return merged

    active: list[dict[str, Any]] = []
    for key in ordered_keys:
        definition = definitions[key]
        if definition["kind"] != KIND_BEHAVIOR:
            continue
        active.append(_validate_behavior(resolve(key), f"mock {key!r}", templates_dir))
    effective_definitions = [copy.deepcopy(definitions[key]) for key in ordered_keys]
    return RuntimeState(effective_definitions, active, named_templates)


def install_runtime(state: RuntimeState) -> None:
    global _ACTIVE_DEFINITIONS, _BEHAVIORS, _NAMED_TEMPLATES
    with _RUNTIME_LOCK:
        _ACTIVE_DEFINITIONS = copy.deepcopy(state.definitions)
        _BEHAVIORS = state.behaviors
        _NAMED_TEMPLATES = state.named_templates


def runtime_snapshot() -> RuntimeState:
    with _RUNTIME_LOCK:
        return RuntimeState(
            copy.deepcopy(_ACTIVE_DEFINITIONS),
            list(_BEHAVIORS),
            dict(_NAMED_TEMPLATES),
        )


def assemble_behaviors(items: list[dict[str, Any]], templates_dir: Optional[str] = None) -> list[dict[str, Any]]:
    state = compile_runtime(items, templates_dir)
    global _NAMED_TEMPLATES
    with _RUNTIME_LOCK:
        _NAMED_TEMPLATES = state.named_templates
    return state.behaviors


def _merge_behavior_definitions(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(parent)
    for key, value in child.items():
        if key == "values":
            parent_values = parent.get("values") or {}
            child_values = value or {}
            merged["values"] = {**copy.deepcopy(parent_values), **copy.deepcopy(child_values)}
        elif key == "actions":
            merged["actions"] = [
                *copy.deepcopy(parent.get("actions") or []),
                *copy.deepcopy(value or []),
            ]
        elif key == "expect":
            merged["expect"] = _merge_recursive_maps(parent.get("expect") or {}, value or {})
        elif _is_non_zero(value):
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_recursive_maps(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(parent)
    for key, value in child.items():
        parent_value = merged.get(key)
        if isinstance(parent_value, dict) and isinstance(value, dict):
            merged[key] = _merge_recursive_maps(parent_value, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _is_non_zero(value: Any) -> bool:
    return value is not None and value != ""


def load_behaviors(templates_dir: str) -> list[dict[str, Any]]:
    return assemble_behaviors(load_yaml_objects(templates_dir), templates_dir)


def _decode_definition_list(value: Any, source: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    try:
        data = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source}: invalid persisted JSON: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{source}: persisted value must be an array of objects")
    return [dict(item) for item in data]


def load_persisted_base(backend: Optional[RedisBackend] = None) -> list[dict[str, Any]]:
    backend = _REDIS_BACKEND if backend is None else backend
    return _decode_definition_list(
        backend.execute(["GET", INTERNAL_TEMPLATES_KEY]),
        INTERNAL_TEMPLATES_KEY,
    )


def save_persisted_base(definitions: list[dict[str, Any]], backend: Optional[RedisBackend] = None) -> None:
    backend = _REDIS_BACKEND if backend is None else backend
    backend.execute([
        "SET",
        INTERNAL_TEMPLATES_KEY,
        json.dumps(definitions, separators=(",", ":")),
    ])


def load_persisted_sets(backend: Optional[RedisBackend] = None) -> dict[str, list[dict[str, Any]]]:
    backend = _REDIS_BACKEND if backend is None else backend
    raw = backend.execute(["HGETALL", INTERNAL_TEMPLATE_SETS_KEY]) or []
    if not isinstance(raw, list) or len(raw) % 2:
        raise ValueError(f"{INTERNAL_TEMPLATE_SETS_KEY}: invalid persisted hash response")
    sets: dict[str, list[dict[str, Any]]] = {}
    for index in range(0, len(raw), 2):
        key = str(raw[index])
        sets[key] = _decode_definition_list(raw[index + 1], f"template set {key!r}")
    return sets


def save_persisted_set(
    set_key: str,
    definitions: list[dict[str, Any]],
    backend: Optional[RedisBackend] = None,
) -> None:
    backend = _REDIS_BACKEND if backend is None else backend
    backend.execute([
        "HSET",
        INTERNAL_TEMPLATE_SETS_KEY,
        set_key,
        json.dumps(definitions, separators=(",", ":")),
    ])


def delete_persisted_set(set_key: str, backend: Optional[RedisBackend] = None) -> None:
    backend = _REDIS_BACKEND if backend is None else backend
    backend.execute(["HDEL", INTERNAL_TEMPLATE_SETS_KEY, set_key])


def merged_definition_items(
    config: Config,
    base_definitions: Optional[list[dict[str, Any]]] = None,
    template_sets: Optional[dict[str, list[dict[str, Any]]]] = None,
    backend: Optional[RedisBackend] = None,
) -> list[dict[str, Any]]:
    backend = _REDIS_BACKEND if backend is None else backend
    base = load_persisted_base(backend) if base_definitions is None else base_definitions
    sets = load_persisted_sets(backend) if template_sets is None else template_sets
    items = load_yaml_objects(config.templates_dir)
    items.extend(copy.deepcopy(base))
    for set_key in sorted(sets):
        items.extend(copy.deepcopy(sets[set_key]))
    return items


def build_runtime(
    config: Config,
    base_definitions: Optional[list[dict[str, Any]]] = None,
    template_sets: Optional[dict[str, list[dict[str, Any]]]] = None,
    backend: Optional[RedisBackend] = None,
) -> RuntimeState:
    return compile_runtime(
        merged_definition_items(config, base_definitions, template_sets, backend),
        config.templates_dir,
    )


def reload_runtime(config: Config, backend: Optional[RedisBackend] = None) -> RuntimeState:
    state = build_runtime(config, backend=backend)
    install_runtime(state)
    return state


def templates_tree_fingerprint(
    templates_dir: str,
) -> tuple[tuple[str, int, int, str], ...]:
    root = Path(templates_dir)
    if not root.exists():
        return ()
    entries: list[tuple[str, int, int, str]] = []
    for path in sorted(root.rglob("*")):
        try:
            if not path.is_file():
                continue
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        entries.append((
            path.relative_to(root).as_posix(),
            stat.st_mtime_ns,
            stat.st_size,
            digest,
        ))
    return tuple(entries)


def run_hot_reload_worker(
    config: Config,
    backend: RedisBackend,
    stop_event: threading.Event,
    interval: float = HOT_RELOAD_INTERVAL_SECONDS,
    initial_fingerprint: Optional[tuple[tuple[str, int, int, str], ...]] = None,
) -> None:
    previous = (
        templates_tree_fingerprint(config.templates_dir)
        if initial_fingerprint is None
        else initial_fingerprint
    )
    while not stop_event.wait(interval):
        current = templates_tree_fingerprint(config.templates_dir)
        if current == previous:
            continue
        previous = current
        try:
            with _MUTATION_LOCK:
                state = build_runtime(config, backend=backend)
                install_runtime(state)
            log_json(
                "info",
                "reloaded behaviors",
                count=len(state.behaviors),
                templates_dir=config.templates_dir,
            )
        except Exception as exc:
            log_json(
                "error",
                "template hot reload failed",
                error=str(exc),
                templates_dir=config.templates_dir,
            )


def start_hot_reload_worker(
    config: Config,
    backend: RedisBackend,
    interval: float = HOT_RELOAD_INTERVAL_SECONDS,
) -> tuple[Optional[threading.Event], Optional[threading.Thread]]:
    if not config.templates_dir_hot_reload:
        return None, None
    stop_event = threading.Event()
    initial_fingerprint = templates_tree_fingerprint(config.templates_dir)
    thread = threading.Thread(
        target=run_hot_reload_worker,
        args=(config, backend, stop_event, interval, initial_fingerprint),
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def normalize_definition_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("request body must be a mock object or an array of mock objects")
    return [dict(item) for item in data]


def _upsert_definitions(
    current: list[dict[str, Any]],
    submitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    submitted_keys: list[str] = []
    submitted_by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(submitted):
        definition = _validate_definition(item, f"submitted mock {index + 1}")
        key = definition["key"]
        if key in submitted_by_key:
            submitted_keys.remove(key)
        submitted_by_key[key] = dict(item)
        submitted_keys.append(key)
    result = [dict(item) for item in current if item.get("key") not in submitted_by_key]
    result.extend(submitted_by_key[key] for key in submitted_keys)
    return result


def mutate_base_templates(
    config: Config,
    submitted: Optional[list[dict[str, Any]]] = None,
    delete_key: Optional[str] = None,
    delete_all: bool = False,
    backend: Optional[RedisBackend] = None,
) -> bool:
    backend = _REDIS_BACKEND if backend is None else backend
    with _MUTATION_LOCK:
        current = load_persisted_base(backend)
        sets = load_persisted_sets(backend)
        if delete_all:
            candidate: list[dict[str, Any]] = []
        elif delete_key is not None:
            if not any(str(item.get("key")) == delete_key for item in current):
                return False
            candidate = [item for item in current if str(item.get("key")) != delete_key]
        else:
            candidate = _upsert_definitions(current, submitted or [])
        state = build_runtime(config, candidate, sets, backend)
        save_persisted_base(candidate, backend)
        install_runtime(state)
        return True


def mutate_template_set(
    config: Config,
    set_key: str,
    submitted: Optional[list[dict[str, Any]]] = None,
    delete: bool = False,
    backend: Optional[RedisBackend] = None,
) -> None:
    backend = _REDIS_BACKEND if backend is None else backend
    with _MUTATION_LOCK:
        base = load_persisted_base(backend)
        sets = load_persisted_sets(backend)
        candidate_sets = copy.deepcopy(sets)
        if delete:
            candidate_sets.pop(set_key, None)
        else:
            candidate_sets[set_key] = [dict(item) for item in submitted or []]
        state = build_runtime(config, base, candidate_sets, backend)
        if delete:
            delete_persisted_set(set_key, backend)
        else:
            save_persisted_set(set_key, candidate_sets[set_key], backend)
        install_runtime(state)


def _compile_path(pattern: str) -> re.Pattern[str]:
    if not pattern.startswith("/"):
        pattern = "/" + pattern
    parts: list[str] = []
    for segment in pattern.strip("/").split("/"):
        if segment.startswith(":") and len(segment) > 1:
            name = re.sub(r"\W+", "_", segment[1:])
            parts.append(f"(?P<{name}>[^/]+)")
        else:
            parts.append(re.escape(segment))
    body = "/".join(parts)
    if body:
        return re.compile(f"^/{body}$")
    return re.compile(r"^/$")


def match_path(pattern: re.Pattern[str], path: str) -> Optional[dict[str, str]]:
    match = pattern.fullmatch(path)
    if not match:
        return None
    return match.groupdict()


def build_context(
    method: str,
    full_path: str,
    query_string: str,
    headers: dict[str, str],
    body: str,
    params: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    return {
        "HTTPHeader": HeaderMap(headers),
        "HTTPBody": body,
        "HTTPPath": full_path,
        "HTTPQueryString": query_string,
        "HTTPMethod": method,
        "HTTPParams": params or {},
        "HTTPPathParams": params or {},
    }


def find_behavior(
    behaviors: list[dict[str, Any]],
    method: str,
    path: str,
    context: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], dict[str, str]]:
    method = method.upper()
    for behavior in behaviors:
        expect = behavior.get("expect") or {}
        http_expect = expect.get("http") or {}
        expected_method = str(http_expect.get("method") or "").upper()
        if expected_method and expected_method != method:
            continue
        pattern = behavior.get("_pattern")
        expected_path = http_expect.get("path")
        if expected_path and pattern is None:
            pattern = _compile_path(str(expected_path))
            behavior["_pattern"] = pattern
        params = match_path(pattern, path) if pattern is not None else {}
        if params is None:
            continue
        check_context = dict(context)
        check_context["HTTPParams"] = params
        check_context["HTTPPathParams"] = params
        check_context["Values"] = behavior.get("values") or {}
        if condition_passes(expect.get("condition"), check_context):
            return behavior, params
    return None, {}


def condition_passes(condition: Any, context: dict[str, Any]) -> bool:
    if condition is None or str(condition) == "":
        return True
    try:
        rendered = render(str(condition), context)
    except TemplateRenderError:
        return False
    return rendered == "true"


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ns|us|ms|s|m|h)\s*", value)
    if not match:
        raise ValueError(f"invalid duration: {value!r}")
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {
        "ns": 1e-9,
        "us": 1e-6,
        "ms": 1e-3,
        "s": 1.0,
        "m": 60.0,
        "h": 3600.0,
    }
    return amount * factors[unit]


def execute_actions(actions: list[dict[str, Any]], context: dict[str, Any]) -> Response:
    for action in _sort_actions(actions):
        if not isinstance(action, dict):
            continue
        if "redis" in action:
            for command_template in action.get("redis") or []:
                execute_redis_command(render(str(command_template), context))
            continue
        if "send_http" in action:
            send_http_request(action.get("send_http") or {}, context)
            continue
        if "sleep" in action:
            duration = str((action.get("sleep") or {}).get("duration") or "")
            time.sleep(parse_duration(duration))
            continue
        if "reply_http" in action:
            return build_http_response(action.get("reply_http") or {}, context)
    return Response(204, {"Content-Length": "0"}, b"")


def build_http_response(config: dict[str, Any], context: dict[str, Any]) -> Response:
    if "status_code" not in config:
        raise ValueError("reply_http.status_code is required")
    status_code = int(config["status_code"])
    rendered_headers: dict[str, str] = {}
    for name, value in (config.get("headers") or {}).items():
        rendered_headers[str(name)] = render(str(value), context)
    if not any(name.lower() == "content-type" for name in rendered_headers):
        rendered_headers["Content-Type"] = "application/json"
    binary_body = _select_binary_body(config)
    if binary_body is not None:
        body = binary_body
        binary_file_name = config.get("binary_file_name")
        if binary_file_name not in (None, ""):
            rendered_headers["Content-Disposition"] = (
                f'inline; filename="{str(binary_file_name)}"'
            )
    else:
        body_text = render(_select_body_template(config) or "", context)
        body = body_text.encode("utf-8")
    rendered_headers["Content-Length"] = str(len(body))
    return Response(status_code, rendered_headers, body)


def send_http_request(config: dict[str, Any], context: dict[str, Any]) -> None:
    try:
        url = render(str(config["url"]), context)
        method = render(str(config["method"]), context).upper()
        headers = {
            str(name): render(str(value), context)
            for name, value in (config.get("headers") or {}).items()
        }
        binary_body = _select_binary_body(config)
        if binary_body is not None and method == "POST":
            part_content_type = _pop_header(headers, "Content-Type") or "application/octet-stream"
            configured_name = config.get("binary_file_name")
            file_name = (
                str(configured_name)
                if configured_name not in (None, "")
                else str(config.get("_body_from_binary_file_name") or "file")
            )
            data, multipart_content_type = encode_multipart_file(
                binary_body,
                file_name,
                part_content_type,
            )
            headers["Content-Type"] = multipart_content_type
        elif binary_body is not None:
            data = binary_body
        else:
            body_template = _select_body_template(config)
            data = (
                None
                if body_template is None
                else render(body_template, context).encode("utf-8")
            )
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=OUTBOUND_HTTP_TIMEOUT_SECONDS) as response:
            response.read()
    except Exception as exc:
        log_json(
            "warn",
            "send_http request failed",
            error=str(exc),
            url=str(config.get("url", "")),
            method=str(config.get("method", "")),
        )


def _select_body_template(config: dict[str, Any]) -> Optional[str]:
    body = config.get("body")
    if body is not None and str(body) != "":
        return str(body)
    if "_body_from_file_content" in config:
        return str(config.get("_body_from_file_content", ""))
    return None


def _select_binary_body(config: dict[str, Any]) -> Optional[bytes]:
    body = config.get("body")
    if body is not None and str(body) != "":
        return None
    value = config.get("_body_from_binary_file_content")
    return value if isinstance(value, bytes) else None


def _pop_header(headers: dict[str, str], name: str) -> Optional[str]:
    expected = name.lower()
    for header_name in list(headers):
        if header_name.lower() == expected:
            return headers.pop(header_name)
    return None


def encode_multipart_file(
    content: bytes,
    file_name: str,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"hmock-{uuid.uuid4().hex}"
    safe_name = file_name.replace("\\", "\\\\").replace('"', '\\"')
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode("utf-8")
    body = prefix + content + f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={boundary}"


def not_found_response() -> Response:
    body = b"not found"
    return Response(404, {"Content-Type": "text/plain", "Content-Length": str(len(body))}, body)


def json_response(status_code: int, data: Any) -> Response:
    body = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return Response(
        status_code,
        {"Content-Type": "application/json", "Content-Length": str(len(body))},
        body,
    )


def no_content_response() -> Response:
    return Response(204, {"Content-Length": "0"}, b"")


def empty_response(status_code: int = 200) -> Response:
    return Response(status_code, {"Content-Length": "0"}, b"")


CORS_DEFAULT_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Credentials": "true",
}


def apply_cors_headers(response: Response) -> Response:
    existing = {name.lower() for name in response.headers}
    for name, value in CORS_DEFAULT_HEADERS.items():
        if name.lower() not in existing:
            response.headers[name] = value
    return response


def error_response(status_code: int, message: str) -> Response:
    return json_response(status_code, {"error": message})


def send_response(handler: BaseHTTPRequestHandler, response: Response, include_body: bool = True) -> None:
    handler.send_response(response.status_code)
    for name, value in response.headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    if include_body and response.body:
        handler.wfile.write(response.body)


class MockRequestHandler(BaseHTTPRequestHandler):
    server_version = "hmock/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def config(self) -> Config:
        return getattr(self.server, "config", Config())

    def _dispatch(self, include_body: bool = True) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        raw_path = self.path or "/"
        path, _, query = raw_path.partition("?")
        context = build_context(self.command, raw_path, query, dict(self.headers.items()), body)
        state = runtime_snapshot()
        _REQUEST_RUNTIME.named_templates = state.named_templates
        try:
            behavior, params = find_behavior(state.behaviors, self.command, path, context)
            if behavior is None:
                if self.command == "OPTIONS" and self.config.cors_enabled:
                    response = empty_response()
                else:
                    response = not_found_response()
            else:
                context["HTTPParams"] = params
                context["HTTPPathParams"] = params
                context["Values"] = behavior.get("values") or {}
                response = execute_actions(behavior.get("actions") or [], context)
        finally:
            del _REQUEST_RUNTIME.named_templates
        if self.config.cors_enabled:
            apply_cors_headers(response)
        send_response(self, response, include_body=include_body)
        log_json(
            "info",
            "http request",
            http_path=raw_path,
            http_method=self.command,
            http_host=self.headers.get("Host", ""),
            http_req={"method": self.command, "path": raw_path, "body": body},
            http_res={"status_code": response.status_code, "headers": response.headers},
        )

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PUT(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def do_OPTIONS(self) -> None:
        self._dispatch()

    def do_HEAD(self) -> None:
        self._dispatch(include_body=False)

    def __getattr__(self, name: str) -> Callable[[], None]:
        if name.startswith("do_"):
            return self._dispatch
        raise AttributeError(name)


class AdminRequestHandler(BaseHTTPRequestHandler):
    server_version = "hmock-admin/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def config(self) -> Config:
        return self.server.config  # type: ignore[attr-defined]

    @property
    def backend(self) -> RedisBackend:
        return self.server.redis_backend  # type: ignore[attr-defined]

    def _read_definitions(self) -> list[dict[str, Any]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        content_type = self.headers.get_content_type()
        try:
            text = raw.decode("utf-8")
            if content_type in {"application/yaml", "application/x-yaml"}:
                data = yaml.safe_load(text)
            else:
                data = json.loads(text)
        except (UnicodeDecodeError, ValueError) as exc:
            format_name = "YAML" if content_type in {"application/yaml", "application/x-yaml"} else "JSON"
            raise ValueError(f"invalid {format_name} request body: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML request body: {exc}") from exc
        return normalize_definition_payload(data)

    def _dispatch(self) -> None:
        path = urllib.parse.urlsplit(self.path or "/").path
        try:
            response = self._route(path)
        except ValueError as exc:
            response = error_response(400, str(exc))
        except Exception as exc:
            log_json("error", "admin request failed", error=str(exc), path=path, method=self.command)
            response = error_response(500, str(exc))
        send_response(self, response)
        log_json(
            "info",
            "admin http request",
            http_path=path,
            http_method=self.command,
            http_res={"status_code": response.status_code},
        )

    def _route(self, path: str) -> Response:
        if self.command == "GET" and path == "/api/v1/health":
            return json_response(200, {"status": "OK"})
        if self.command == "GET" and path == "/api/v1/templates":
            return json_response(200, runtime_snapshot().definitions)
        if path == "/api/v1/templates":
            if self.command == "POST":
                submitted = self._read_definitions()
                mutate_base_templates(self.config, submitted=submitted, backend=self.backend)
                return json_response(200, submitted)
            if self.command == "DELETE":
                mutate_base_templates(self.config, delete_all=True, backend=self.backend)
                return no_content_response()
        template_prefix = "/api/v1/templates/"
        if self.command == "DELETE" and path.startswith(template_prefix):
            template_key = urllib.parse.unquote(path[len(template_prefix):])
            if not template_key:
                return not_found_response()
            deleted = mutate_base_templates(
                self.config,
                delete_key=template_key,
                backend=self.backend,
            )
            return no_content_response() if deleted else error_response(404, "template not found")
        set_prefix = "/api/v1/template_sets/"
        if path.startswith(set_prefix):
            set_key = urllib.parse.unquote(path[len(set_prefix):])
            if not set_key:
                return not_found_response()
            if self.command == "POST":
                submitted = self._read_definitions()
                mutate_template_set(
                    self.config,
                    set_key,
                    submitted=submitted,
                    backend=self.backend,
                )
                return json_response(200, submitted)
            if self.command == "DELETE":
                mutate_template_set(self.config, set_key, delete=True, backend=self.backend)
                return no_content_response()
        return not_found_response()

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()


def create_server(
    config: Config,
    behaviors: Optional[list[dict[str, Any]]] = None,
    backend: Optional[RedisBackend] = None,
) -> ThreadingHTTPServer:
    global _BEHAVIORS, _REDIS_BACKEND
    if behaviors is not None:
        with _RUNTIME_LOCK:
            _BEHAVIORS = behaviors
    if backend is None:
        backend = create_redis_backend(config)
    _REDIS_BACKEND = backend
    server = ThreadingHTTPServer((config.http_host, config.http_port), MockRequestHandler)
    server.config = config  # type: ignore[attr-defined]
    return server


def create_admin_server(
    config: Config,
    backend: Optional[RedisBackend] = None,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(
        (config.admin_http_host, config.admin_http_port),
        AdminRequestHandler,
    )
    server.config = config  # type: ignore[attr-defined]
    server.redis_backend = _REDIS_BACKEND if backend is None else backend  # type: ignore[attr-defined]
    return server


def start_admin_server(
    config: Config,
    backend: Optional[RedisBackend] = None,
) -> tuple[Optional[ThreadingHTTPServer], Optional[threading.Thread]]:
    if not config.admin_http_enabled:
        return None, None
    server = create_admin_server(config, backend)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def main() -> None:
    global LOGGER, _REDIS_BACKEND
    config = load_config()
    LOGGER = setup_logger(config.log_level)
    _REDIS_BACKEND = create_redis_backend(config)
    state = reload_runtime(config, _REDIS_BACKEND)
    log_json("info", "loaded behaviors", count=len(state.behaviors), templates_dir=config.templates_dir)
    server = create_server(config, backend=_REDIS_BACKEND)
    reload_stop, reload_thread = start_hot_reload_worker(config, _REDIS_BACKEND)
    admin_server, admin_thread = start_admin_server(config, _REDIS_BACKEND)
    if admin_server is not None:
        log_json(
            "info",
            "admin listening",
            host=config.admin_http_host,
            port=config.admin_http_port,
        )
    log_json("info", "listening", host=config.http_host, port=config.http_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if reload_stop is not None:
            reload_stop.set()
        if reload_thread is not None:
            reload_thread.join(timeout=2)
        server.server_close()
        if admin_server is not None:
            admin_server.shutdown()
            admin_server.server_close()
        if admin_thread is not None:
            admin_thread.join(timeout=2)


_TOKEN_RE = re.compile(
    r'"[^"\\]*(?:\\.[^"\\]*)*"|`[^`]*`|\S+'
)
_BLOCK_RE = re.compile(r"\{\{-?.*?-?\}\}", re.DOTALL)
_VAR_RE = re.compile(r"(?<![\w.])\.(\w+(?:\.\w+)*)")
_METHOD_CALL_RE = re.compile(r"(?<![\w.])\.?(\w+(?:\.\w+)*)\.Get\s+(\"[^\"\\]*(?:\\.[^\"\\]*)*\")")
_PIPE_FUNC_RE = re.compile(r"\|\s*(\w+)((?:\s+[^|]+?)?)(?=\s*(?:\||$))")


def _make_template_env() -> Environment:
    env = Environment(undefined=StrictUndefined, autoescape=False, finalize=_finalize_template_value)
    functions: dict[str, Callable[..., Any]] = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "lt": lambda a, b: a < b,
        "gt": lambda a, b: a > b,
        "le": lambda a, b: a <= b,
        "ge": lambda a, b: a >= b,
        "and_": lambda *args: all(args),
        "or_": lambda *args: any(args),
        "not_": lambda value: not value,
        "print": lambda *args: "".join(str(arg) for arg in args),
        "printf": lambda fmt, *args: str(fmt) % tuple(args),
        "println": lambda *args: " ".join(str(arg) for arg in args) + "\n",
        "html": lambda value: html_lib.escape(str(value), quote=True),
        "js": lambda value: json.dumps(str(value)),
        "urlquery": lambda value: urllib.parse.quote_plus(str(value)),
        "len": lambda value: len(value),
        "index": lambda value, key: value[int(key)] if isinstance(value, (list, tuple, str)) else value[key],
        "call": lambda fn, *args: fn(*args),
        "contains": lambda value, needle: str(needle) in str(value),
        "hasPrefix": lambda value, prefix: str(value).startswith(str(prefix)),
        "hasSuffix": lambda value, suffix: str(value).endswith(str(suffix)),
        "replace": lambda value, old, new: str(value).replace(str(old), str(new)),
        "trim": lambda value: str(value).strip(),
        "upper": lambda value: str(value).upper(),
        "lower": lambda value: str(value).lower(),
        "title": lambda value: str(value).title(),
        "split": lambda value, sep: str(value).split(str(sep)),
        "splitList": split_list,
        "join": lambda value, sep="": str(sep).join(str(part) for part in value),
        "repeat": lambda value, count: str(value) * int(count),
        "nospace": lambda value: "".join(str(value).split()),
        "toString": lambda value: str(value),
        "default": lambda value, fallback="": value if value not in ("", None, False, [], {}) else fallback,
        "empty": lambda value: value in ("", None, False, [], {}),
        "coalesce": lambda *args: next((arg for arg in args if arg not in ("", None, False, [], {})), ""),
        "ternary": lambda condition, yes, no: yes if condition else no,
        "b64enc": lambda value: base64.b64encode(str(value).encode("utf-8")).decode("ascii"),
        "b64dec": lambda value: base64.b64decode(str(value).encode("ascii")).decode("utf-8"),
        "env": lambda name: os.environ.get(str(name), ""),
        "add": lambda a, b: _number(a) + _number(b),
        "sub": lambda a, b: _number(a) - _number(b),
        "mul": lambda a, b: _number(a) * _number(b),
        "div": lambda a, b: _number(a) / _number(b),
        "mod": lambda a, b: _number(a) % _number(b),
        "max": lambda *args: max(_number(arg) for arg in args),
        "min": lambda *args: min(_number(arg) for arg in args),
        "uuidv4": lambda: str(uuid.uuid4()),
        "jsonPath": json_path,
        "gJsonPath": g_json_path,
        "xmlPath": xml_path,
        "uuidv5": lambda value: str(uuid.uuid5(uuid.NAMESPACE_OID, str(value))),
        "regexFindAllSubmatch": regex_find_all_submatch,
        "regexFindFirstSubmatch": regex_find_first_submatch,
        "hmacSHA256": hmac_sha256,
        "isLastIndex": is_last_index,
        "htmlEscapeString": lambda value: html_lib.escape(str(value), quote=True),
        "redisDo": redis_do,
        "template": render_named_template,
        "enumerate": enumerate,
    }
    env.globals.update(functions)
    env.filters.update(functions)
    return env


def _finalize_template_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if "." in text:
        return float(text)
    return int(text)


def split_list(first: Any, second: Any = "") -> list[str]:
    first_text = str(first)
    second_text = str(second)
    if second_text in {";;", ",", " ", "|", "\n", "\t"} or len(first_text) > len(second_text):
        return first_text.split(second_text)
    if first_text == "":
        return list(second_text)
    return second_text.split(first_text)


def _template_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def json_path(expr: Any, data: Any) -> str:
    text = "" if data is None else str(data)
    if text == "":
        return ""
    try:
        root = json.loads(text)
    except json.JSONDecodeError:
        return ""
    query = str(expr).strip()
    if query == "":
        return _template_result(root)
    if query.startswith("//"):
        key = query[2:].strip()
        if not key:
            return ""
        found = _find_json_key(root, key)
        return _template_result(found) if found is not _MISSING else ""
    parts = [part for part in query.strip("/").split("/") if part]
    if len(parts) == 1 and "." in parts[0]:
        parts = [part for part in parts[0].split(".") if part]
    found = _walk_json_path(root, parts)
    return _template_result(found) if found is not _MISSING else ""


def g_json_path(expr: Any, data: Any) -> str:
    text = "" if data is None else str(data)
    if text == "":
        return ""
    root = json.loads(text)
    query = str(expr).strip()
    if query == "":
        return _template_result(root)
    found = _walk_gjson_path(root, [part for part in query.split(".") if part])
    return _template_result(found) if found is not _MISSING else ""


def xml_path(expr: Any, data: Any) -> str:
    text = "" if data is None else str(data)
    if text == "":
        return ""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ""
    query = str(expr).strip()
    if query == "":
        return "".join(root.itertext())
    if query == root.tag:
        node = root
    else:
        if query.startswith("//"):
            query = "." + query
        node = root.find(query)
    if node is None:
        return ""
    return "".join(node.itertext())


def regex_find_all_submatch(pattern: Any, value: Any) -> list[str]:
    match = re.search(str(pattern), str(value))
    if not match:
        return []
    return [match.group(0), *match.groups()]


def regex_find_first_submatch(pattern: Any, value: Any) -> str:
    match = re.search(str(pattern), str(value))
    if not match or not match.groups():
        return ""
    return match.group(1)


def hmac_sha256(secret: Any, data: Any) -> str:
    return hmac.new(str(secret).encode("utf-8"), str(data).encode("utf-8"), hashlib.sha256).hexdigest()


def is_last_index(index: Any, array: Any) -> bool:
    try:
        return int(index) == len(array) - 1
    except (TypeError, ValueError):
        return False


def _walk_json_path(value: Any, parts: list[str]) -> Any:
    current = value
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, list):
            if not part.isdigit():
                return _MISSING
            index = int(part)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _walk_gjson_path(value: Any, parts: list[str]) -> Any:
    if not parts:
        return value
    part = parts[0]
    rest = parts[1:]
    if isinstance(value, dict):
        if part not in value:
            return _MISSING
        return _walk_gjson_path(value[part], rest)
    if isinstance(value, list):
        if part == "#":
            if not rest:
                return len(value)
            results = []
            for item in value:
                found = _walk_gjson_path(item, rest)
                if found is not _MISSING:
                    results.append(found)
            return results
        if not part.isdigit():
            return _MISSING
        index = int(part)
        if index >= len(value):
            return _MISSING
        return _walk_gjson_path(value[index], rest)
    return _MISSING


def _find_json_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_json_key(child, key)
            if found is not _MISSING:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_json_key(child, key)
            if found is not _MISSING:
                return found
    return _MISSING


_MISSING = object()


_TEMPLATE_ENV = _make_template_env()


def render(template: str, context: dict[str, Any]) -> str:
    try:
        compiled = _TEMPLATE_ENV.from_string(_preprocess_template(template))
        render_context = dict(context)
        render_context["_context"] = render_context
        return compiled.render(**render_context)
    except Exception as exc:
        raise TemplateRenderError(str(exc)) from exc


def _preprocess_template(template: str) -> str:
    template = template.replace("\r\n", " ").replace("\n", " ").replace("\t", " ")

    def replace_block(match: re.Match[str]) -> str:
        raw = match.group(0)
        trim_left = raw.startswith("{{-")
        trim_right = raw.endswith("-}}")
        inner = raw[3 if trim_left else 2: -3 if trim_right else -2].strip()
        inner = _rewrite_expression(inner)
        left = "{%-" if trim_left else "{{"
        right = "-%}" if trim_right else "}}"
        if inner.startswith("__stmt__:"):
            body = inner[len("__stmt__:"):]
            return ("{%-" if trim_left else "{%") + body + ("-%}" if trim_right else "%}")
        return left + " " + inner + " " + right

    return _BLOCK_RE.sub(replace_block, template)


def _rewrite_expression(expr: str) -> str:
    expr = expr.strip()
    if expr == "else":
        return "__stmt__: else "
    if expr == "end":
        return "__stmt__: endif "
    if expr.startswith("if "):
        return "__stmt__: if " + _rewrite_value_expr(expr[3:].strip()) + " "
    if expr.startswith("range "):
        return "__stmt__: " + _rewrite_range(expr[6:].strip()) + " "
    if expr.startswith("$") and ":=" in expr:
        name, _, rhs = expr.partition(":=")
        return "__stmt__: set " + name.strip().lstrip("$") + " = " + _rewrite_value_expr(rhs.strip()) + " "
    return _rewrite_value_expr(expr)


def _rewrite_range(expr: str) -> str:
    expr = expr.replace("$", "")
    left, _, right = expr.partition(":=")
    target = left.strip()
    source = _rewrite_value_expr(right.strip())
    if "," in target:
        return f"for {target} in enumerate({source})"
    return f"for {target} in {source}"


def _rewrite_value_expr(expr: str) -> str:
    if expr == ".":
        return "_context"
    expr = re.sub(r"`([^`]*)`", lambda m: json.dumps(m.group(1)), expr)
    expr = expr.replace("$", "")
    expr = _METHOD_CALL_RE.sub(lambda m: f"{m.group(1)}.Get({m.group(2)})", expr)
    expr = _rewrite_vars_outside_strings(expr)
    expr = _rewrite_parenthesized_functions(expr)
    expr = _rewrite_pipeline_left(expr)
    expr = _rewrite_pipeline_functions(expr)
    return expr


def _rewrite_vars_outside_strings(expr: str) -> str:
    chunks: list[str] = []
    start = 0
    in_string = False
    escaped = False
    string_start = 0
    for index, char in enumerate(expr):
        if not in_string:
            if char == '"':
                chunks.append(_VAR_RE.sub(lambda m: m.group(1), expr[start:index]))
                string_start = index
                in_string = True
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            chunks.append(expr[string_start:index + 1])
            start = index + 1
            in_string = False
    if in_string:
        chunks.append(expr[string_start:])
    else:
        chunks.append(_VAR_RE.sub(lambda m: m.group(1), expr[start:]))
    return "".join(chunks)


def _rewrite_parenthesized_functions(expr: str) -> str:
    function_names = set(_TEMPLATE_ENV.globals.keys()) | {"and", "or", "not"}

    def replace(match: re.Match[str]) -> str:
        name = _function_name(match.group(1))
        if name not in function_names:
            return match.group(0)
        args = ", ".join(_rewrite_token_arg(part) for part in _TOKEN_RE.findall(match.group(2)))
        return f"({name}({args}))"

    previous = None
    while previous != expr:
        previous = expr
        expr = re.sub(r"\((\w+)\s+([^()]+)\)", replace, expr)
    return expr


def _rewrite_direct_function(expr: str) -> str:
    paren_call = re.fullmatch(r"(\w+)\s+\((.*)\)", expr)
    if paren_call:
        name = _function_name(paren_call.group(1))
        function_names = set(_TEMPLATE_ENV.globals.keys()) | {"and", "or", "not"}
        if name in function_names:
            return f"{name}({paren_call.group(2)})"
    if _contains_outside_strings(expr, "|"):
        return expr
    if _contains_outside_strings(expr, "("):
        return expr
    parts = _TOKEN_RE.findall(expr)
    if not parts:
        return expr
    name = _function_name(parts[0])
    function_names = set(_TEMPLATE_ENV.globals.keys()) | {"and", "or", "not"}
    if name not in function_names or len(parts) == 1:
        return expr
    args = ", ".join(_rewrite_token_arg(part) for part in parts[1:])
    return f"{_function_name(name)}({args})"


def _rewrite_pipeline_left(expr: str) -> str:
    left, separator, right = _partition_outside_strings(expr, "|")
    if not separator:
        return _rewrite_direct_function(expr)
    return f"{_rewrite_direct_function(left.strip())} |{right}"


def _partition_outside_strings(expr: str, needle: str) -> tuple[str, str, str]:
    in_string = False
    escaped = False
    for index, char in enumerate(expr):
        if not in_string:
            if char == needle:
                return expr[:index], char, expr[index + 1:]
            if char == '"':
                in_string = True
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = False
    return expr, "", ""


def _contains_outside_strings(expr: str, needle: str) -> bool:
    in_string = False
    escaped = False
    for char in expr:
        if not in_string:
            if char == needle:
                return True
            if char == '"':
                in_string = True
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = False
    return False


def _rewrite_pipeline_functions(expr: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = _function_name(match.group(1))
        arg_text = match.group(2).strip()
        if not arg_text:
            return f"|{name}"
        args = ", ".join(_rewrite_token_arg(part) for part in _TOKEN_RE.findall(arg_text))
        return f"|{name}({args})"

    return _PIPE_FUNC_RE.sub(replace, expr)


def _rewrite_token_arg(token: str) -> str:
    if token == ".":
        return "_context"
    if token.startswith("`") and token.endswith("`"):
        return json.dumps(token[1:-1])
    return token


def _function_name(name: str) -> str:
    return {"and": "and_", "or": "or_", "not": "not_"}.get(name, name)


if __name__ == "__main__":
    main()
