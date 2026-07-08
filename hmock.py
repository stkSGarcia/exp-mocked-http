from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import html as html_lib
import hmac
import importlib
import json
import os
import posixpath
import re
import shlex
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from fnmatch import fnmatch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote, urlsplit


class HMockError(Exception):
    pass


class TemplateError(HMockError):
    pass


class RedisError(TemplateError):
    pass


class ValidationError(HMockError):
    pass


@dataclasses.dataclass(frozen=True)
class KafkaClientConfig:
    seed_brokers: tuple[str, ...] = ("kafka:9092",)
    sasl_username: str = ""
    sasl_password: str = ""
    sasl_enabled: bool = False
    tls_enabled: bool = False


@dataclasses.dataclass(frozen=True)
class KafkaConfig:
    enabled: bool = False
    client_id: str = "hmock"
    producer: KafkaClientConfig = dataclasses.field(default_factory=KafkaClientConfig)
    consumer: KafkaClientConfig = dataclasses.field(default_factory=KafkaClientConfig)


@dataclasses.dataclass(frozen=True)
class AMQPConfig:
    enabled: bool = False
    url: str = "amqp://guest:guest@rabbitmq:5672"


@dataclasses.dataclass(frozen=True)
class Config:
    templates_dir: str = "./templates"
    http_port: int = 9999
    http_host: str = "0.0.0.0"
    log_level: str = "info"
    redis_type: str = "memory"
    redis_url: str = "redis://redis:6379"
    admin_http_enabled: bool = True
    admin_http_port: int = 9998
    admin_http_host: str = "0.0.0.0"
    templates_dir_hot_reload: bool = True
    cors_enabled: bool = False
    kafka: KafkaConfig = dataclasses.field(default_factory=KafkaConfig)
    amqp: AMQPConfig = dataclasses.field(default_factory=AMQPConfig)


def _env_bool(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _kafka_client_config(env: dict[str, str], side: str) -> KafkaClientConfig:
    side_prefix = f"HM_KAFKA_{side}_"
    sasl_prefix = f"HM_KAFKA_SASL_{side}_"
    brokers = _env_csv(env.get(f"{side_prefix}SEED_BROKERS", env.get("HM_KAFKA_SEED_BROKERS", "kafka:9092")))
    username = env.get(f"{sasl_prefix}USERNAME", env.get("HM_KAFKA_SASL_USERNAME", ""))
    password = env.get(f"{sasl_prefix}PASSWORD", env.get("HM_KAFKA_SASL_PASSWORD", ""))
    tls_value = env.get(f"HM_KAFKA_TLS_{side}_ENABLED")
    tls_enabled = _env_bool(tls_value) if tls_value is not None else _env_bool(env.get("HM_KAFKA_TLS_ENABLED", "false"))
    return KafkaClientConfig(
        seed_brokers=brokers,
        sasl_username=username,
        sasl_password=password,
        sasl_enabled=bool(username and password),
        tls_enabled=tls_enabled,
    )


def load_config(env: dict[str, str] | None = None) -> Config:
    env = env if env is not None else os.environ
    return Config(
        templates_dir=env.get("HM_TEMPLATES_DIR", "./templates"),
        http_port=int(env.get("HM_HTTP_PORT", "9999")),
        http_host=env.get("HM_HTTP_HOST", "0.0.0.0"),
        log_level=env.get("HM_LOG_LEVEL", "info").lower(),
        redis_type=env.get("HM_REDIS_TYPE", "memory").lower(),
        redis_url=env.get("HM_REDIS_URL", "redis://redis:6379"),
        admin_http_enabled=_env_bool(env.get("HM_ADMIN_HTTP_ENABLED", "true")),
        admin_http_port=int(env.get("HM_ADMIN_HTTP_PORT", "9998")),
        admin_http_host=env.get("HM_ADMIN_HTTP_HOST", "0.0.0.0"),
        templates_dir_hot_reload=_env_bool(env.get("HM_TEMPLATES_DIR_HOT_RELOAD", "true")),
        cors_enabled=_env_bool(env.get("HM_CORS_ENABLED", "false")),
        kafka=KafkaConfig(
            enabled=_env_bool(env.get("HM_KAFKA_ENABLED", "false")),
            client_id=env.get("HM_KAFKA_CLIENT_ID", "hmock"),
            producer=_kafka_client_config(env, "PRODUCER"),
            consumer=_kafka_client_config(env, "CONSUMER"),
        ),
        amqp=AMQPConfig(
            enabled=_env_bool(env.get("HM_AMQP_ENABLED", "false")),
            url=env.get("HM_AMQP_URL", "amqp://guest:guest@rabbitmq:5672"),
        ),
    )


class JsonLogger:
    LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}

    def __init__(self, level: str = "info", stream: Any | None = None) -> None:
        self.level = level if level in self.LEVELS else "info"
        self.stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()

    def enabled(self, level: str) -> bool:
        return self.LEVELS[level] >= self.LEVELS[self.level]

    def log(self, level: str, message: str, **fields: Any) -> None:
        if not self.enabled(level):
            return
        entry = {"level": level, "message": message, **fields}
        with self._lock:
            self.stream.write(json.dumps(entry, separators=(",", ":")) + "\n")
            self.stream.flush()

    def debug(self, message: str, **fields: Any) -> None:
        self.log("debug", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self.log("info", message, **fields)

    def warn(self, message: str, **fields: Any) -> None:
        self.log("warn", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self.log("error", message, **fields)


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise RedisError(f"invalid Redis command: {command}") from exc


def _parse_redis_command(command: str) -> list[str]:
    parts = _split_command(command)
    if not parts:
        raise RedisError("Redis command is empty")
    parts[0] = parts[0].upper()
    name = parts[0]
    argc = len(parts) - 1
    if name in {"GET", "LPOP", "RPOP", "HGETALL", "KEYS"} and argc != 1:
        raise RedisError(f"{name} expects 1 argument")
    if name == "SET" and argc != 2:
        raise RedisError("SET expects 2 arguments")
    if name in {"RPUSH", "LPUSH"} and argc < 2:
        raise RedisError(f"{name} expects at least 2 arguments")
    if name == "LRANGE" and argc != 3:
        raise RedisError("LRANGE expects 3 arguments")
    if name == "HGET" and argc != 2:
        raise RedisError("HGET expects 2 arguments")
    if name == "HSET" and (argc < 3 or argc % 2 != 1):
        raise RedisError("HSET expects a key and field/value pairs")
    if name == "HDEL" and argc < 2:
        raise RedisError("HDEL expects a key and at least one field")
    if name in {"DEL", "EXISTS"} and argc < 1:
        raise RedisError(f"{name} expects at least 1 argument")
    if name not in {
        "SET",
        "GET",
        "RPUSH",
        "LPUSH",
        "LRANGE",
        "LPOP",
        "RPOP",
        "HSET",
        "HGET",
        "HGETALL",
        "HDEL",
        "DEL",
        "EXISTS",
        "KEYS",
    }:
        raise RedisError(f"unsupported Redis command: {name}")
    return parts


INTERNAL_REDIS_PREFIX = "__hmock_internal:"
INTERNAL_TEMPLATES_KEY = "__hmock_internal:templates"
INTERNAL_TEMPLATE_SET_PREFIX = "__hmock_internal:template_sets:"


def _redis_command_keys(parts: list[str]) -> list[str]:
    name = parts[0]
    args = parts[1:]
    if name in {"GET", "SET", "RPUSH", "LPUSH", "LRANGE", "LPOP", "RPOP", "HSET", "HGET", "HGETALL", "HDEL"}:
        return [args[0]]
    if name in {"DEL", "EXISTS"}:
        return args
    if name == "KEYS":
        return args
    return []


def _redis_key_touches_internal(key: str, command_name: str) -> bool:
    if key.startswith(INTERNAL_REDIS_PREFIX):
        return True
    if command_name == "KEYS":
        return fnmatch(INTERNAL_TEMPLATES_KEY, key) or fnmatch(INTERNAL_TEMPLATE_SET_PREFIX + "example", key)
    return False


def _assert_redis_command_allowed(parts: list[str]) -> None:
    for key in _redis_command_keys(parts):
        if _redis_key_touches_internal(key, parts[0]):
            raise RedisError("Redis command targets internal hmock keyspace")


def _format_redis_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ";;".join("" if item is None else str(item) for item in value)
    return str(value)


class MemoryRedisStore:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._lock = threading.Lock()

    def do(self, command: str, allow_internal: bool = False) -> str:
        parts = _parse_redis_command(command)
        if not allow_internal:
            _assert_redis_command_allowed(parts)
        name = parts[0]
        args = parts[1:]
        with self._lock:
            if name == "SET":
                self._values[args[0]] = args[1]
                return "OK"
            if name == "GET":
                return _format_redis_result(self._get_string(args[0]))
            if name == "RPUSH":
                items = self._list_for_write(args[0])
                items.extend(args[1:])
                return str(len(items))
            if name == "LPUSH":
                items = self._list_for_write(args[0])
                for value in args[1:]:
                    items.insert(0, value)
                return str(len(items))
            if name == "LRANGE":
                return _format_redis_result(self._lrange(args[0], int(args[1]), int(args[2])))
            if name == "LPOP":
                items = self._list_for_read(args[0])
                return _format_redis_result(items.pop(0) if items else None)
            if name == "RPOP":
                items = self._list_for_read(args[0])
                return _format_redis_result(items.pop() if items else None)
            if name == "HSET":
                return str(self._hset(args[0], args[1:]))
            if name == "HGET":
                return _format_redis_result(self._hash_for_read(args[0]).get(args[1]))
            if name == "HGETALL":
                flat: list[str] = []
                for field, value in self._hash_for_read(args[0]).items():
                    flat.extend([field, value])
                return _format_redis_result(flat)
            if name == "HDEL":
                mapping = self._hash_for_read(args[0])
                removed = 0
                for field in args[1:]:
                    if field in mapping:
                        removed += 1
                        del mapping[field]
                return str(removed)
            if name == "DEL":
                removed = 0
                for key in args:
                    if key in self._values:
                        removed += 1
                        del self._values[key]
                return str(removed)
            if name == "EXISTS":
                return str(sum(1 for key in args if key in self._values))
            if name == "KEYS":
                return _format_redis_result(sorted(key for key in self._values if fnmatch(key, args[0])))
        raise RedisError(f"unsupported Redis command: {name}")

    def _get_string(self, key: str) -> str | None:
        value = self._values.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise RedisError(f"WRONGTYPE for key {key}")
        return value

    def _list_for_write(self, key: str) -> list[str]:
        value = self._values.setdefault(key, [])
        if not isinstance(value, list):
            raise RedisError(f"WRONGTYPE for key {key}")
        return value

    def _list_for_read(self, key: str) -> list[str]:
        value = self._values.get(key, [])
        if not isinstance(value, list):
            raise RedisError(f"WRONGTYPE for key {key}")
        return value

    def _lrange(self, key: str, start: int, stop: int) -> list[str]:
        items = self._list_for_read(key)
        if start < 0:
            start = len(items) + start
        if stop < 0:
            stop = len(items) + stop
        start = max(start, 0)
        stop = min(stop, len(items) - 1)
        if stop < start or not items:
            return []
        return items[start : stop + 1]

    def _hash_for_write(self, key: str) -> dict[str, str]:
        value = self._values.setdefault(key, {})
        if not isinstance(value, dict):
            raise RedisError(f"WRONGTYPE for key {key}")
        return value

    def _hash_for_read(self, key: str) -> dict[str, str]:
        value = self._values.get(key, {})
        if not isinstance(value, dict):
            raise RedisError(f"WRONGTYPE for key {key}")
        return value

    def _hset(self, key: str, pairs: list[str]) -> int:
        mapping = self._hash_for_write(key)
        added = 0
        for index in range(0, len(pairs), 2):
            field = pairs[index]
            if field not in mapping:
                added += 1
            mapping[field] = pairs[index + 1]
        return added


class ExternalRedisStore:
    def __init__(self, url: str, timeout: float = 3.0) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "redis":
            raise ValidationError("HM_REDIS_URL must use redis://")
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 6379
        self.username = parsed.username
        self.password = parsed.password
        self.db = int(parsed.path.strip("/") or "0")
        self.timeout = timeout

    def do(self, command: str, allow_internal: bool = False) -> str:
        parts = _parse_redis_command(command)
        if not allow_internal:
            _assert_redis_command_allowed(parts)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
            reader = conn.makefile("rb")
            if self.password is not None:
                auth = ["AUTH", self.password]
                if self.username is not None:
                    auth = ["AUTH", self.username, self.password]
                self._send(conn, auth)
                self._read(reader)
            if self.db:
                self._send(conn, ["SELECT", str(self.db)])
                self._read(reader)
            self._send(conn, parts)
            return _format_redis_result(self._read(reader))

    def _send(self, conn: socket.socket, parts: list[str]) -> None:
        payload = [f"*{len(parts)}\r\n".encode()]
        for part in parts:
            data = str(part).encode()
            payload.append(f"${len(data)}\r\n".encode())
            payload.append(data + b"\r\n")
        conn.sendall(b"".join(payload))

    def _read(self, reader: Any) -> Any:
        prefix = reader.read(1)
        if not prefix:
            raise RedisError("empty Redis response")
        line = reader.readline().rstrip(b"\r\n")
        if prefix == b"+":
            return line.decode()
        if prefix == b"-":
            raise RedisError(line.decode())
        if prefix == b":":
            return int(line)
        if prefix == b"$":
            length = int(line)
            if length == -1:
                return None
            data = reader.read(length)
            reader.read(2)
            return data.decode()
        if prefix == b"*":
            length = int(line)
            if length == -1:
                return None
            return [self._read(reader) for _ in range(length)]
        raise RedisError(f"unknown Redis response prefix: {prefix!r}")


RedisStore = MemoryRedisStore | ExternalRedisStore


def build_redis_store(config: Config) -> RedisStore:
    if config.redis_type == "memory":
        return MemoryRedisStore()
    if config.redis_type == "redis":
        return ExternalRedisStore(config.redis_url)
    raise ValidationError("HM_REDIS_TYPE must be memory or redis")


def _strip_comment(line: str) -> str:
    quote = ""
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            continue
        if ch == "#":
            return line[:i].rstrip()
    return line.rstrip()


def _split_key_value(text: str) -> tuple[str, str | None]:
    quote = ""
    escaped = False
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            continue
        if ch == ":":
            return text[:i].strip(), text[i + 1 :].strip()
    raise ValidationError(f"invalid YAML mapping entry: {text}")


def _parse_scalar(value: str | None) -> Any:
    if value is None or value == "":
        return None
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "Null", "~"):
        return None
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_yaml_subset(text: str) -> Any:
    raw_lines: list[tuple[int, str]] = []
    for line in text.splitlines():
        cleaned = _strip_comment(line)
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        raw_lines.append((indent, cleaned.strip()))
    if not raw_lines:
        return []

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        def parse_block_scalar(index: int, parent_indent: int, style: str) -> tuple[str, int]:
            lines: list[str] = []
            while index < len(raw_lines) and raw_lines[index][0] > parent_indent:
                lines.append(raw_lines[index][1])
                index += 1
            if style == "|":
                return "\n".join(lines), index
            return " ".join(lines), index

        if index >= len(raw_lines):
            return {}, index
        current_indent, current_text = raw_lines[index]
        if current_indent < indent:
            return {}, index
        if current_text.startswith("- "):
            items: list[Any] = []
            while index < len(raw_lines):
                item_indent, item_text = raw_lines[index]
                if item_indent != indent or not item_text.startswith("- "):
                    break
                rest = item_text[2:].strip()
                index += 1
                if rest == "":
                    item, index = parse_block(index, indent + 2)
                    items.append(item)
                    continue
                if ":" in rest:
                    key, value = _split_key_value(rest)
                    item: Any = {}
                    if value in {">", "|"}:
                        item[key], index = parse_block_scalar(index, indent, value)
                    else:
                        item[key] = _parse_scalar(value)
                    if value == "" or value is None:
                        if index < len(raw_lines) and raw_lines[index][0] > indent:
                            nested, index = parse_block(index, raw_lines[index][0])
                            item[key] = nested
                        else:
                            item[key] = {}
                    while index < len(raw_lines) and raw_lines[index][0] > indent:
                        nested, index = parse_block(index, raw_lines[index][0])
                        if isinstance(item, dict) and isinstance(nested, dict):
                            item.update(nested)
                        else:
                            break
                    items.append(item)
                else:
                    items.append(_parse_scalar(rest))
                    if index < len(raw_lines) and raw_lines[index][0] > indent:
                        _, index = parse_block(index, indent + 2)
            return items, index

        mapping: dict[str, Any] = {}
        while index < len(raw_lines):
            item_indent, item_text = raw_lines[index]
            if item_indent != indent or item_text.startswith("- "):
                break
            key, value = _split_key_value(item_text)
            index += 1
            if value in {">", "|"}:
                mapping[key], index = parse_block_scalar(index, item_indent, value)
            elif value == "" or value is None:
                if index < len(raw_lines) and raw_lines[index][0] > indent:
                    nested, index = parse_block(index, raw_lines[index][0])
                    mapping[key] = nested
                else:
                    mapping[key] = {}
            else:
                mapping[key] = _parse_scalar(value)
        return mapping, index

    parsed, end = parse_block(0, raw_lines[0][0])
    if end != len(raw_lines):
        raise ValidationError("could not parse YAML document")
    return parsed


def discover_yaml_files(root: str | Path) -> list[Path]:
    path = Path(root)
    if not path.exists():
        return []
    return sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}
    )


