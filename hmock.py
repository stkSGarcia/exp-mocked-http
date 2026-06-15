from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import html as html_lib
import hmac
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
from urllib.parse import quote_plus, unquote_plus, urlsplit


class HMockError(Exception):
    pass


class TemplateError(HMockError):
    pass


class RedisError(TemplateError):
    pass


class ValidationError(HMockError):
    pass


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
    kafka_enabled: bool = False
    kafka_client_id: str = "hmock"
    kafka_seed_brokers: str = "kafka:9092"
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""
    kafka_tls_enabled: bool = False
    kafka_producer_seed_brokers: str = ""
    kafka_consumer_seed_brokers: str = ""
    kafka_sasl_producer_username: str = ""
    kafka_sasl_producer_password: str = ""
    kafka_sasl_consumer_username: str = ""
    kafka_sasl_consumer_password: str = ""
    kafka_tls_producer_enabled: bool | None = None
    kafka_tls_consumer_enabled: bool | None = None
    amqp_enabled: bool = False
    amqp_url: str = "amqp://guest:guest@rabbitmq:5672"


@dataclasses.dataclass(frozen=True)
class KafkaClientConfig:
    client_id: str
    seed_brokers: tuple[str, ...]
    sasl_username: str
    sasl_password: str
    sasl_enabled: bool
    tls_enabled: bool


@dataclasses.dataclass(frozen=True)
class AMQPBinding:
    exchange: str
    routing_key: str
    queue: str


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return _env_bool(value, False)


def load_config(env: dict[str, str] | None = None) -> Config:
    env = env if env is not None else os.environ
    return Config(
        templates_dir=env.get("HM_TEMPLATES_DIR", "./templates"),
        http_port=int(env.get("HM_HTTP_PORT", "9999")),
        http_host=env.get("HM_HTTP_HOST", "0.0.0.0"),
        log_level=env.get("HM_LOG_LEVEL", "info").lower(),
        redis_type=env.get("HM_REDIS_TYPE", "memory").lower(),
        redis_url=env.get("HM_REDIS_URL", "redis://redis:6379"),
        admin_http_enabled=_env_bool(env.get("HM_ADMIN_HTTP_ENABLED"), True),
        admin_http_port=int(env.get("HM_ADMIN_HTTP_PORT", "9998")),
        admin_http_host=env.get("HM_ADMIN_HTTP_HOST", "0.0.0.0"),
        templates_dir_hot_reload=_env_bool(env.get("HM_TEMPLATES_DIR_HOT_RELOAD"), True),
        cors_enabled=_env_bool(env.get("HM_CORS_ENABLED"), False),
        kafka_enabled=_env_bool(env.get("HM_KAFKA_ENABLED"), False),
        kafka_client_id=env.get("HM_KAFKA_CLIENT_ID", "hmock"),
        kafka_seed_brokers=env.get("HM_KAFKA_SEED_BROKERS", "kafka:9092"),
        kafka_sasl_username=env.get("HM_KAFKA_SASL_USERNAME", ""),
        kafka_sasl_password=env.get("HM_KAFKA_SASL_PASSWORD", ""),
        kafka_tls_enabled=_env_bool(env.get("HM_KAFKA_TLS_ENABLED"), False),
        kafka_producer_seed_brokers=env.get("HM_KAFKA_PRODUCER_SEED_BROKERS", ""),
        kafka_consumer_seed_brokers=env.get("HM_KAFKA_CONSUMER_SEED_BROKERS", ""),
        kafka_sasl_producer_username=env.get("HM_KAFKA_SASL_PRODUCER_USERNAME", ""),
        kafka_sasl_producer_password=env.get("HM_KAFKA_SASL_PRODUCER_PASSWORD", ""),
        kafka_sasl_consumer_username=env.get("HM_KAFKA_SASL_CONSUMER_USERNAME", ""),
        kafka_sasl_consumer_password=env.get("HM_KAFKA_SASL_CONSUMER_PASSWORD", ""),
        kafka_tls_producer_enabled=_env_optional_bool(env.get("HM_KAFKA_TLS_PRODUCER_ENABLED")),
        kafka_tls_consumer_enabled=_env_optional_bool(env.get("HM_KAFKA_TLS_CONSUMER_ENABLED")),
        amqp_enabled=_env_bool(env.get("HM_AMQP_ENABLED"), False),
        amqp_url=env.get("HM_AMQP_URL", "amqp://guest:guest@rabbitmq:5672"),
    )


def _split_seed_brokers(value: str) -> tuple[str, ...]:
    brokers = tuple(item.strip() for item in value.split(",") if item.strip())
    return brokers or ("kafka:9092",)


def _resolve_kafka_config(
    config: Config,
    seed_brokers: str,
    username: str,
    password: str,
    tls_enabled: bool | None,
) -> KafkaClientConfig:
    resolved_username = username if username != "" else config.kafka_sasl_username
    resolved_password = password if password != "" else config.kafka_sasl_password
    return KafkaClientConfig(
        client_id=config.kafka_client_id,
        seed_brokers=_split_seed_brokers(seed_brokers if seed_brokers else config.kafka_seed_brokers),
        sasl_username=resolved_username,
        sasl_password=resolved_password,
        sasl_enabled=bool(resolved_username and resolved_password),
        tls_enabled=config.kafka_tls_enabled if tls_enabled is None else tls_enabled,
    )


def resolve_kafka_producer_config(config: Config) -> KafkaClientConfig:
    return _resolve_kafka_config(
        config,
        config.kafka_producer_seed_brokers,
        config.kafka_sasl_producer_username,
        config.kafka_sasl_producer_password,
        config.kafka_tls_producer_enabled,
    )


def resolve_kafka_consumer_config(config: Config) -> KafkaClientConfig:
    return _resolve_kafka_config(
        config,
        config.kafka_consumer_seed_brokers,
        config.kafka_sasl_consumer_username,
        config.kafka_sasl_consumer_password,
        config.kafka_tls_consumer_enabled,
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

    def do(self, command: str) -> str:
        parts = _parse_redis_command(command)
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

    def do(self, command: str) -> str:
        parts = _parse_redis_command(command)
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

INTERNAL_REDIS_PREFIX = "__hmock_internal:"
BASE_TEMPLATES_KEY = INTERNAL_REDIS_PREFIX + "templates"
TEMPLATE_SET_KEY_PREFIX = INTERNAL_REDIS_PREFIX + "template_sets:"


def build_redis_store(config: Config) -> RedisStore:
    if config.redis_type == "memory":
        return MemoryRedisStore()
    if config.redis_type == "redis":
        return ExternalRedisStore(config.redis_url)
    raise ValidationError("HM_REDIS_TYPE must be memory or redis")


def _is_internal_redis_target(value: str) -> bool:
    text = str(value)
    return (
        text.startswith(INTERNAL_REDIS_PREFIX)
        or fnmatch(BASE_TEMPLATES_KEY, text)
        or fnmatch(TEMPLATE_SET_KEY_PREFIX + "example", text)
    )


def _redis_key_args(parts: list[str]) -> list[str]:
    name = parts[0]
    args = parts[1:]
    if name in {
        "GET",
        "SET",
        "RPUSH",
        "LPUSH",
        "LRANGE",
        "LPOP",
        "RPOP",
        "HSET",
        "HGET",
        "HGETALL",
        "HDEL",
        "KEYS",
    }:
        return args[:1]
    if name in {"DEL", "EXISTS"}:
        return args
    return []


def protected_redis_do(redis_store: RedisStore, command: str) -> str:
    parts = _parse_redis_command(command)
    for key in _redis_key_args(parts):
        if _is_internal_redis_target(key):
            raise RedisError("redisDo cannot access internal hmock keyspace")
    return redis_store.do(command)


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
    method: str
    path: str
    condition: str
    actions: list[dict[str, Any]]
    pattern: PathPattern | None
    values: dict[str, Any]
    templates: dict[str, str]
    kafka_topic: str | None = None
    amqp_exchange: str | None = None
    amqp_routing_key: str | None = None
    amqp_queue: str | None = None


@dataclasses.dataclass
class LoadedMocks:
    definitions: list[dict[str, Any]]
    behaviors: list[Behavior]


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)", str(value))
    if not match:
        raise ValidationError(f"unsupported duration: {value}")
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
    return amount * factors[unit]


def _resolve_template_file_path(templates_dir: str | Path, relative_path: str, field_name: str) -> Path:
    root = Path(templates_dir).resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {relative_path}")
    return path


def _resolve_body_file(templates_dir: str | Path, body_from_file: str, field_name: str = "reply_http.body_from_file") -> str:
    path = _resolve_template_file_path(templates_dir, body_from_file, field_name)
    return path.read_text()


def _resolve_binary_body_file(templates_dir: str | Path, body_from_file: str, field_name: str) -> bytes:
    path = _resolve_template_file_path(templates_dir, body_from_file, field_name)
    return path.read_bytes()


def _templates_dir_fingerprint(templates_dir: str | Path) -> tuple[tuple[str, str], ...]:
    root = Path(templates_dir)
    if not root.exists():
        return ()
    resolved = root.resolve()
    fingerprints: list[tuple[str, str]] = []
    for path in sorted(p for p in resolved.rglob("*") if p.is_file()):
        try:
            relative = path.relative_to(resolved).as_posix()
            fingerprints.append((relative, hashlib.sha256(path.read_bytes()).hexdigest()))
        except OSError:
            continue
    return tuple(fingerprints)


def _validate_headers_mapping(headers: Any, field_name: str) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a mapping")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")