@dataclasses.dataclass
class PathPattern:
    source: str
    regex: re.Pattern[str]

    @classmethod
    def compile(cls, source: str) -> "PathPattern":
        if not source.startswith("/"):
            source = "/" + source
        segments = source.strip("/").split("/") if source != "/" else []
        parts = ["^"]
        if not segments:
            parts.append("/")
        for segment in segments:
            parts.append("/")
            if segment.startswith(":") and len(segment) > 1:
                name = re.escape(segment[1:])
                parts.append(f"(?P<{name}>[^/]+)")
            else:
                parts.append(re.escape(segment))
        parts.append("$")
        return cls(source=source, regex=re.compile("".join(parts)))

    def match(self, path: str) -> dict[str, str] | None:
        match = self.regex.match(path)
        if not match:
            return None
        return match.groupdict()


@dataclasses.dataclass
class Behavior:
    key: str
    kind: str
    expectation_type: str
    method: str | None
    path: str | None
    condition: str
    actions: list[dict[str, Any]]
    pattern: PathPattern | None
    values: dict[str, Any]
    templates: dict[str, str]
    kafka_topic: str | None = None
    amqp_exchange: str | None = None
    amqp_routing_key: str | None = None
    amqp_queue: str | None = None


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)", str(value))
    if not match:
        raise ValidationError(f"unsupported duration: {value}")
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
    return amount * factors[unit]