def _payload_source(payload: dict[str, Any], key: str, action_name: str) -> tuple[str | None, str | None]:
    inline = payload.get("payload")
    from_file = payload.get("payload_from_file")
    if inline is not None and not isinstance(inline, str):
        raise ValidationError(f"behavior {key} {action_name}.payload must be a string")
    if from_file is not None and (not isinstance(from_file, str) or not from_file):
        raise ValidationError(f"behavior {key} {action_name}.payload_from_file must be a non-empty string")
    if (inline is None or inline == "") and not from_file:
        raise ValidationError(f"behavior {key} {action_name} requires payload or payload_from_file")
    return inline, from_file


def _validate_publish_payload(
    payload: Any,
    key: str,
    action_name: str,
    templates_dir: str | Path | None,
) -> None:
    if not isinstance(payload, dict):
        raise ValidationError(f"behavior {key} action {action_name} payload must be a mapping")
    if action_name == "publish_kafka":
        if not isinstance(payload.get("topic"), str) or not payload.get("topic"):
            raise ValidationError(f"behavior {key} publish_kafka.topic is required")
    else:
        if not isinstance(payload.get("exchange"), str):
            raise ValidationError(f"behavior {key} publish_amqp.exchange is required")
        if not isinstance(payload.get("routing_key"), str):
            raise ValidationError(f"behavior {key} publish_amqp.routing_key is required")
    _, from_file = _payload_source(payload, key, action_name)
    if from_file is not None and templates_dir is not None:
        payload[f"{action_name}_payload_from_file_content"] = _resolve_body_file(
            templates_dir,
            from_file,
            f"{action_name}.payload_from_file",
        )


def _validate_kafka_expect(expect: dict[str, Any], key: str) -> str | None:
    if "kafka" not in expect:
        return None
    kafka = expect.get("kafka")
    if not isinstance(kafka, dict):
        raise ValidationError(f"behavior {key} expect.kafka must be a mapping")
    topic = kafka.get("topic")
    if not isinstance(topic, str) or not topic:
        raise ValidationError(f"behavior {key} expect.kafka.topic is required")
    return topic


def _validate_amqp_expect(expect: dict[str, Any], key: str) -> tuple[str | None, str | None, str | None]:
    if "amqp" not in expect:
        return None, None, None
    amqp = expect.get("amqp")
    if not isinstance(amqp, dict):
        raise ValidationError(f"behavior {key} expect.amqp must be a mapping")
    exchange = amqp.get("exchange")
    routing_key = amqp.get("routing_key")
    queue = amqp.get("queue", "")
    if not isinstance(exchange, str):
        raise ValidationError(f"behavior {key} expect.amqp.exchange is required")
    if not isinstance(routing_key, str):
        raise ValidationError(f"behavior {key} expect.amqp.routing_key is required")
    if not isinstance(queue, str):
        raise ValidationError(f"behavior {key} expect.amqp.queue must be a string")
    return exchange, routing_key, queue or routing_key


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
            if "body" in payload and payload["body"] is not None and not isinstance(payload["body"], str):
                raise ValidationError(f"behavior {key} reply_http.body must be a string")
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
                    payload["body_from_binary_file_content"] = _resolve_binary_body_file(
                        templates_dir,
                        body_from_binary_file,
                        "reply_http.body_from_binary_file",
                    )
            binary_file_name = payload.get("binary_file_name")
            if binary_file_name is not None and not isinstance(binary_file_name, str):
                raise ValidationError(f"behavior {key} reply_http.binary_file_name must be a string")
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
                    payload["send_http_body_from_binary_file_content"] = _resolve_binary_body_file(
                        templates_dir,
                        body_from_binary_file,
                        "send_http.body_from_binary_file",
                    )
            binary_file_name = payload.get("binary_file_name")
            if binary_file_name is not None and not isinstance(binary_file_name, str):
                raise ValidationError(f"behavior {key} send_http.binary_file_name must be a string")
        elif name in {"publish_kafka", "publish_amqp"}:
            _validate_publish_payload(payload, key, name, templates_dir)
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
    http = expect.get("http", {})
    if http is not None and not isinstance(http, dict):
        raise ValidationError(f"behavior {key} expect.http must be a mapping")
    _validate_kafka_expect(expect, key)
    _validate_amqp_expect(expect, key)
    _validate_actions(raw.get("actions", []), key, templates_dir)


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
    http = expect.get("http")
    if http is None:
        http = {}
    if not isinstance(http, dict):
        raise ValidationError(f"behavior {key} expect.http must be a mapping")
    kafka_topic = _validate_kafka_expect(expect, key)
    amqp_exchange, amqp_routing_key, amqp_queue = _validate_amqp_expect(expect, key)
    has_http = bool(http)
    method = http.get("method") if has_http else ""
    path = http.get("path") if has_http else ""
    if has_http:
        if not isinstance(method, str) or not method:
            raise ValidationError(f"behavior {key} expect.http.method is required")
        if not isinstance(path, str) or not path:
            raise ValidationError(f"behavior {key} expect.http.path is required")
    elif kafka_topic is None and amqp_exchange is None:
        raise ValidationError(f"behavior {key} expect.http.method is required")
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
        method=method.upper(),
        path=path,
        condition=condition,
        actions=sorted_actions,
        pattern=PathPattern.compile(path) if has_http else None,
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


def load_mock_definitions(templates_dir: str | Path) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for path in discover_yaml_files(templates_dir):
        for raw in load_mock_file(path):
            definitions.append(raw)
    return definitions


def load_mock_collection(
    templates_dir: str | Path,
    raw_definitions: list[Any],
    logger: JsonLogger | None = None,
) -> LoadedMocks:
    logger = logger or JsonLogger("error")
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in raw_definitions:
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
    definitions = [copy.deepcopy(raw_by_key[key]) for key in order]
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
    return LoadedMocks(definitions, behaviors)


def load_behaviors(templates_dir: str | Path, logger: JsonLogger | None = None) -> list[Behavior]:
    return load_mock_collection(templates_dir, load_mock_definitions(templates_dir), logger).behaviors


def _json_array(value: str, label: str) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{label} contains invalid JSON") from exc
    if not isinstance(parsed, list):
        raise ValidationError(f"{label} must be a JSON array")
    return [copy.deepcopy(item) for item in parsed]


def _compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _set_command(key: str, value: str) -> str:
    return f"SET {key} {shlex.quote(value)}"


def _merge_definition_lists(
    existing: list[dict[str, Any]],
    submitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in [*existing, *submitted]:
        key, _ = _definition_kind(raw)
        if key in by_key:
            order.remove(key)
        by_key[key] = copy.deepcopy(raw)
        order.append(key)
    return [by_key[key] for key in order]


class AdminMockStore:
    def __init__(self, redis_store: RedisStore) -> None:
        self.redis_store = redis_store

    def load_base_templates(self) -> list[dict[str, Any]]:
        return _json_array(self.redis_store.do(f"GET {BASE_TEMPLATES_KEY}"), "base API templates")

    def save_base_templates(self, definitions: list[dict[str, Any]]) -> None:
        self.redis_store.do(_set_command(BASE_TEMPLATES_KEY, _compact_json(definitions)))

    def clear_base_templates(self) -> None:
        self.redis_store.do(f"DEL {BASE_TEMPLATES_KEY}")

    def load_template_sets(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        keys = self.redis_store.do(f"KEYS {TEMPLATE_SET_KEY_PREFIX}*")
        for key in [item for item in keys.split(";;") if item]:
            encoded = key[len(TEMPLATE_SET_KEY_PREFIX) :]
            result[unquote_plus(encoded)] = _json_array(
                self.redis_store.do(f"GET {key}"),
                f"template set {encoded}",
            )
        return result

    def save_template_set(self, set_key: str, definitions: list[dict[str, Any]]) -> None:
        self.redis_store.do(_set_command(self._template_set_key(set_key), _compact_json(definitions)))

    def delete_template_set(self, set_key: str) -> None:
        self.redis_store.do(f"DEL {self._template_set_key(set_key)}")

    def _template_set_key(self, set_key: str) -> str:
        return TEMPLATE_SET_KEY_PREFIX + quote_plus(set_key, safe="")


class KafkaAdapter:
    def __init__(
        self,
        producer_config: KafkaClientConfig,
        consumer_config: KafkaClientConfig,
        logger: JsonLogger,
    ) -> None:
        self.producer_config = producer_config
        self.consumer_config = consumer_config
        self.logger = logger
        self.topics: tuple[str, ...] = ()
        self.callback: Callable[[str, str], None] | None = None
        self.closed = False

    def subscribe(self, topics: Iterable[str], callback: Callable[[str, str], None]) -> None:
        self.topics = tuple(sorted(set(topics)))
        self.callback = callback

    def publish(self, topic: str, payload: str) -> None:
        raise RuntimeError("Kafka adapter is not configured")

    def close(self) -> None:
        self.closed = True


class AMQPAdapter:
    def __init__(self, url: str, logger: JsonLogger) -> None:
        self.url = url
        self.logger = logger
        self.bindings: tuple[AMQPBinding, ...] = ()
        self.callback: Callable[[str, str, str, str], None] | None = None
        self.closed = False

    def declare_and_consume(
        self,
        bindings: Iterable[AMQPBinding],
        callback: Callable[[str, str, str, str], None],
    ) -> None:
        self.bindings = tuple(sorted(set(bindings), key=lambda item: (item.exchange, item.routing_key, item.queue)))
        self.callback = callback

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        raise RuntimeError("AMQP adapter is not configured")

    def reconnect(self, bindings: Iterable[AMQPBinding], callback: Callable[[str, str, str, str], None]) -> None:
        self.declare_and_consume(bindings, callback)

    def close(self) -> None:
        self.closed = True


class HMockRuntime:
    def __init__(
        self,
        config: Config,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.redis_store = redis_store or build_redis_store(config)
        self.admin_store = AdminMockStore(self.redis_store)
        self.kafka_adapter = kafka_adapter if kafka_adapter is not None else self._build_kafka_adapter()
        self.amqp_adapter = amqp_adapter if amqp_adapter is not None else self._build_amqp_adapter()
        self._lock = threading.RLock()
        self._loaded = LoadedMocks([], [])
        self._filesystem_fingerprint: tuple[tuple[str, str], ...] = ()
        self.reload()

    def _build_kafka_adapter(self) -> KafkaAdapter | None:
        if not self.config.kafka_enabled:
            return None
        return KafkaAdapter(
            resolve_kafka_producer_config(self.config),
            resolve_kafka_consumer_config(self.config),
            self.logger,
        )

    def _build_amqp_adapter(self) -> AMQPAdapter | None:
        if not self.config.amqp_enabled:
            return None
        return AMQPAdapter(self.config.amqp_url, self.logger)

    def _set_loaded(self, loaded: LoadedMocks) -> None:
        with self._lock:
            self._loaded = loaded
            self._filesystem_fingerprint = _templates_dir_fingerprint(self.config.templates_dir)
        self._refresh_broker_subscriptions()

    def _kafka_topics(self) -> list[str]:
        with self._lock:
            return sorted({behavior.kafka_topic for behavior in self._loaded.behaviors if behavior.kafka_topic})

    def _amqp_bindings(self) -> list[AMQPBinding]:
        with self._lock:
            bindings = {
                AMQPBinding(behavior.amqp_exchange, behavior.amqp_routing_key, behavior.amqp_queue)
                for behavior in self._loaded.behaviors
                if behavior.amqp_exchange is not None
                and behavior.amqp_routing_key is not None
                and behavior.amqp_queue is not None
            }
        return sorted(bindings, key=lambda item: (item.exchange, item.routing_key, item.queue))

    def _refresh_broker_subscriptions(self) -> None:
        if self.kafka_adapter is not None:
            self.kafka_adapter.subscribe(self._kafka_topics(), self.handle_kafka_message)
        if self.amqp_adapter is not None:
            self.amqp_adapter.declare_and_consume(self._amqp_bindings(), self.handle_amqp_message)

    def reload(self) -> None:
        loaded = self._load_candidate(
            self.admin_store.load_base_templates(),
            self.admin_store.load_template_sets(),
        )
        self._set_loaded(loaded)

    def reload_filesystem_if_changed(self) -> None:
        if not self.config.templates_dir_hot_reload:
            return
        fingerprint = _templates_dir_fingerprint(self.config.templates_dir)
        with self._lock:
            if fingerprint == self._filesystem_fingerprint:
                return
            loaded = self._load_candidate(
                self.admin_store.load_base_templates(),
                self.admin_store.load_template_sets(),
            )
            self._loaded = loaded
            self._filesystem_fingerprint = fingerprint
        self._refresh_broker_subscriptions()

    def get_behaviors(self) -> list[Behavior]:
        self.reload_filesystem_if_changed()
        with self._lock:
            return list(self._loaded.behaviors)

    def get_definitions(self) -> list[dict[str, Any]]:
        self.reload_filesystem_if_changed()
        with self._lock:
            return copy.deepcopy(self._loaded.definitions)

    def add_base_templates(self, submitted: list[dict[str, Any]]) -> None:
        base = self.admin_store.load_base_templates()
        sets = self.admin_store.load_template_sets()
        next_base = _merge_definition_lists(base, submitted)
        loaded = self._load_candidate(next_base, sets)
        self.admin_store.save_base_templates(next_base)
        self._set_loaded(loaded)

    def clear_base_templates(self) -> None:
        sets = self.admin_store.load_template_sets()
        loaded = self._load_candidate([], sets)
        self.admin_store.clear_base_templates()
        self._set_loaded(loaded)

    def delete_base_template(self, template_key: str) -> bool:
        base = self.admin_store.load_base_templates()
        next_base = [raw for raw in base if raw.get("key") != template_key]
        if len(next_base) == len(base):
            return False
        sets = self.admin_store.load_template_sets()
        loaded = self._load_candidate(next_base, sets)
        self.admin_store.save_base_templates(next_base)
        self._set_loaded(loaded)
        return True

    def replace_template_set(self, set_key: str, submitted: list[dict[str, Any]]) -> None:
        base = self.admin_store.load_base_templates()
        sets = self.admin_store.load_template_sets()
        sets[set_key] = copy.deepcopy(submitted)
        loaded = self._load_candidate(base, sets)
        self.admin_store.save_template_set(set_key, submitted)
        self._set_loaded(loaded)

    def delete_template_set(self, set_key: str) -> None:
        base = self.admin_store.load_base_templates()
        sets = self.admin_store.load_template_sets()
        sets.pop(set_key, None)
        loaded = self._load_candidate(base, sets)
        self.admin_store.delete_template_set(set_key)
        self._set_loaded(loaded)

    def _load_candidate(
        self,
        base_templates: list[dict[str, Any]],
        template_sets: dict[str, list[dict[str, Any]]],
    ) -> LoadedMocks:
        definitions: list[Any] = []
        definitions.extend(load_mock_definitions(self.config.templates_dir))
        definitions.extend(copy.deepcopy(base_templates))
        for set_key in sorted(template_sets):
            definitions.extend(copy.deepcopy(template_sets[set_key]))
        return load_mock_collection(self.config.templates_dir, definitions, self.logger)

    def handle_kafka_message(self, topic: str, payload: str) -> None:
        for behavior in find_kafka_behaviors(self.get_behaviors(), topic, payload, self.redis_store):
            execute_behavior(
                behavior,
                BrokerMessageInfo("kafka", payload, kafka_topic=topic),
                {},
                self.redis_store,
                self.logger,
                kafka_adapter=self.kafka_adapter,
                amqp_adapter=self.amqp_adapter,
            )

    def handle_amqp_message(self, exchange: str, routing_key: str, queue: str, payload: str) -> None:
        for behavior in find_amqp_behaviors(self.get_behaviors(), exchange, routing_key, queue, payload, self.redis_store):
            execute_behavior(
                behavior,
                BrokerMessageInfo("amqp", payload, amqp_exchange=exchange, amqp_routing_key=routing_key, amqp_queue=queue),
                {},
                self.redis_store,
                self.logger,
                kafka_adapter=self.kafka_adapter,
                amqp_adapter=self.amqp_adapter,
            )

    def recover_amqp_consumption(self) -> None:
        if self.amqp_adapter is not None:
            self.amqp_adapter.reconnect(self._amqp_bindings(), self.handle_amqp_message)

    def close(self) -> None:
        if self.kafka_adapter is not None:
            self.kafka_adapter.close()
        if self.amqp_adapter is not None:
            self.amqp_adapter.close()


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
class BrokerMessageInfo:
    broker: str
    payload: str
    kafka_topic: str = ""
    amqp_exchange: str = ""
    amqp_routing_key: str = ""
    amqp_queue: str = ""


@dataclasses.dataclass
class ResponseInfo:
    status_code: int
    headers: dict[str, str]
    body: str | bytes

    def body_bytes(self) -> bytes:
        return self.body if isinstance(self.body, bytes) else self.body.encode()

    def body_text(self) -> str:
        return self.body.decode(errors="replace") if isinstance(self.body, bytes) else self.body


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Credentials": "true",
}


def apply_cors_headers(response: ResponseInfo) -> ResponseInfo:
    headers = dict(response.headers)
    existing = {key.lower() for key in headers}
    for key, value in CORS_HEADERS.items():
        if key.lower() not in existing:
            headers[key] = value
    return ResponseInfo(response.status_code, headers, response.body)


def cors_preflight_response() -> ResponseInfo:
    return apply_cors_headers(ResponseInfo(200, {"Content-Length": "0"}, ""))


def find_behavior(
    behaviors: list[Behavior],
    request: RequestInfo,
    redis_store: RedisStore | None = None,
) -> tuple[Behavior, dict[str, str]] | tuple[None, dict[str, str]]:
    for behavior in behaviors:
        if behavior.pattern is None:
            continue
        if behavior.method != request.method.upper():
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
            (lambda command: protected_redis_do(redis_store, command)) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                return behavior, params
        except TemplateError:
            continue
    return None, {}


def build_broker_template_context(
    message: BrokerMessageInfo,
    redis_do: Callable[[str], str] | None = None,
    values: dict[str, Any] | None = None,
    templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    context = build_template_context({}, "", "", "", {}, redis_do, values, templates)
    if message.broker == "kafka":
        context["KafkaTopic"] = message.kafka_topic
        context["KafkaPayload"] = message.payload
    if message.broker == "amqp":
        context["AMQPExchange"] = message.amqp_exchange
        context["AMQPRoutingKey"] = message.amqp_routing_key
        context["AMQPQueue"] = message.amqp_queue
        context["AMQPPayload"] = message.payload
    return context


def _broker_condition_matches(
    behavior: Behavior,
    context: dict[str, Any],
) -> bool:
    if not behavior.condition:
        return True
    try:
        return render_template(behavior.condition, context) == "true"
    except TemplateError:
        return False


def find_kafka_behaviors(
    behaviors: list[Behavior],
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
) -> list[Behavior]:
    matched: list[Behavior] = []
    for behavior in behaviors:
        if behavior.kafka_topic != topic:
            continue
        context = build_broker_template_context(
            BrokerMessageInfo("kafka", payload, kafka_topic=topic),
            (lambda command: protected_redis_do(redis_store, command)) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        if _broker_condition_matches(behavior, context):
            matched.append(behavior)
    return matched


def find_amqp_behaviors(
    behaviors: list[Behavior],
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_store: RedisStore | None = None,
) -> list[Behavior]:
    matched: list[Behavior] = []
    for behavior in behaviors:
        if (
            behavior.amqp_exchange != exchange
            or behavior.amqp_routing_key != routing_key
            or behavior.amqp_queue != queue
        ):
            continue
        context = build_broker_template_context(
            BrokerMessageInfo("amqp", payload, amqp_exchange=exchange, amqp_routing_key=routing_key, amqp_queue=queue),
            (lambda command: protected_redis_do(redis_store, command)) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        if _broker_condition_matches(behavior, context):
            matched.append(behavior)
    return matched


def _multipart_file_body(field_name: str, filename: str, content_type: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----hmock-" + uuid.uuid4().hex
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode()
    footer = f"\r\n--{boundary}--\r\n".encode()
    return header + content + footer, boundary


def _header_value(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


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
    elif payload.get("send_http_body_from_binary_file_content") is not None:
        binary = payload["send_http_body_from_binary_file_content"]
        if method == "POST":
            filename = payload.get("binary_file_name") or posixpath.basename(str(payload.get("body_from_binary_file", "file")))
            content_type = _header_value(headers, "Content-Type") or "application/octet-stream"
            data, boundary = _multipart_file_body("file", str(filename), content_type, binary)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            data = binary
    else:
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


def _render_publish_payload(payload: dict[str, Any], context: dict[str, Any], content_key: str) -> str:
    body_source = payload.get("payload")
    if body_source is None or body_source == "":
        body_source = payload.get(content_key, "")
    return render_template(str(body_source), context)


def _publish_kafka(
    payload: dict[str, Any],
    context: dict[str, Any],
    adapter: KafkaAdapter | None,
    logger: JsonLogger | None = None,
) -> None:
    topic = render_template(str(payload["topic"]), context)
    rendered_payload = _render_publish_payload(payload, context, "publish_kafka_payload_from_file_content")
    try:
        if adapter is None:
            raise RuntimeError("Kafka adapter is not configured")
        adapter.publish(topic, rendered_payload)
    except Exception as exc:
        if logger is not None:
            logger.warn("publish_kafka failed", topic=topic, error=str(exc))


def _publish_amqp(
    payload: dict[str, Any],
    context: dict[str, Any],
    adapter: AMQPAdapter | None,
    logger: JsonLogger | None = None,
) -> None:
    exchange = render_template(str(payload["exchange"]), context)
    routing_key = render_template(str(payload["routing_key"]), context)
    rendered_payload = _render_publish_payload(payload, context, "publish_amqp_payload_from_file_content")
    try:
        if adapter is None:
            raise RuntimeError("AMQP adapter is not configured")
        adapter.publish(exchange, routing_key, rendered_payload)
    except Exception as exc:
        if logger is not None:
            logger.warn("publish_amqp failed", exchange=exchange, routing_key=routing_key, error=str(exc))


def execute_behavior(
    behavior: Behavior,
    request: RequestInfo | BrokerMessageInfo,
    params: dict[str, str],
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    if isinstance(request, BrokerMessageInfo):
        context = build_broker_template_context(
            request,
            lambda command: protected_redis_do(redis_store, command),
            behavior.values,
            behavior.templates,
        )
    else:
        context = build_template_context(
            request.headers,
            request.body,
            request.path,
            request.query,
            params,
            lambda command: protected_redis_do(redis_store, command),
            behavior.values,
            behavior.templates,
        )
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
            _publish_kafka(payload, context, kafka_adapter, logger)
        elif name == "publish_amqp":
            _publish_amqp(payload, context, amqp_adapter, logger)
        elif name == "reply_http":
            body_source = payload.get("body")
            binary_body = None
            if body_source is None or body_source == "":
                binary_body = payload.get("body_from_binary_file_content")
            if binary_body is not None:
                body = binary_body
            else:
                if body_source is None or body_source == "":
                    body_source = payload.get("body_from_file_content", "")
                body = render_template(str(body_source), context)
            headers = {
                str(key): render_template(str(value), context)
                for key, value in (payload.get("headers") or {}).items()
            }
            if binary_body is not None and payload.get("binary_file_name") is not None:
                headers["Content-Disposition"] = f'inline; filename="{payload["binary_file_name"]}"'
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body if isinstance(body, bytes) else body.encode()))
            response = ResponseInfo(int(payload["status_code"]), headers, body)
    return response or ResponseInfo(204, {"Content-Length": "0"}, "")


def not_found_response() -> ResponseInfo:
    body = "not found"
    return ResponseInfo(
        404,
        {"Content-Type": "text/plain", "Content-Length": str(len(body.encode()))},
        body,
    )


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

    def do_HEAD(self) -> None:
        self._handle(send_body=False)

    def do_OPTIONS(self) -> None:
        self._handle()

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
        behavior, params = find_behavior(self.server.get_behaviors(), request, self.server.redis_store)
        try:
            if behavior:
                response = execute_behavior(behavior, request, params, self.server.redis_store, self.server.hm_logger)
            elif self.server.cors_enabled and request.method.upper() == "OPTIONS":
                response = cors_preflight_response()
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
            response = apply_cors_headers(response)
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
                "body": response.body_text(),
            },
        )


class HMockHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        behaviors: list[Behavior] | None,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        runtime: HMockRuntime | None = None,
    ) -> None:
        super().__init__(address, MockHTTPRequestHandler)
        self.behaviors = behaviors or []
        self.runtime = runtime
        self.hm_logger = logger
        self.redis_store = runtime.redis_store if runtime is not None else (redis_store or MemoryRedisStore())
        self.cors_enabled = runtime.config.cors_enabled if runtime is not None else False

    def get_behaviors(self) -> list[Behavior]:
        if self.runtime is not None:
            return self.runtime.get_behaviors()
        return list(self.behaviors)

    def server_close(self) -> None:
        if self.runtime is not None:
            self.runtime.close()
        super().server_close()


class AdminHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "HMockAdminHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        split = urlsplit(self.path)
        if split.path == "/api/v1/health":
            self._send_json(200, {"status": "OK"})
            return
        if split.path == "/api/v1/templates":
            self._send_json(200, self.server.runtime.get_definitions())
            return
        self._send_text(404, "not found")

    def do_POST(self) -> None:
        split = urlsplit(self.path)
        try:
            submitted = self._read_definition_array()
            if split.path == "/api/v1/templates":
                self.server.runtime.add_base_templates(submitted)
                self._send_json(200, submitted)
                return
            set_key = self._extract_key(split.path, "/api/v1/template_sets/")
            if set_key is not None:
                self.server.runtime.replace_template_set(set_key, submitted)
                self._send_json(200, submitted)
                return
        except ValidationError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self.server.hm_logger.error("admin request failed", error=str(exc), http_path=self.path)
            self._send_json(500, {"error": str(exc)})
            return
        self._send_text(404, "not found")

    def do_DELETE(self) -> None:
        split = urlsplit(self.path)
        try:
            if split.path == "/api/v1/templates":
                self.server.runtime.clear_base_templates()
                self._send_no_content()
                return
            template_key = self._extract_key(split.path, "/api/v1/templates/")
            if template_key is not None:
                if not self.server.runtime.delete_base_template(template_key):
                    self._send_text(404, "not found")
                    return
                self._send_no_content()
                return
            set_key = self._extract_key(split.path, "/api/v1/template_sets/")
            if set_key is not None:
                self.server.runtime.delete_template_set(set_key)
                self._send_no_content()
                return
        except ValidationError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception as exc:
            self.server.hm_logger.error("admin request failed", error=str(exc), http_path=self.path)
            self._send_json(500, {"error": str(exc)})
            return
        self._send_text(404, "not found")

    def _extract_key(self, path: str, prefix: str) -> str | None:
        if not path.startswith(prefix):
            return None
        rest = path[len(prefix) :]
        if not rest or "/" in rest:
            return None
        return unquote_plus(rest)

    def _read_definition_array(self) -> list[dict[str, Any]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type in {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"}:
            try:
                parsed = parse_yaml_subset(body)
            except ValidationError as exc:
                raise ValidationError("request body must be a YAML array of mock definitions") from exc
            if not isinstance(parsed, list):
                raise ValidationError("request body must be a YAML array of mock definitions")
            return [copy.deepcopy(item) for item in parsed]
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValidationError("request body must be a JSON array of mock definitions") from exc
        if not isinstance(parsed, list):
            raise ValidationError("request body must be a JSON array of mock definitions")
        return [copy.deepcopy(item) for item in parsed]

    def _send_json(self, status_code: int, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":"))
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def _send_text(self, status_code: int, body: str) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


class HMockAdminHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], runtime: HMockRuntime, logger: JsonLogger) -> None:
        super().__init__(address, AdminHTTPRequestHandler)
        self.runtime = runtime
        self.hm_logger = logger


def build_server(config: Config | None = None, logger: JsonLogger | None = None) -> HMockHTTPServer:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    runtime = HMockRuntime(config, logger)
    return HMockHTTPServer((config.http_host, config.http_port), None, logger, runtime=runtime)


def build_servers(
    config: Config | None = None,
    logger: JsonLogger | None = None,
) -> tuple[HMockHTTPServer, HMockAdminHTTPServer | None]:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    runtime = HMockRuntime(config, logger)
    mock_server = HMockHTTPServer((config.http_host, config.http_port), None, logger, runtime=runtime)
    admin_server = (
        HMockAdminHTTPServer((config.admin_http_host, config.admin_http_port), runtime, logger)
        if config.admin_http_enabled
        else None
    )
    return mock_server, admin_server


def main() -> None:
    config = load_config()
    logger = JsonLogger(config.log_level)
    server, admin_server = build_servers(config, logger)
    admin_thread: threading.Thread | None = None
    if admin_server is not None:
        admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        admin_thread.start()
        logger.info("hmock admin server started", host=config.admin_http_host, port=config.admin_http_port)
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
        server.server_close()


if __name__ == "__main__":
    main()