def _resolve_template_file_path(templates_dir: str | Path, file_name: str, field_name: str) -> Path:
    root = Path(templates_dir).resolve()
    path = (root / file_name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {file_name}")
    return path


def _resolve_body_file(templates_dir: str | Path, body_from_file: str, field_name: str = "reply_http.body_from_file") -> str:
    path = _resolve_template_file_path(templates_dir, body_from_file, field_name)
    return path.read_text()


def _resolve_binary_file(templates_dir: str | Path, body_from_file: str, field_name: str) -> bytes:
    path = _resolve_template_file_path(templates_dir, body_from_file, field_name)
    return path.read_bytes()


def _validate_optional_string(value: Any, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")


def _validate_headers_mapping(headers: Any, field_name: str) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a mapping")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")


def _validate_payload_source(
    payload: dict[str, Any],
    key: str,
    action_name: str,
    templates_dir: str | Path | None,
) -> None:
    inline_payload = payload.get("payload")
    if inline_payload is not None and not isinstance(inline_payload, str):
        raise ValidationError(f"behavior {key} {action_name}.payload must be a string")
    payload_from_file = payload.get("payload_from_file")
    if payload_from_file is not None:
        if not isinstance(payload_from_file, str) or not payload_from_file:
            raise ValidationError(f"behavior {key} {action_name}.payload_from_file must be a non-empty string")
        if templates_dir is not None:
            payload[f"{action_name}_payload_from_file_content"] = _resolve_body_file(
                templates_dir,
                payload_from_file,
                f"{action_name}.payload_from_file",
            )
    if inline_payload is None and payload_from_file is None:
        raise ValidationError(f"behavior {key} {action_name}.payload or {action_name}.payload_from_file is required")


VALID_KINDS = {"Behavior", "Template", "AbstractBehavior"}
ALLOWED_FIELDS = {
    "Behavior": {"key", "kind", "extend", "expect", "actions", "values"},
    "Template": {"key", "kind", "template"},
    "AbstractBehavior": {"key", "kind", "expect", "actions", "values"},
}


def _definition_kind(raw: Any) -> tuple[str, str]:
    if not isinstance(raw, dict):
        raise ValidationError("definition must be a mapping")
    key = raw.get("key")
    if not isinstance(key, str) or not key:
        raise ValidationError("definition key must be a non-empty string")
    kind = raw.get("kind", "Behavior")
    if not isinstance(kind, str) or not kind:
        raise ValidationError(f"definition {key} kind must be a non-empty string")
    if kind not in VALID_KINDS:
        raise ValidationError(f"definition {key} kind is not supported: {kind}")
    unknown = set(raw) - ALLOWED_FIELDS[kind]
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise ValidationError(f"{kind} {key} field is not supported: {fields}")
    if kind == "Template":
        template = raw.get("template")
        if not isinstance(template, str):
            raise ValidationError(f"template {key} template must be a string")
    if kind in {"Behavior", "AbstractBehavior"} and "values" in raw and not isinstance(raw["values"], dict):
        raise ValidationError(f"behavior {key} values must be a mapping")
    return key, kind


def _action_name_payload(action: Any, key: str) -> tuple[str, Any]:
    if not isinstance(action, dict):
        raise ValidationError(f"behavior {key} action must be a mapping")
    names = [name for name in action if name != "order"]
    if len(names) != 1:
        raise ValidationError(f"behavior {key} action must contain exactly one action")
    return names[0], action[names[0]]


def _action_order(action: dict[str, Any], key: str) -> int:
    value = action.get("order", 0)
    if isinstance(value, bool):
        raise ValidationError(f"behavior {key} action order must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    raise ValidationError(f"behavior {key} action order must be an integer")


def _sort_actions(actions: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [
        action
        for _, action in sorted(
            enumerate(actions),
            key=lambda item: (_action_order(item[1], key), item[0]),
        )
    ]


def _validate_actions(
    actions: Any,
    key: str,
    templates_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        raise ValidationError(f"behavior {key} actions must be a list")
    reply_count = 0
    for action in actions:
        name, payload = _action_name_payload(action, key)
        _action_order(action, key)
        if name == "reply_http":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            reply_count += 1
            if "status_code" not in payload or not isinstance(payload["status_code"], int):
                raise ValidationError(f"behavior {key} reply_http.status_code is required")
            _validate_headers_mapping(payload.get("headers", {}), f"behavior {key} reply_http.headers")
            body_from_file = payload.get("body_from_file")
            if body_from_file is not None:
                if not isinstance(body_from_file, str) or not body_from_file:
                    raise ValidationError(f"behavior {key} reply_http.body_from_file must be a non-empty string")
                if templates_dir is not None:
                    payload["body_from_file_content"] = _resolve_body_file(templates_dir, body_from_file)
            body_from_binary_file = payload.get("body_from_binary_file")
            if body_from_binary_file is not None:
                if not isinstance(body_from_binary_file, str) or not body_from_binary_file:
                    raise ValidationError(f"behavior {key} reply_http.body_from_binary_file must be a non-empty string")
                if templates_dir is not None:
                    payload["body_from_binary_file_content"] = _resolve_binary_file(
                        templates_dir,
                        body_from_binary_file,
                        "reply_http.body_from_binary_file",
                    )
            _validate_optional_string(payload.get("binary_file_name"), f"behavior {key} reply_http.binary_file_name")
        elif name == "sleep":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            if "duration" not in payload:
                raise ValidationError(f"behavior {key} sleep.duration is required")
            parse_duration(str(payload["duration"]))
        elif name == "redis":
            if not isinstance(payload, list):
                raise ValidationError(f"behavior {key} redis action payload must be an array")
            for item in payload:
                if not isinstance(item, str):
                    raise ValidationError(f"behavior {key} redis action items must be strings")
        elif name == "send_http":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            if not isinstance(payload.get("url"), str) or not payload.get("url"):
                raise ValidationError(f"behavior {key} send_http.url is required")
            if not isinstance(payload.get("method"), str) or not payload.get("method"):
                raise ValidationError(f"behavior {key} send_http.method is required")
            _validate_headers_mapping(payload.get("headers", {}), f"behavior {key} send_http.headers")
            if "body" in payload and payload["body"] is not None and not isinstance(payload["body"], str):
                raise ValidationError(f"behavior {key} send_http.body must be a string")
            body_from_file = payload.get("body_from_file")
            if body_from_file is not None:
                if not isinstance(body_from_file, str) or not body_from_file:
                    raise ValidationError(f"behavior {key} send_http.body_from_file must be a non-empty string")
                if templates_dir is not None:
                    payload["send_http_body_from_file_content"] = _resolve_body_file(
                        templates_dir,
                        body_from_file,
                        "send_http.body_from_file",
                    )
            body_from_binary_file = payload.get("body_from_binary_file")
            if body_from_binary_file is not None:
                if not isinstance(body_from_binary_file, str) or not body_from_binary_file:
                    raise ValidationError(f"behavior {key} send_http.body_from_binary_file must be a non-empty string")
                if templates_dir is not None:
                    payload["send_http_body_from_binary_file_content"] = _resolve_binary_file(
                        templates_dir,
                        body_from_binary_file,
                        "send_http.body_from_binary_file",
                    )
            _validate_optional_string(payload.get("binary_file_name"), f"behavior {key} send_http.binary_file_name")
        elif name == "publish_kafka":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            if not isinstance(payload.get("topic"), str) or not payload.get("topic"):
                raise ValidationError(f"behavior {key} publish_kafka.topic is required")
            _validate_payload_source(payload, key, name, templates_dir)
        elif name == "publish_amqp":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            if not isinstance(payload.get("exchange"), str) or not payload.get("exchange"):
                raise ValidationError(f"behavior {key} publish_amqp.exchange is required")
            if not isinstance(payload.get("routing_key"), str) or not payload.get("routing_key"):
                raise ValidationError(f"behavior {key} publish_amqp.routing_key is required")
            _validate_payload_source(payload, key, name, templates_dir)
        else:
            raise ValidationError(f"behavior {key} action {name} is not supported")
    if reply_count > 1:
        raise ValidationError(f"behavior {key} has more than one reply_http action")
    return _sort_actions(actions, key)


def _validate_abstract_definition(raw: dict[str, Any], templates_dir: str | Path | None = None) -> None:
    key, kind = _definition_kind(raw)
    if kind != "AbstractBehavior":
        raise ValidationError(f"{kind} {key} cannot be used as an abstract behavior")
    expect = raw.get("expect", {})
    if expect is None:
        expect = {}
    if not isinstance(expect, dict):
        raise ValidationError(f"behavior {key} expect must be a mapping")
    condition = expect.get("condition", "")
    if condition is not None and not isinstance(condition, str):
        raise ValidationError(f"behavior {key} expect.condition must be a string")
    for name in ("http", "kafka", "amqp"):
        if name in expect and expect[name] is not None and not isinstance(expect[name], dict):
            raise ValidationError(f"behavior {key} expect.{name} must be a mapping")
    _validate_actions(raw.get("actions", []), key, templates_dir)


def _expectation_names(expect: dict[str, Any]) -> list[str]:
    return [
        name
        for name in ("http", "kafka", "amqp")
        if name in expect and expect[name] is not None and expect[name] != {}
    ]


def validate_behavior(
    raw: Any,
    templates_dir: str | Path | None = None,
    templates: dict[str, str] | None = None,
) -> Behavior:
    key, kind = _definition_kind(raw)
    if kind != "Behavior":
        raise ValidationError(f"{kind} {key} cannot be used as a concrete behavior")
    expect = raw.get("expect", {})
    if not isinstance(expect, dict):
        raise ValidationError(f"behavior {key} expect must be a mapping")
    for name in ("http", "kafka", "amqp"):
        if name in expect and expect[name] is not None and not isinstance(expect[name], dict):
            raise ValidationError(f"behavior {key} expect.{name} must be a mapping")
    expectation_names = _expectation_names(expect)
    if len(expectation_names) != 1:
        raise ValidationError(f"behavior {key} expect must contain exactly one of http, kafka, or amqp")
    expectation_type = expectation_names[0]
    method: str | None = None
    path: str | None = None
    pattern: PathPattern | None = None
    kafka_topic: str | None = None
    amqp_exchange: str | None = None
    amqp_routing_key: str | None = None
    amqp_queue: str | None = None
    if expectation_type == "http":
        http = expect["http"]
        method = http.get("method")
        path = http.get("path")
        if not isinstance(method, str) or not method:
            raise ValidationError(f"behavior {key} expect.http.method is required")
        if not isinstance(path, str) or not path:
            raise ValidationError(f"behavior {key} expect.http.path is required")
        method = method.upper()
        pattern = PathPattern.compile(path)
    elif expectation_type == "kafka":
        kafka = expect["kafka"]
        kafka_topic = kafka.get("topic")
        if not isinstance(kafka_topic, str) or not kafka_topic:
            raise ValidationError(f"behavior {key} expect.kafka.topic is required")
    else:
        amqp = expect["amqp"]
        amqp_exchange = amqp.get("exchange")
        amqp_routing_key = amqp.get("routing_key")
        amqp_queue = amqp.get("queue")
        if not isinstance(amqp_exchange, str) or not amqp_exchange:
            raise ValidationError(f"behavior {key} expect.amqp.exchange is required")
        if not isinstance(amqp_routing_key, str) or not amqp_routing_key:
            raise ValidationError(f"behavior {key} expect.amqp.routing_key is required")
        if amqp_queue is None or amqp_queue == "":
            amqp_queue = amqp_routing_key
            amqp["queue"] = amqp_queue
        if not isinstance(amqp_queue, str) or not amqp_queue:
            raise ValidationError(f"behavior {key} expect.amqp.queue must be a non-empty string")
    condition = expect.get("condition", "")
    if condition is None:
        condition = ""
    if not isinstance(condition, str):
        raise ValidationError(f"behavior {key} expect.condition must be a string")
    values = raw.get("values", {})
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise ValidationError(f"behavior {key} values must be a mapping")
    sorted_actions = _validate_actions(raw.get("actions", []), key, templates_dir)
    return Behavior(
        key=key,
        kind=kind,
        expectation_type=expectation_type,
        method=method,
        path=path,
        condition=condition,
        actions=sorted_actions,
        pattern=pattern,
        values=dict(values),
        templates=dict(templates or {}),
        kafka_topic=kafka_topic,
        amqp_exchange=amqp_exchange,
        amqp_routing_key=amqp_routing_key,
        amqp_queue=amqp_queue,
    )


def load_mock_file(path: str | Path) -> list[Any]:
    parsed = parse_yaml_subset(Path(path).read_text())
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise ValidationError(f"{path} must contain a top-level list")
    return parsed


def load_mock_definitions(templates_dir: str | Path) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for path in discover_yaml_files(templates_dir):
        for raw in load_mock_file(path):
            if not isinstance(raw, dict):
                raise ValidationError("definition must be a mapping")
            definitions.append(copy.deepcopy(raw))
    return definitions


def _templates_dir_fingerprint(templates_dir: str | Path) -> tuple[tuple[str, int, int], ...]:
    root = Path(templates_dir)
    if not root.exists():
        return ()
    entries: list[tuple[str, int, int]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        try:
            stat = path.stat()
            rel = path.relative_to(root).as_posix()
        except OSError:
            continue
        entries.append((rel, stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


def _recursive_merge(parent: Any, child: Any) -> Any:
    if isinstance(parent, dict) and isinstance(child, dict):
        merged = copy.deepcopy(parent)
        for key, value in child.items():
            if key in merged:
                merged[key] = _recursive_merge(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(child)


def _non_zero(value: Any) -> bool:
    return value not in (None, "", [], {})


def _merge_definitions(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(parent)
    for key, value in child.items():
        if key == "values":
            parent_values = parent.get("values") if isinstance(parent.get("values"), dict) else {}
            child_values = value if isinstance(value, dict) else {}
            merged["values"] = {**copy.deepcopy(parent_values), **copy.deepcopy(child_values)}
        elif key == "actions":
            merged["actions"] = copy.deepcopy(parent.get("actions") or []) + copy.deepcopy(value or [])
        elif key == "expect":
            merged["expect"] = _recursive_merge(parent.get("expect", {}), value or {})
        elif _non_zero(value):
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_behavior_definition(
    key: str,
    definitions: dict[str, dict[str, Any]],
    stack: tuple[str, ...] = (),
) -> dict[str, Any]:
    if key in stack:
        chain = " -> ".join((*stack, key))
        raise ValidationError(f"behavior inheritance cycle: {chain}")
    raw = copy.deepcopy(definitions[key])
    parent_key = raw.get("extend")
    if parent_key is None or parent_key == "":
        return raw
    if not isinstance(parent_key, str):
        raise ValidationError(f"behavior {key} extend must be a string")
    if parent_key not in definitions:
        return raw
    parent = definitions[parent_key]
    _, parent_kind = _definition_kind(parent)
    if parent_kind not in {"Behavior", "AbstractBehavior"}:
        raise ValidationError(f"behavior {key} cannot extend {parent_kind} {parent_key}")
    if parent_kind == "Behavior":
        parent = _resolve_behavior_definition(parent_key, definitions, (*stack, key))
    else:
        parent = copy.deepcopy(parent)
    merged = _merge_definitions(parent, raw)
    merged["kind"] = raw.get("kind", "Behavior")
    merged["key"] = key
    return merged


def build_behaviors_from_definitions(
    definitions: list[dict[str, Any]],
    templates_dir: str | Path | None = None,
    logger: JsonLogger | None = None,
) -> tuple[list[Behavior], list[dict[str, Any]]]:
    logger = logger or JsonLogger("error")
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in definitions:
        key, kind = _definition_kind(raw)
        if kind == "AbstractBehavior":
            _validate_abstract_definition(raw)
        if key in raw_by_key:
            order.remove(key)
            logger.warn("duplicate mock key override", key=key)
        raw_by_key[key] = copy.deepcopy(raw)
        raw_by_key[key].setdefault("kind", "Behavior")
        order.append(key)

    templates: dict[str, str] = {
        key: raw["template"]
        for key, raw in raw_by_key.items()
        if raw.get("kind", "Behavior") == "Template"
    }
    behaviors: list[Behavior] = []
    for key in order:
        raw = raw_by_key[key]
        _, kind = _definition_kind(raw)
        if kind == "Template":
            continue
        if kind == "AbstractBehavior":
            _validate_abstract_definition(raw, templates_dir)
            continue
        effective = _resolve_behavior_definition(key, raw_by_key)
        behaviors.append(validate_behavior(effective, templates_dir, templates))
    active_definitions = [copy.deepcopy(raw_by_key[key]) for key in order]
    return behaviors, active_definitions


def load_behaviors(templates_dir: str | Path, logger: JsonLogger | None = None) -> list[Behavior]:
    behaviors, _ = build_behaviors_from_definitions(load_mock_definitions(templates_dir), templates_dir, logger)
    return behaviors


def _redis_arg(*parts: str) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def _redis_internal_do(redis_store: RedisStore, *parts: str) -> str:
    return redis_store.do(_redis_arg(*parts), allow_internal=True)


def _canonical_mock_json(definitions: list[dict[str, Any]]) -> str:
    return json.dumps(definitions, sort_keys=True, separators=(",", ":"))


def _mock_definitions_from_json(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored mock definitions are invalid JSON: {exc}") from exc
    return validate_mock_definition_array(parsed)


def validate_mock_definition_array(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError("mock definitions must be a JSON array")
    definitions: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValidationError("mock definition must be an object")
        _definition_kind(raw)
        definitions.append(copy.deepcopy(raw))
    build_behaviors_from_definitions(definitions)
    return definitions


class StaticMockRegistry:
    def __init__(self, behaviors: list[Behavior]) -> None:
        self._behaviors = list(behaviors)

    def behaviors(self) -> list[Behavior]:
        return list(self._behaviors)

    def active_definitions(self) -> list[dict[str, Any]]:
        return []


class ActiveMockRegistry:
    def __init__(
        self,
        templates_dir: str | Path,
        redis_store: RedisStore,
        logger: JsonLogger | None = None,
        templates_dir_hot_reload: bool = True,
    ) -> None:
        self.templates_dir = templates_dir
        self.redis_store = redis_store
        self.logger = logger or JsonLogger("error")
        self.templates_dir_hot_reload = templates_dir_hot_reload
        self._lock = threading.RLock()
        self._filesystem_definitions: list[dict[str, Any]] = []
        self._filesystem_fingerprint: tuple[tuple[str, int, int], ...] = ()
        self._behaviors: list[Behavior] = []
        self._active_definitions: list[dict[str, Any]] = []
        self.reload()

    def behaviors(self) -> list[Behavior]:
        with self._lock:
            if self.templates_dir_hot_reload:
                self._reload_filesystem_if_changed_locked()
            return list(self._behaviors)

    def active_definitions(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._active_definitions)

    def reload(self) -> None:
        with self._lock:
            self._load_filesystem_locked()
            self._reload_locked()

    def _load_filesystem_locked(self) -> None:
        self._filesystem_definitions = load_mock_definitions(self.templates_dir)
        self._filesystem_fingerprint = _templates_dir_fingerprint(self.templates_dir)

    def _reload_filesystem_if_changed_locked(self) -> None:
        fingerprint = _templates_dir_fingerprint(self.templates_dir)
        if fingerprint == self._filesystem_fingerprint:
            return
        self._filesystem_definitions = load_mock_definitions(self.templates_dir)
        self._filesystem_fingerprint = fingerprint
        self._reload_locked()

    def _reload_locked(self) -> None:
        definitions = self._combined_definitions_locked()
        behaviors, active_definitions = build_behaviors_from_definitions(definitions, self.templates_dir, self.logger)
        self._behaviors = behaviors
        self._active_definitions = active_definitions

    def _combined_definitions_locked(self) -> list[dict[str, Any]]:
        definitions = copy.deepcopy(self._filesystem_definitions)
        definitions.extend(self._read_base_definitions_locked())
        for set_key in sorted(self._read_template_set_keys_locked()):
            definitions.extend(self._read_template_set_locked(set_key))
        return definitions

    def _validate_combined_locked(
        self,
        base_definitions: list[dict[str, Any]] | None = None,
        template_sets: dict[str, list[dict[str, Any]]] | None = None,
    ) -> tuple[list[Behavior], list[dict[str, Any]]]:
        if self.templates_dir_hot_reload:
            self._reload_filesystem_if_changed_locked()
        definitions = copy.deepcopy(self._filesystem_definitions)
        definitions.extend(base_definitions if base_definitions is not None else self._read_base_definitions_locked())
        if template_sets is None:
            set_keys = self._read_template_set_keys_locked()
            template_sets = {set_key: self._read_template_set_locked(set_key) for set_key in set_keys}
        for set_key in sorted(template_sets):
            definitions.extend(template_sets[set_key])
        return build_behaviors_from_definitions(definitions, self.templates_dir, self.logger)

    def _read_base_definitions_locked(self) -> list[dict[str, Any]]:
        return _mock_definitions_from_json(_redis_internal_do(self.redis_store, "GET", INTERNAL_TEMPLATES_KEY))

    def _write_base_definitions_locked(self, definitions: list[dict[str, Any]]) -> None:
        if definitions:
            _redis_internal_do(self.redis_store, "SET", INTERNAL_TEMPLATES_KEY, _canonical_mock_json(definitions))
        else:
            _redis_internal_do(self.redis_store, "DEL", INTERNAL_TEMPLATES_KEY)

    def _template_set_storage_key(self, set_key: str) -> str:
        return INTERNAL_TEMPLATE_SET_PREFIX + set_key

    def _read_template_set_keys_locked(self) -> list[str]:
        result = _redis_internal_do(self.redis_store, "KEYS", INTERNAL_TEMPLATE_SET_PREFIX + "*")
        if not result:
            return []
        keys = result.split(";;")
        return [key[len(INTERNAL_TEMPLATE_SET_PREFIX) :] for key in keys if key.startswith(INTERNAL_TEMPLATE_SET_PREFIX)]

    def _read_template_set_locked(self, set_key: str) -> list[dict[str, Any]]:
        return _mock_definitions_from_json(_redis_internal_do(self.redis_store, "GET", self._template_set_storage_key(set_key)))

    def _write_template_set_locked(self, set_key: str, definitions: list[dict[str, Any]]) -> None:
        _redis_internal_do(self.redis_store, "SET", self._template_set_storage_key(set_key), _canonical_mock_json(definitions))

    def upsert_base_definitions(self, submitted: Any) -> list[dict[str, Any]]:
        submitted_definitions = validate_mock_definition_array(submitted)
        submitted_keys = {definition["key"] for definition in submitted_definitions}
        with self._lock:
            base_definitions = [
                definition
                for definition in self._read_base_definitions_locked()
                if definition["key"] not in submitted_keys
            ]
            base_definitions.extend(submitted_definitions)
            self._validate_combined_locked(base_definitions=base_definitions)
            self._write_base_definitions_locked(base_definitions)
            self._reload_locked()
        return copy.deepcopy(submitted_definitions)

    def delete_all_base_definitions(self) -> None:
        with self._lock:
            self._write_base_definitions_locked([])
            self._reload_locked()

    def delete_base_definition(self, template_key: str) -> None:
        with self._lock:
            base_definitions = self._read_base_definitions_locked()
            kept = [definition for definition in base_definitions if definition["key"] != template_key]
            if len(kept) == len(base_definitions):
                raise KeyError(template_key)
            self._validate_combined_locked(base_definitions=kept)
            self._write_base_definitions_locked(kept)
            self._reload_locked()

    def replace_template_set(self, set_key: str, submitted: Any) -> list[dict[str, Any]]:
        if not set_key:
            raise ValidationError("template set key must be non-empty")
        submitted_definitions = validate_mock_definition_array(submitted)
        with self._lock:
            template_sets = {key: self._read_template_set_locked(key) for key in self._read_template_set_keys_locked()}
            template_sets[set_key] = submitted_definitions
            self._validate_combined_locked(template_sets=template_sets)
            self._write_template_set_locked(set_key, submitted_definitions)
            self._reload_locked()
        return copy.deepcopy(submitted_definitions)

    def delete_template_set(self, set_key: str) -> None:
        if not set_key:
            raise ValidationError("template set key must be non-empty")
        with self._lock:
            template_sets = {key: self._read_template_set_locked(key) for key in self._read_template_set_keys_locked()}
            template_sets.pop(set_key, None)
            self._validate_combined_locked(template_sets=template_sets)
            _redis_internal_do(self.redis_store, "DEL", self._template_set_storage_key(set_key))
            self._reload_locked()


class HeaderMap:
    def __init__(self, headers: dict[str, str] | Iterable[tuple[str, str]]) -> None:
        self._values: dict[str, str] = {}
        for key, value in dict(headers).items():
            self._values[key.lower()] = str(value)

    def Get(self, name: str) -> str:
        return self._values.get(str(name).lower(), "")


class ValueMap:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def Get(self, name: str) -> Any:
        return self._values.get(str(name), "")


def build_template_context(
    headers: dict[str, str] | Iterable[tuple[str, str]],
    body: str,
    path: str,
    query: str,
    path_params: dict[str, str] | None = None,
    redis_do: Callable[[str], str] | None = None,
    values: dict[str, Any] | None = None,
    templates: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path_params = path_params or {}
    context: dict[str, Any] = {
        "HTTPHeader": HeaderMap(headers),
        "HTTPBody": body,
        "HTTPPath": path,
        "HTTPQueryString": query,
        "HTTPPathParams": ValueMap(path_params),
        "HTTPURL": ValueMap(path_params),
        "Values": dict(values or {}),
    }
    if redis_do is not None:
        context["redisDo"] = redis_do
    if templates is not None:
        context["__templates"] = templates
    if extra:
        context.update(extra)
    return context


def preprocess_template(source: str) -> str:
    return str(source).replace("\r\n", " ").replace("\n", " ").replace("\t", " ")


@dataclasses.dataclass
class TextNode:
    text: str


@dataclasses.dataclass
class ExprNode:
    expr: str


@dataclasses.dataclass
class AssignNode:
    name: str
    expr: str


@dataclasses.dataclass
class IfNode:
    expr: str
    yes: list[Any]
    no: list[Any]


@dataclasses.dataclass
class RangeNode:
    index_name: str | None
    value_name: str
    expr: str
    body: list[Any]


def _action_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("-"):
        text = text[1:].lstrip()
    if text.endswith("-"):
        text = text[:-1].rstrip()
    return text


def _tokenize_template(source: str) -> list[tuple[str, str]]:
    source = preprocess_template(source)
    pattern = re.compile(r"({{.*?}})")
    tokens: list[tuple[str, str]] = []
    position = 0
    for match in pattern.finditer(source):
        if match.start() > position:
            tokens.append(("text", source[position : match.start()]))
        inner = match.group(1)[2:-2]
        tokens.append(("action", _action_text(inner)))
        position = match.end()
    if position < len(source):
        tokens.append(("text", source[position:]))
    return tokens


def _parse_template_nodes(tokens: list[tuple[str, str]], index: int = 0, stops: set[str] | None = None) -> tuple[list[Any], int, str | None]:
    stops = stops or set()
    nodes: list[Any] = []
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "text":
            nodes.append(TextNode(value))
            index += 1
            continue
        if value in stops:
            return nodes, index, value
        if value.startswith("if "):
            yes, next_index, stop = _parse_template_nodes(tokens, index + 1, {"else", "end"})
            no: list[Any] = []
            if stop == "else":
                no, next_index, stop = _parse_template_nodes(tokens, next_index + 1, {"end"})
            if stop != "end":
                raise TemplateError("if missing end")
            nodes.append(IfNode(value[3:].strip(), yes, no))
            index = next_index + 1
            continue
        if value.startswith("range "):
            index_name, value_name, expr = _parse_range(value[6:].strip())
            body, next_index, stop = _parse_template_nodes(tokens, index + 1, {"end"})
            if stop != "end":
                raise TemplateError("range missing end")
            nodes.append(RangeNode(index_name, value_name, expr, body))
            index = next_index + 1
            continue
        if ":=" in value and value.strip().startswith("$"):
            name, expr = value.split(":=", 1)
            nodes.append(AssignNode(name.strip(), expr.strip()))
            index += 1
            continue
        nodes.append(ExprNode(value))
        index += 1
    return nodes, index, None


def _parse_range(value: str) -> tuple[str | None, str, str]:
    if ":=" not in value:
        return None, "$value", value
    names, expr = value.split(":=", 1)
    parts = [part.strip() for part in names.split(",")]
    if len(parts) == 1:
        return None, parts[0], expr.strip()
    return parts[0], parts[1], expr.strip()


def render_template(source: str, context: Any) -> str:
    tokens = _tokenize_template(source)
    nodes, _, stop = _parse_template_nodes(tokens)
    if stop is not None:
        raise TemplateError(f"unexpected {stop}")
    return _render_nodes(nodes, context, {})


def _render_nodes(nodes: list[Any], context: dict[str, Any], locals_: dict[str, Any]) -> str:
    out: list[str] = []
    for node in nodes:
        if isinstance(node, TextNode):
            out.append(node.text)
        elif isinstance(node, ExprNode):
            out.append(_to_string(_eval_expr(node.expr, context, locals_)))
        elif isinstance(node, AssignNode):
            locals_[node.name] = _eval_expr(node.expr, context, locals_)
        elif isinstance(node, IfNode):
            selected = node.yes if _truthy(_eval_expr(node.expr, context, locals_)) else node.no
            out.append(_render_nodes(selected, context, dict(locals_)))
        elif isinstance(node, RangeNode):
            collection = _eval_expr(node.expr, context, locals_)
            for i, value in _iter_collection(collection):
                next_locals = dict(locals_)
                if node.index_name:
                    next_locals[node.index_name] = i
                next_locals[node.value_name] = value
                out.append(_render_nodes(node.body, context, next_locals))
        else:
            raise TemplateError(f"unknown template node: {node}")
    return "".join(out)


def _iter_collection(value: Any) -> Iterable[tuple[Any, Any]]:
    if isinstance(value, dict):
        return value.items()
    if isinstance(value, (list, tuple, str)):
        return enumerate(value)
    raise TemplateError("range value is not iterable")


def _split_pipeline(expr: str) -> list[str]:
    return _split_outside(expr, "|")


def _split_outside(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote = ""
    escaped = False
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            continue
        if ch == separator:
            parts.append(text[start:i].strip())
            start = i + 1
    parts.append(text[start:].strip())
    return parts


def _split_args(expr: str) -> list[str]:
    lexer = shlex.shlex(expr, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.quotes = "\"'`"
    return list(lexer)


def _eval_expr(expr: str, context: dict[str, Any], locals_: dict[str, Any]) -> Any:
    pieces = _split_pipeline(expr)
    if not pieces or not pieces[0]:
        return ""
    value = _eval_command(pieces[0], context, locals_)
    for command in pieces[1:]:
        tokens = _split_args(command)
        if not tokens:
            continue
        func = tokens[0]
        args = [_eval_atom(token, context, locals_) for token in tokens[1:]]
        args.append(value)
        value = _call_function(func, args, context)
    return value


def _eval_command(command: str, context: dict[str, Any], locals_: dict[str, Any]) -> Any:
    tokens = _split_args(command)
    if not tokens:
        return ""
    if len(tokens) == 1:
        if tokens[0] in FUNCTIONS or callable(_context_get(context, tokens[0])):
            return _call_function(tokens[0], [], context)
        return _eval_atom(tokens[0], context, locals_)
    first = tokens[0]
    if first == "template":
        return _render_named_template([_eval_atom(token, context, locals_) for token in tokens[1:]], context)
    if first in FUNCTIONS or callable(_context_get(context, first)):
        return _call_function(first, [_eval_atom(token, context, locals_) for token in tokens[1:]], context)
    value = _eval_atom(first, context, locals_)
    if callable(value):
        return value(*[_eval_atom(token, context, locals_) for token in tokens[1:]])
    raise TemplateError(f"{first} is not callable")


def _eval_atom(token: str, context: dict[str, Any], locals_: dict[str, Any]) -> Any:
    if token == "":
        return ""
    if token.startswith("$"):
        if token not in locals_:
            raise TemplateError(f"undefined variable {token}")
        return locals_[token]
    if token.startswith("."):
        return _resolve_path(token[1:], context)
    if token in ("true", "false"):
        return token == "true"
    if token in ("nil", "null"):
        return None
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    return token


def _context_get(context: Any, name: str) -> Any:
    if isinstance(context, dict):
        return context.get(name)
    return getattr(context, name, None)


def _resolve_path(path: str, context: Any) -> Any:
    if path == "":
        return context
    parts = path.split(".") if path else []
    if not parts:
        return context
    if isinstance(context, dict):
        if parts[0] not in context:
            raise TemplateError(f"undefined variable .{path}")
        value: Any = context[parts[0]]
    elif hasattr(context, parts[0]):
        value = getattr(context, parts[0])
    else:
        raise TemplateError(f"undefined variable .{path}")
    for part in parts[1:]:
        if isinstance(value, dict):
            if part not in value:
                raise TemplateError(f"undefined variable .{path}")
            value = value[part]
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            raise TemplateError(f"undefined variable .{path}")
    return value


def _render_named_template(args: list[Any], context: Any) -> str:
    if len(args) != 2:
        raise TemplateError("template expects name and context")
    name = args[0]
    if not isinstance(name, str):
        raise TemplateError("template name must be a string")
    templates = _context_get(context, "__templates")
    if not isinstance(templates, dict) or name not in templates:
        raise TemplateError(f"undefined template {name}")
    nested_context = args[1]
    if isinstance(nested_context, dict):
        next_context = dict(nested_context)
        next_context.setdefault("__templates", templates)
    else:
        next_context = nested_context
    return render_template(templates[name], next_context)


def _truthy(value: Any) -> bool:
    return not _empty(value)


def _empty(value: Any) -> bool:
    return value is None or value is False or value == "" or value == 0 or value == [] or value == {}


def _to_string(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


def _number(value: Any) -> float | int:
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return float(text)


def _compare(a: Any, b: Any, op: str) -> bool:
    try:
        left = _number(a)
        right = _number(b)
    except (TypeError, ValueError):
        left = str(a)
        right = str(b)
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "lt":
        return left < right
    if op == "gt":
        return left > right
    if op == "le":
        return left <= right
    if op == "ge":
        return left >= right
    raise TemplateError(f"unknown comparison {op}")


def _call_function(name: str, args: list[Any], context: dict[str, Any] | None = None) -> Any:
    if name in FUNCTIONS:
        return FUNCTIONS[name](*args)
    value = _context_get(context, name) if context is not None else None
    if callable(value):
        return value(*args)
    raise TemplateError(f"undefined function {name}")


def _printf(fmt: Any, *args: Any) -> str:
    text = str(fmt)
    if not args:
        return text
    try:
        return text % tuple(args)
    except (TypeError, ValueError):
        return text.format(*args)


def _js(value: Any) -> str:
    return json.dumps(str(value))[1:-1]


def _index(collection: Any, key: Any) -> Any:
    try:
        return collection[key]
    except (KeyError, IndexError, TypeError):
        if isinstance(collection, (list, tuple)) and str(key).isdigit():
            return collection[int(key)]
        raise TemplateError("index lookup failed")


def _contains(needle: Any, haystack: Any) -> bool:
    return str(needle) in str(haystack)


def _replace(old: Any, new: Any, source: Any) -> str:
    return str(source).replace(str(old), str(new))


def _split(sep: Any, source: Any) -> list[str]:
    return str(source).split(str(sep))


def _join(sep: Any, values: Any) -> str:
    return str(sep).join(str(v) for v in values)


def _default(default: Any, value: Any) -> Any:
    return default if _empty(value) else value


def _coalesce(*values: Any) -> Any:
    for value in values:
        if not _empty(value):
            return value
    return ""


def _ternary(yes: Any, no: Any, condition: Any) -> Any:
    return yes if _truthy(condition) else no


def _b64enc(value: Any) -> str:
    return base64.b64encode(str(value).encode()).decode()


def _b64dec(value: Any) -> str:
    return base64.b64decode(str(value).encode()).decode()


def _math(op: str, *args: Any) -> Any:
    nums = [_number(arg) for arg in args]
    if not nums:
        return 0
    result = nums[0]
    for value in nums[1:]:
        if op == "add":
            result += value
        elif op == "sub":
            result -= value
        elif op == "mul":
            result *= value
        elif op == "div":
            result /= value
        elif op == "mod":
            result %= value
    if op == "max":
        result = max(nums)
    if op == "min":
        result = min(nums)
    return int(result) if isinstance(result, float) and result.is_integer() else result


def _parse_json_data(data: Any, *, fail_invalid: bool) -> Any:
    if _empty(data):
        return None
    try:
        return json.loads(str(data))
    except json.JSONDecodeError as exc:
        if fail_invalid:
            raise TemplateError("invalid JSON") from exc
        return None


def _json_value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _find_recursive_json(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        if name in value:
            return value[name]
        for child in value.values():
            found = _find_recursive_json(child, name)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_recursive_json(child, name)
            if found is not None:
                return found
    return None


def _json_path(expr: Any, data: Any) -> str:
    parsed = _parse_json_data(data, fail_invalid=False)
    if parsed is None:
        return ""
    path = str(expr).strip()
    if not path:
        return ""
    if path.startswith("//"):
        return _json_value_to_text(_find_recursive_json(parsed, path[2:]))
    value = parsed
    for part in path.strip("./").split("."):
        if part == "":
            continue
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return ""
    return _json_value_to_text(value)


def _gjson_lookup(value: Any, parts: list[str]) -> Any:
    if not parts:
        return value
    part = parts[0]
    rest = parts[1:]
    if part == "#":
        if not isinstance(value, list):
            return None
        if not rest:
            return len(value)
        results = []
        for item in value:
            found = _gjson_lookup(item, rest)
            if found is not None:
                results.append(found)
        return results
    if isinstance(value, dict):
        if part not in value:
            return None
        return _gjson_lookup(value[part], rest)
    if isinstance(value, list) and part.isdigit():
        index = int(part)
        if index >= len(value):
            return None
        return _gjson_lookup(value[index], rest)
    return None


def _gjson_path(expr: Any, data: Any) -> str:
    parsed = _parse_json_data(data, fail_invalid=True)
    if parsed is None:
        return ""
    path = str(expr).strip()
    if not path:
        return ""
    found = _gjson_lookup(parsed, path.split("."))
    return _json_value_to_text(found)


def _xml_inner_text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _xml_path(expr: Any, data: Any) -> str:
    if _empty(data):
        return ""
    try:
        root = ET.fromstring(str(data))
    except ET.ParseError as exc:
        raise TemplateError("invalid XML") from exc
    path = str(expr).strip()
    if not path:
        return ""
    if path.startswith("//"):
        path = ".//" + path[2:]
    elif path.startswith("/"):
        parts = [part for part in path.strip("/").split("/") if part]
        if parts and parts[0] == root.tag:
            parts = parts[1:]
        path = "./" + "/".join(parts) if parts else "."
    elif not path.startswith("."):
        path = "./" + path
    found = root if path == "." else root.find(path)
    return _xml_inner_text(found) if found is not None else ""


def _regex_all_submatches(pattern: Any, source: Any) -> list[str]:
    match = re.search(str(pattern), str(source))
    if not match:
        return []
    groups = [match.group(0)]
    groups.extend(group if group is not None else "" for group in match.groups(default=""))
    return groups


def _regex_first_submatch(pattern: Any, source: Any) -> str:
    groups = _regex_all_submatches(pattern, source)
    return groups[1] if len(groups) > 1 else ""


def _hmac_sha256(secret: Any, data: Any) -> str:
    digest = hmac.new(str(secret).encode(), str(data).encode(), hashlib.sha256)
    return digest.hexdigest()


def _is_last_index(index: Any, array: Any) -> bool:
    try:
        return int(index) == len(array) - 1
    except (TypeError, ValueError):
        return False


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "eq": lambda a, b: _compare(a, b, "eq"),
    "ne": lambda a, b: _compare(a, b, "ne"),
    "lt": lambda a, b: _compare(a, b, "lt"),
    "gt": lambda a, b: _compare(a, b, "gt"),
    "le": lambda a, b: _compare(a, b, "le"),
    "ge": lambda a, b: _compare(a, b, "ge"),
    "and": lambda *args: all(_truthy(arg) for arg in args),
    "or": lambda *args: any(_truthy(arg) for arg in args),
    "not": lambda arg: not _truthy(arg),
    "print": lambda *args: "".join(_to_string(arg) for arg in args),
    "printf": _printf,
    "println": lambda *args: " ".join(_to_string(arg) for arg in args) + "\n",
    "html": lambda value: html_lib.escape(str(value)),
    "js": _js,
    "urlquery": lambda value: quote_plus(str(value)),
    "len": lambda value: len(value),
    "index": _index,
    "call": lambda fn, *args: fn(*args),
    "contains": _contains,
    "hasPrefix": lambda prefix, source: str(source).startswith(str(prefix)),
    "hasSuffix": lambda suffix, source: str(source).endswith(str(suffix)),
    "replace": _replace,
    "trim": lambda value: str(value).strip(),
    "upper": lambda value: str(value).upper(),
    "lower": lambda value: str(value).lower(),
    "title": lambda value: str(value).title(),
    "split": _split,
    "splitList": _split,
    "join": _join,
    "repeat": lambda count, value: str(value) * int(count),
    "nospace": lambda value: re.sub(r"\s+", "", str(value)),
    "toString": _to_string,
    "default": _default,
    "empty": _empty,
    "coalesce": _coalesce,
    "ternary": _ternary,
    "b64enc": _b64enc,
    "b64dec": _b64dec,
    "env": lambda name: os.environ.get(str(name), ""),
    "add": lambda *args: _math("add", *args),
    "sub": lambda *args: _math("sub", *args),
    "mul": lambda *args: _math("mul", *args),
    "div": lambda *args: _math("div", *args),
    "mod": lambda *args: _math("mod", *args),
    "max": lambda *args: _math("max", *args),
    "min": lambda *args: _math("min", *args),
    "uuidv4": lambda: str(uuid.uuid4()),
    "jsonPath": _json_path,
    "gJsonPath": _gjson_path,
    "xmlPath": _xml_path,
    "uuidv5": lambda data: str(uuid.uuid5(uuid.NAMESPACE_OID, str(data))),
    "regexFindAllSubmatch": _regex_all_submatches,
    "regexFindFirstSubmatch": _regex_first_submatch,
    "hmacSHA256": _hmac_sha256,
    "isLastIndex": _is_last_index,
    "htmlEscapeString": lambda value: html_lib.escape(str(value), quote=True),
}


@dataclasses.dataclass
class RequestInfo:
    method: str
    path: str
    route_path: str
    query: str
    host: str
    headers: dict[str, str]
    body: str


@dataclasses.dataclass
class ResponseInfo:
    status_code: int
    headers: dict[str, str]
    body: str | bytes

    def body_bytes(self) -> bytes:
        return self.body if isinstance(self.body, bytes) else self.body.encode()

    def body_text_for_log(self) -> str:
        if isinstance(self.body, str):
            return self.body
        return base64.b64encode(self.body).decode()


@dataclasses.dataclass
class KafkaMessage:
    topic: str
    payload: str


@dataclasses.dataclass
class AMQPMessage:
    exchange: str
    routing_key: str
    queue: str
    payload: str


class ConfluentKafkaAdapter:
    def __init__(self, config: KafkaConfig) -> None:
        module = importlib.import_module("confluent_kafka")
        producer_config = self._client_config(config.client_id, config.producer)
        consumer_config = self._client_config(config.client_id, config.consumer)
        consumer_config.setdefault("group.id", f"{config.client_id}-hmock")
        consumer_config.setdefault("auto.offset.reset", "latest")
        self._producer = module.Producer(producer_config)
        self._consumer = module.Consumer(consumer_config)
        self._topics: tuple[str, ...] = ()

    def _client_config(self, client_id: str, client: KafkaClientConfig) -> dict[str, Any]:
        protocol = "SASL_SSL" if client.sasl_enabled and client.tls_enabled else "SASL_PLAINTEXT" if client.sasl_enabled else "SSL" if client.tls_enabled else "PLAINTEXT"
        config: dict[str, Any] = {
            "bootstrap.servers": ",".join(client.seed_brokers),
            "client.id": client_id,
            "security.protocol": protocol,
        }
        if client.sasl_enabled:
            config.update(
                {
                    "sasl.mechanism": "PLAIN",
                    "sasl.username": client.sasl_username,
                    "sasl.password": client.sasl_password,
                }
            )
        return config

    def subscribe(self, topics: Iterable[str]) -> None:
        next_topics = tuple(dict.fromkeys(topics))
        if next_topics == self._topics:
            return
        self._consumer.subscribe(list(next_topics))
        self._topics = next_topics

    def poll(self, timeout: float = 1.0) -> KafkaMessage | None:
        message = self._consumer.poll(timeout)
        if message is None:
            return None
        if hasattr(message, "error") and message.error():
            raise RuntimeError(str(message.error()))
        payload = message.value()
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        return KafkaMessage(message.topic(), str(payload or ""))

    def publish(self, topic: str, payload: str) -> None:
        self._producer.produce(topic, payload.encode())
        self._producer.poll(0)

    def close(self) -> None:
        self._producer.flush(2)
        self._consumer.close()


class PikaAMQPAdapter:
    def __init__(self, config: AMQPConfig) -> None:
        self.url = config.url
        self._pika = importlib.import_module("pika")
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._bindings: dict[str, tuple[str, str]] = {}
        self.reconnect()

    def reconnect(self) -> None:
        self.close()
        params = self._pika.URLParameters(self.url)
        self._connection = self._pika.BlockingConnection(params)
        self._channel = self._connection.channel()

    def ensure_binding(self, exchange: str, routing_key: str, queue_name: str) -> None:
        if self._channel is None:
            self.reconnect()
        self._channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
        self._channel.queue_declare(queue=queue_name, durable=True)
        self._channel.queue_bind(exchange=exchange, queue=queue_name, routing_key=routing_key)
        self._bindings[queue_name] = (exchange, routing_key)

    def consume_once(self, timeout: float = 1.0) -> AMQPMessage | None:
        if self._channel is None:
            self.reconnect()
        deadline = time.monotonic() + timeout
        while time.monotonic() <= deadline:
            for queue_name, fallback in list(self._bindings.items()):
                method, _, body = self._channel.basic_get(queue_name, auto_ack=True)
                if method is None:
                    continue
                exchange = getattr(method, "exchange", "") or fallback[0]
                routing_key = getattr(method, "routing_key", "") or fallback[1]
                payload = body.decode(errors="replace") if isinstance(body, bytes) else str(body or "")
                return AMQPMessage(exchange, routing_key, queue_name, payload)
            time.sleep(0.05)
        return None

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        if self._channel is None:
            self.reconnect()
        self._channel.basic_publish(exchange=exchange, routing_key=routing_key, body=payload.encode())

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
        self._connection = None
        self._channel = None


def build_kafka_adapter(config: KafkaConfig) -> Any | None:
    if not config.enabled:
        return None
    try:
        return ConfluentKafkaAdapter(config)
    except ModuleNotFoundError as exc:
        raise ValidationError("Kafka support requires the confluent_kafka package") from exc


def build_amqp_adapter(config: AMQPConfig) -> Any | None:
    if not config.enabled:
        return None
    try:
        return PikaAMQPAdapter(config)
    except ModuleNotFoundError as exc:
        raise ValidationError("AMQP support requires the pika package") from exc


def find_behavior(
    behaviors: list[Behavior],
    request: RequestInfo,
    redis_store: RedisStore | None = None,
) -> tuple[Behavior, dict[str, str]] | tuple[None, dict[str, str]]:
    for behavior in behaviors:
        if behavior.expectation_type != "http":
            continue
        if behavior.method != request.method.upper():
            continue
        if behavior.pattern is None:
            continue
        params = behavior.pattern.match(request.route_path)
        if params is None:
            continue
        if not behavior.condition:
            return behavior, params
        context = build_template_context(
            request.headers,
            request.body,
            request.path,
            request.query,
            params,
            redis_store.do if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                return behavior, params
        except TemplateError:
            continue
    return None, {}


def _condition_matches(behavior: Behavior, context: dict[str, Any]) -> bool:
    if not behavior.condition:
        return True
    try:
        return render_template(behavior.condition, context) == "true"
    except TemplateError:
        return False


def build_kafka_template_context(
    topic: str,
    payload: str,
    behavior: Behavior,
    redis_store: RedisStore | None = None,
) -> dict[str, Any]:
    return build_template_context(
        {},
        "",
        "",
        "",
        {},
        redis_store.do if redis_store is not None else None,
        behavior.values,
        behavior.templates,
        {"KafkaTopic": topic, "KafkaPayload": payload},
    )


def find_kafka_behaviors(
    behaviors: list[Behavior],
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
) -> list[Behavior]:
    matches: list[Behavior] = []
    for behavior in behaviors:
        if behavior.expectation_type != "kafka" or behavior.kafka_topic != topic:
            continue
        context = build_kafka_template_context(topic, payload, behavior, redis_store)
        if _condition_matches(behavior, context):
            matches.append(behavior)
    return matches


def build_amqp_template_context(
    exchange: str,
    routing_key: str,
    queue_name: str,
    payload: str,
    behavior: Behavior,
    redis_store: RedisStore | None = None,
) -> dict[str, Any]:
    return build_template_context(
        {},
        "",
        "",
        "",
        {},
        redis_store.do if redis_store is not None else None,
        behavior.values,
        behavior.templates,
        {
            "AMQPExchange": exchange,
            "AMQPRoutingKey": routing_key,
            "AMQPQueue": queue_name,
            "AMQPPayload": payload,
        },
    )


def find_amqp_behaviors(
    behaviors: list[Behavior],
    exchange: str,
    routing_key: str,
    queue_name: str,
    payload: str,
    redis_store: RedisStore | None = None,
) -> list[Behavior]:
    matches: list[Behavior] = []
    for behavior in behaviors:
        if behavior.expectation_type != "amqp":
            continue
        if behavior.amqp_exchange != exchange or behavior.amqp_routing_key != routing_key or behavior.amqp_queue != queue_name:
            continue
        context = build_amqp_template_context(exchange, routing_key, queue_name, payload, behavior, redis_store)
        if _condition_matches(behavior, context):
            matches.append(behavior)
    return matches


def _pop_header_case_insensitive(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    for key in list(headers):
        if key.lower() == expected:
            return headers.pop(key)
    return None


def _multipart_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _multipart_file_body(field_name: str, filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----hmock-" + uuid.uuid4().hex
    disposition = (
        f'Content-Disposition: form-data; name="{_multipart_escape(field_name)}"; '
        f'filename="{_multipart_escape(filename)}"'
    )
    head = (
        f"--{boundary}\r\n"
        f"{disposition}\r\n"
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + data + tail, boundary


def _send_http(payload: dict[str, Any], context: dict[str, Any], logger: JsonLogger | None = None) -> None:
    url = render_template(str(payload["url"]), context)
    method = render_template(str(payload["method"]), context).upper()
    headers = {
        str(key): render_template(str(value), context)
        for key, value in (payload.get("headers") or {}).items()
    }
    body_source = payload.get("body")
    data: bytes | None
    if body_source is not None and body_source != "":
        data = render_template(str(body_source), context).encode()
    elif "send_http_body_from_binary_file_content" in payload:
        binary_data = payload["send_http_body_from_binary_file_content"]
        if method == "POST":
            file_content_type = _pop_header_case_insensitive(headers, "Content-Type") or "application/octet-stream"
            filename = payload.get("binary_file_name") or posixpath.basename(str(payload.get("body_from_binary_file", "file")))
            data, boundary = _multipart_file_body("file", str(filename), file_content_type, binary_data)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            data = binary_data
    else:
        if body_source is None or body_source == "":
            body_source = payload.get("send_http_body_from_file_content")
        body = render_template(str(body_source), context) if body_source is not None else None
        data = body.encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
    except Exception as exc:
        if logger is not None:
            logger.warn("send_http request failed", url=url, method=method, error=str(exc))


def _render_publish_payload(action_name: str, payload: dict[str, Any], context: dict[str, Any]) -> str:
    body_source = payload.get("payload")
    if body_source is None or body_source == "":
        body_source = payload.get(f"{action_name}_payload_from_file_content", "")
    return render_template(str(body_source), context)


def _publish_kafka(payload: dict[str, Any], context: dict[str, Any], publisher: Any | None) -> None:
    if publisher is None:
        return
    topic = render_template(str(payload["topic"]), context)
    publisher.publish(topic, _render_publish_payload("publish_kafka", payload, context))


def _publish_amqp(payload: dict[str, Any], context: dict[str, Any], publisher: Any | None) -> None:
    if publisher is None:
        return
    exchange = render_template(str(payload["exchange"]), context)
    routing_key = render_template(str(payload["routing_key"]), context)
    publisher.publish(exchange, routing_key, _render_publish_payload("publish_amqp", payload, context))


def execute_actions(
    behavior: Behavior,
    context: dict[str, Any],
    redis_store: RedisStore,
    logger: JsonLogger | None = None,
    kafka_publisher: Any | None = None,
    amqp_publisher: Any | None = None,
    include_reply_http: bool = True,
) -> ResponseInfo | None:
    response: ResponseInfo | None = None
    for action in behavior.actions:
        name, payload = _action_name_payload(action, behavior.key)
        if name == "sleep":
            time.sleep(parse_duration(str(payload["duration"])))
        elif name == "redis":
            for command_template in payload:
                redis_store.do(render_template(command_template, context))
        elif name == "send_http":
            _send_http(payload, context, logger)
        elif name == "publish_kafka":
            _publish_kafka(payload, context, kafka_publisher)
        elif name == "publish_amqp":
            _publish_amqp(payload, context, amqp_publisher)
        elif name == "reply_http" and include_reply_http:
            body_source = payload.get("body")
            binary_body: bytes | None = None
            if (body_source is None or body_source == "") and "body_from_binary_file_content" in payload:
                binary_body = payload["body_from_binary_file_content"]
            elif body_source is None or body_source == "":
                body_source = payload.get("body_from_file_content", "")
            body: str | bytes = binary_body if binary_body is not None else render_template(str(body_source), context)
            headers = {
                str(key): render_template(str(value), context)
                for key, value in (payload.get("headers") or {}).items()
            }
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "application/json"
            if binary_body is not None and payload.get("binary_file_name"):
                headers["Content-Disposition"] = f'inline; filename="{payload["binary_file_name"]}"'
            headers["Content-Length"] = str(len(body if isinstance(body, bytes) else body.encode()))
            response = ResponseInfo(int(payload["status_code"]), headers, body)
    return response


def execute_behavior(
    behavior: Behavior,
    request: RequestInfo,
    params: dict[str, str],
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_publisher: Any | None = None,
    amqp_publisher: Any | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    context = build_template_context(
        request.headers,
        request.body,
        request.path,
        request.query,
        params,
        redis_store.do,
        behavior.values,
        behavior.templates,
    )
    response = execute_actions(
        behavior,
        context,
        redis_store,
        logger,
        kafka_publisher,
        amqp_publisher,
        include_reply_http=True,
    )
    return response or ResponseInfo(204, {"Content-Length": "0"}, "")


def execute_kafka_behavior(
    behavior: Behavior,
    topic: str,
    payload: str,
    redis_store: RedisStore,
    logger: JsonLogger | None = None,
    kafka_publisher: Any | None = None,
    amqp_publisher: Any | None = None,
) -> None:
    context = build_kafka_template_context(topic, payload, behavior, redis_store)
    execute_actions(
        behavior,
        context,
        redis_store,
        logger,
        kafka_publisher,
        amqp_publisher,
        include_reply_http=False,
    )


def execute_amqp_behavior(
    behavior: Behavior,
    exchange: str,
    routing_key: str,
    queue_name: str,
    payload: str,
    redis_store: RedisStore,
    logger: JsonLogger | None = None,
    kafka_publisher: Any | None = None,
    amqp_publisher: Any | None = None,
) -> None:
    context = build_amqp_template_context(exchange, routing_key, queue_name, payload, behavior, redis_store)
    execute_actions(
        behavior,
        context,
        redis_store,
        logger,
        kafka_publisher,
        amqp_publisher,
        include_reply_http=False,
    )


class KafkaBrokerService:
    def __init__(
        self,
        registry: ActiveMockRegistry | StaticMockRegistry,
        adapter: Any,
        redis_store: RedisStore,
        logger: JsonLogger,
        amqp_publisher: Any | None = None,
    ) -> None:
        self.registry = registry
        self.adapter = adapter
        self.redis_store = redis_store
        self.logger = logger
        self.amqp_publisher = amqp_publisher
        self._topics: tuple[str, ...] = ()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def referenced_topics(self) -> tuple[str, ...]:
        topics: list[str] = []
        for behavior in self.registry.behaviors():
            if behavior.expectation_type == "kafka" and behavior.kafka_topic and behavior.kafka_topic not in topics:
                topics.append(behavior.kafka_topic)
        return tuple(topics)

    def sync_subscriptions(self) -> None:
        topics = self.referenced_topics()
        if topics != self._topics:
            self.adapter.subscribe(topics)
            self._topics = topics

    def process_message(self, message: KafkaMessage) -> list[str]:
        matches = find_kafka_behaviors(self.registry.behaviors(), message.topic, message.payload, self.redis_store)
        for behavior in matches:
            execute_kafka_behavior(
                behavior,
                message.topic,
                message.payload,
                self.redis_store,
                self.logger,
                self.adapter,
                self.amqp_publisher,
            )
        if matches:
            self.logger.info("kafka message matched", kafka_topic=message.topic, behavior_keys=[b.key for b in matches])
        return [behavior.key for behavior in matches]

    def poll_once(self, timeout: float = 0.1) -> list[str]:
        self.sync_subscriptions()
        message = self.adapter.poll(timeout)
        if message is None:
            return []
        if not isinstance(message, KafkaMessage):
            message = KafkaMessage(str(message.topic), str(message.payload))
        return self.process_message(message)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once(0.5)
            except Exception as exc:
                self.logger.warn("kafka consumer failed", error=str(exc))
                self._stop.wait(0.5)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if hasattr(self.adapter, "close"):
            self.adapter.close()


class AMQPBrokerService:
    def __init__(
        self,
        registry: ActiveMockRegistry | StaticMockRegistry,
        adapter: Any,
        redis_store: RedisStore,
        logger: JsonLogger,
        kafka_publisher: Any | None = None,
    ) -> None:
        self.registry = registry
        self.adapter = adapter
        self.redis_store = redis_store
        self.logger = logger
        self.kafka_publisher = kafka_publisher
        self._resources: tuple[tuple[str, str, str], ...] = ()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def required_resources(self) -> tuple[tuple[str, str, str], ...]:
        resources: list[tuple[str, str, str]] = []
        for behavior in self.registry.behaviors():
            if behavior.expectation_type != "amqp":
                continue
            resource = (str(behavior.amqp_exchange), str(behavior.amqp_routing_key), str(behavior.amqp_queue))
            if resource not in resources:
                resources.append(resource)
        return tuple(resources)

    def ensure_resources(self, force: bool = False) -> None:
        resources = self.required_resources()
        if not force and resources == self._resources:
            return
        for exchange, routing_key, queue_name in resources:
            self.adapter.ensure_binding(exchange, routing_key, queue_name)
        self._resources = resources

    def process_message(self, message: AMQPMessage) -> list[str]:
        matches = find_amqp_behaviors(
            self.registry.behaviors(),
            message.exchange,
            message.routing_key,
            message.queue,
            message.payload,
            self.redis_store,
        )
        for behavior in matches:
            execute_amqp_behavior(
                behavior,
                message.exchange,
                message.routing_key,
                message.queue,
                message.payload,
                self.redis_store,
                self.logger,
                self.kafka_publisher,
                self.adapter,
            )
        if matches:
            self.logger.info(
                "amqp message matched",
                amqp_exchange=message.exchange,
                amqp_routing_key=message.routing_key,
                amqp_queue=message.queue,
                behavior_keys=[b.key for b in matches],
            )
        return [behavior.key for behavior in matches]

    def poll_once(self, timeout: float = 0.1) -> list[str]:
        self.ensure_resources()
        try:
            message = self.adapter.consume_once(timeout)
        except Exception as exc:
            self.logger.warn("amqp consumer failed", error=str(exc))
            if hasattr(self.adapter, "reconnect"):
                self.adapter.reconnect()
            self.ensure_resources(force=True)
            return []
        if message is None:
            return []
        if not isinstance(message, AMQPMessage):
            message = AMQPMessage(str(message.exchange), str(message.routing_key), str(message.queue), str(message.payload))
        return self.process_message(message)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once(0.5)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if hasattr(self.adapter, "close"):
            self.adapter.close()


def not_found_response() -> ResponseInfo:
    body = "not found"
    return ResponseInfo(
        404,
        {"Content-Type": "text/plain", "Content-Length": str(len(body.encode()))},
        body,
    )


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Credentials": "true",
}


def apply_cors(response: ResponseInfo) -> ResponseInfo:
    headers = dict(response.headers)
    existing = {key.lower() for key in headers}
    for key, value in CORS_HEADERS.items():
        if key.lower() not in existing:
            headers[key] = value
    return ResponseInfo(response.status_code, headers, response.body)


class MockHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "HMockHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle(send_body=False)

    def _handle(self, send_body: bool = True) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        split = urlsplit(self.path)
        route_path = posixpath.normpath(split.path)
        if split.path.startswith("/") and not route_path.startswith("/"):
            route_path = "/" + route_path
        if split.path == "/":
            route_path = "/"
        request = RequestInfo(
            method=self.command,
            path=self.path,
            route_path=route_path,
            query=split.query,
            host=self.headers.get("Host", ""),
            headers={key: value for key, value in self.headers.items()},
            body=body,
        )
        behavior, params = find_behavior(self.server.behaviors, request, self.server.redis_store)
        try:
            if behavior:
                response = execute_behavior(
                    behavior,
                    request,
                    params,
                    self.server.redis_store,
                    self.server.hm_logger,
                    self.server.kafka_publisher,
                    self.server.amqp_publisher,
                )
            elif self.command == "OPTIONS" and self.server.cors_enabled:
                response = ResponseInfo(200, {"Content-Length": "0"}, "")
            else:
                response = not_found_response()
        except TemplateError as exc:
            self.server.hm_logger.error("template render error", error=str(exc), http_path=request.path)
            response = ResponseInfo(
                500,
                {"Content-Type": "text/plain", "Content-Length": "21"},
                "template render error",
            )
        if self.server.cors_enabled:
            response = apply_cors(response)
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if send_body:
            self.wfile.write(response.body_bytes())
        self.server.hm_logger.info(
            "http request",
            http_path=request.path,
            http_method=request.method,
            http_host=request.host,
            http_req={
                "headers": request.headers,
                "body": request.body,
            },
            http_res={
                "status_code": response.status_code,
                "headers": response.headers,
                "body": response.body_text_for_log(),
            },
        )


class HMockHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        behaviors: list[Behavior] | ActiveMockRegistry | StaticMockRegistry,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        cors_enabled: bool = False,
        broker_services: list[Any] | None = None,
        kafka_publisher: Any | None = None,
        amqp_publisher: Any | None = None,
    ) -> None:
        super().__init__(address, MockHTTPRequestHandler)
        self.registry = behaviors if isinstance(behaviors, (ActiveMockRegistry, StaticMockRegistry)) else StaticMockRegistry(behaviors)
        self.hm_logger = logger
        self.redis_store = redis_store or MemoryRedisStore()
        self.cors_enabled = cors_enabled
        self.broker_services = list(broker_services or [])
        self.kafka_publisher = kafka_publisher
        self.amqp_publisher = amqp_publisher

    @property
    def behaviors(self) -> list[Behavior]:
        return self.registry.behaviors()

    def start_broker_services(self) -> None:
        for service in self.broker_services:
            service.start()

    def stop_broker_services(self) -> None:
        for service in reversed(self.broker_services):
            service.stop()


def _json_response(payload: Any, status_code: int = 200) -> ResponseInfo:
    body = json.dumps(payload, separators=(",", ":"))
    return ResponseInfo(
        status_code,
        {
            "Content-Type": "application/json",
            "Content-Length": str(len(body.encode())),
        },
        body,
    )


def _empty_response(status_code: int = 204) -> ResponseInfo:
    return ResponseInfo(status_code, {"Content-Length": "0"}, "")


def _text_response(message: str, status_code: int) -> ResponseInfo:
    return ResponseInfo(
        status_code,
        {"Content-Type": "text/plain", "Content-Length": str(len(message.encode()))},
        message,
    )


class AdminHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "HMockAdminServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def _read_payload(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        if not body:
            raise ValidationError("request body is required")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type in {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"}:
            parsed = parse_yaml_subset(body)
            return [] if parsed is None else parsed
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"invalid JSON: {exc}") from exc

    def _handle(self) -> None:
        split = urlsplit(self.path)
        route_path = posixpath.normpath(split.path)
        if split.path.startswith("/") and not route_path.startswith("/"):
            route_path = "/" + route_path
        if split.path == "/":
            route_path = "/"
        try:
            response = self._route(route_path)
        except ValidationError as exc:
            response = _json_response({"error": str(exc)}, 400)
        except KeyError:
            response = _text_response("not found", 404)
        except Exception as exc:
            self.server.hm_logger.error("admin request failed", error=str(exc), path=self.path)
            response = _text_response("internal server error", 500)
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if response.body:
            self.wfile.write(response.body.encode())

    def _route(self, route_path: str) -> ResponseInfo:
        if self.command == "GET" and route_path == "/api/v1/health":
            return _json_response({"status": "OK"})
        if self.command == "GET" and route_path == "/api/v1/templates":
            return _json_response(self.server.registry.active_definitions())
        if self.command == "POST" and route_path == "/api/v1/templates":
            return _json_response(self.server.registry.upsert_base_definitions(self._read_payload()))
        if self.command == "DELETE" and route_path == "/api/v1/templates":
            self.server.registry.delete_all_base_definitions()
            return _empty_response()
        template_prefix = "/api/v1/templates/"
        if self.command == "DELETE" and route_path.startswith(template_prefix):
            template_key = unquote(route_path[len(template_prefix) :])
            if not template_key:
                raise KeyError(template_key)
            self.server.registry.delete_base_definition(template_key)
            return _empty_response()
        set_prefix = "/api/v1/template_sets/"
        if route_path.startswith(set_prefix):
            set_key = unquote(route_path[len(set_prefix) :])
            if self.command == "POST":
                return _json_response(self.server.registry.replace_template_set(set_key, self._read_payload()))
            if self.command == "DELETE":
                self.server.registry.delete_template_set(set_key)
                return _empty_response()
        return _text_response("not found", 404)


class HMockAdminServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        registry: ActiveMockRegistry,
        logger: JsonLogger,
    ) -> None:
        super().__init__(address, AdminHTTPRequestHandler)
        self.registry = registry
        self.hm_logger = logger


def build_server(config: Config | None = None, logger: JsonLogger | None = None) -> HMockHTTPServer:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    redis_store = build_redis_store(config)
    registry = ActiveMockRegistry(config.templates_dir, redis_store, logger, config.templates_dir_hot_reload)
    kafka_adapter = build_kafka_adapter(config.kafka)
    amqp_adapter = build_amqp_adapter(config.amqp)
    broker_services: list[Any] = []
    if kafka_adapter is not None:
        broker_services.append(KafkaBrokerService(registry, kafka_adapter, redis_store, logger, amqp_adapter))
    if amqp_adapter is not None:
        broker_services.append(AMQPBrokerService(registry, amqp_adapter, redis_store, logger, kafka_adapter))
    return HMockHTTPServer(
        (config.http_host, config.http_port),
        registry,
        logger,
        redis_store,
        config.cors_enabled,
        broker_services,
        kafka_adapter,
        amqp_adapter,
    )


def build_admin_server(
    config: Config,
    registry: ActiveMockRegistry,
    logger: JsonLogger | None = None,
) -> HMockAdminServer | None:
    if not config.admin_http_enabled:
        return None
    return HMockAdminServer(
        (config.admin_http_host, config.admin_http_port),
        registry,
        logger or JsonLogger(config.log_level),
    )


def main() -> None:
    config = load_config()
    logger = JsonLogger(config.log_level)
    server = build_server(config, logger)
    admin_server = build_admin_server(config, server.registry, logger)
    admin_thread: threading.Thread | None = None
    if admin_server is not None:
        admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        admin_thread.start()
        logger.info("hmock admin server started", host=config.admin_http_host, port=config.admin_http_port)
    server.start_broker_services()
    logger.info("hmock server started", host=config.http_host, port=config.http_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("hmock server stopped")
    finally:
        if admin_server is not None:
            admin_server.shutdown()
            admin_server.server_close()
        if admin_thread is not None:
            admin_thread.join(timeout=2)
        server.stop_broker_services()
        server.server_close()


if __name__ == "__main__":
    main()
