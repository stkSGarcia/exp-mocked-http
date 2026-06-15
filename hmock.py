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
from typing import Any, Protocol
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
class KafkaEndpointConfig:
    seed_brokers: tuple[str, ...] = ("kafka:9092",)
    sasl_username: str = ""
    sasl_password: str = ""
    tls_enabled: bool = False

    @property
    def sasl_enabled(self) -> bool:
        return bool(self.sasl_username and self.sasl_password)


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
    kafka_seed_brokers: tuple[str, ...] = ("kafka:9092",)
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""
    kafka_tls_enabled: bool = False
    kafka_producer: KafkaEndpointConfig = dataclasses.field(default_factory=KafkaEndpointConfig)
    kafka_consumer: KafkaEndpointConfig = dataclasses.field(default_factory=KafkaEndpointConfig)
    amqp_enabled: bool = False
    amqp_url: str = "amqp://guest:guest@rabbitmq:5672"


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def parse_kafka_seed_brokers(value: str | None, default: str = "kafka:9092") -> tuple[str, ...]:
    raw = default if value is None else value
    brokers = tuple(part.strip() for part in raw.split(",") if part.strip())
    return brokers or tuple(part.strip() for part in default.split(",") if part.strip())


def _env_value(env: dict[str, str], name: str, default: str) -> str:
    value = env.get(name)
    return default if value is None else value


def resolve_kafka_endpoint_config(
    env: dict[str, str],
    *,
    side: str,
    shared_brokers: tuple[str, ...],
    shared_username: str,
    shared_password: str,
    shared_tls_enabled: bool,
) -> KafkaEndpointConfig:
    side_upper = side.upper()
    brokers_key = f"HM_KAFKA_{side_upper}_SEED_BROKERS"
    username_key = f"HM_KAFKA_SASL_{side_upper}_USERNAME"
    password_key = f"HM_KAFKA_SASL_{side_upper}_PASSWORD"
    tls_key = f"HM_KAFKA_TLS_{side_upper}_ENABLED"
    return KafkaEndpointConfig(
        seed_brokers=parse_kafka_seed_brokers(env.get(brokers_key), ",".join(shared_brokers)),
        sasl_username=_env_value(env, username_key, shared_username),
        sasl_password=_env_value(env, password_key, shared_password),
        tls_enabled=_env_bool(env.get(tls_key), shared_tls_enabled),
    )


def load_config(env: dict[str, str] | None = None) -> Config:
    env = env if env is not None else os.environ
    kafka_seed_brokers = parse_kafka_seed_brokers(env.get("HM_KAFKA_SEED_BROKERS"))
    kafka_sasl_username = env.get("HM_KAFKA_SASL_USERNAME", "")
    kafka_sasl_password = env.get("HM_KAFKA_SASL_PASSWORD", "")
    kafka_tls_enabled = _env_bool(env.get("HM_KAFKA_TLS_ENABLED"), False)
    kafka_producer = resolve_kafka_endpoint_config(
        env,
        side="producer",
        shared_brokers=kafka_seed_brokers,
        shared_username=kafka_sasl_username,
        shared_password=kafka_sasl_password,
        shared_tls_enabled=kafka_tls_enabled,
    )
    kafka_consumer = resolve_kafka_endpoint_config(
        env,
        side="consumer",
        shared_brokers=kafka_seed_brokers,
        shared_username=kafka_sasl_username,
        shared_password=kafka_sasl_password,
        shared_tls_enabled=kafka_tls_enabled,
    )
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
        kafka_seed_brokers=kafka_seed_brokers,
        kafka_sasl_username=kafka_sasl_username,
        kafka_sasl_password=kafka_sasl_password,
        kafka_tls_enabled=kafka_tls_enabled,
        kafka_producer=kafka_producer,
        kafka_consumer=kafka_consumer,
        amqp_enabled=_env_bool(env.get("HM_AMQP_ENABLED"), False),
        amqp_url=env.get("HM_AMQP_URL", "amqp://guest:guest@rabbitmq:5672"),
    )


@dataclasses.dataclass(frozen=True)
class KafkaMessage:
    topic: str
    payload: str


@dataclasses.dataclass(frozen=True)
class AMQPMessage:
    exchange: str
    routing_key: str
    queue: str
    payload: str


@dataclasses.dataclass(frozen=True, order=True)
class AMQPBinding:
    exchange: str
    routing_key: str
    queue: str


class KafkaAdapter(Protocol):
    def publish(self, topic: str, payload: str) -> None:
        ...

    def subscribe(self, topics: Iterable[str]) -> None:
        ...

    def consume(self, callback: Callable[[KafkaMessage], None], stop_event: threading.Event) -> None:
        ...

    def close(self) -> None:
        ...


class AMQPAdapter(Protocol):
    def setup_bindings(self, bindings: Iterable[AMQPBinding]) -> None:
        ...

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        ...

    def consume(self, bindings: Iterable[AMQPBinding], callback: Callable[[AMQPMessage], None], stop_event: threading.Event) -> None:
        ...

    def close(self) -> None:
        ...


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

INTERNAL_KEY_PREFIX = "__hmock_internal:"
INTERNAL_TEMPLATES_KEY = INTERNAL_KEY_PREFIX + "templates"
INTERNAL_TEMPLATE_SET_PREFIX = INTERNAL_KEY_PREFIX + "template_sets:"


def build_redis_store(config: Config) -> RedisStore:
    if config.redis_type == "memory":
        return MemoryRedisStore()
    if config.redis_type == "redis":
        return ExternalRedisStore(config.redis_url)
    raise ValidationError("HM_REDIS_TYPE must be memory or redis")


def _redis_key_args(parts: list[str]) -> list[str]:
    name = parts[0]
    args = parts[1:]
    if name in {"GET", "SET", "RPUSH", "LPUSH", "LRANGE", "LPOP", "RPOP", "HSET", "HGET", "HGETALL", "HDEL"}:
        return args[:1]
    if name in {"DEL", "EXISTS"}:
        return args
    if name == "KEYS":
        pattern = args[0]
        if (
            pattern.startswith(INTERNAL_KEY_PREFIX)
            or fnmatch(INTERNAL_TEMPLATES_KEY, pattern)
            or fnmatch(INTERNAL_TEMPLATE_SET_PREFIX + "example", pattern)
        ):
            return [INTERNAL_KEY_PREFIX]
        return []
    return []


def redis_command_targets_internal(command: str) -> bool:
    parts = _parse_redis_command(command)
    return any(key.startswith(INTERNAL_KEY_PREFIX) for key in _redis_key_args(parts))


def guarded_redis_do(store: RedisStore, command: str) -> str:
    if redis_command_targets_internal(command):
        raise RedisError("Redis command targets reserved internal keyspace")
    return store.do(command)


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


FilesystemSignature = tuple[tuple[str, int, int], ...]


def filesystem_template_signature(root: str | Path) -> FilesystemSignature:
    base = Path(root).resolve()
    signature: list[tuple[str, int, int]] = []
    for path in discover_yaml_files(base):
        try:
            stat = path.stat()
            relpath = str(path.resolve().relative_to(base))
        except (FileNotFoundError, ValueError):
            continue
        signature.append((relpath, stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


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
    pattern: PathPattern
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


def _resolve_safe_template_file(templates_dir: str | Path, file_path: str, field_name: str) -> Path:
    root = Path(templates_dir).resolve()
    path = (root / file_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {file_path}")
    return path


def _resolve_body_file(templates_dir: str | Path, body_from_file: str, field_name: str = "reply_http.body_from_file") -> str:
    path = _resolve_safe_template_file(templates_dir, body_from_file, field_name)
    return path.read_text()


def _resolve_binary_body_file(templates_dir: str | Path, body_from_file: str, field_name: str) -> bytes:
    path = _resolve_safe_template_file(templates_dir, body_from_file, field_name)
    return path.read_bytes()


def _validate_headers_mapping(headers: Any, field_name: str) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a mapping")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")


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
        elif name == "publish_kafka":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            if not isinstance(payload.get("topic"), str) or not payload.get("topic"):
                raise ValidationError(f"behavior {key} publish_kafka.topic is required")
            if "payload" not in payload and "payload_from_file" not in payload:
                raise ValidationError(f"behavior {key} publish_kafka payload is required")
            if "payload" in payload and payload["payload"] is not None and not isinstance(payload["payload"], str):
                raise ValidationError(f"behavior {key} publish_kafka.payload must be a string")
            payload_from_file = payload.get("payload_from_file")
            if payload_from_file is not None:
                if not isinstance(payload_from_file, str) or not payload_from_file:
                    raise ValidationError(f"behavior {key} publish_kafka.payload_from_file must be a non-empty string")
                if templates_dir is not None:
                    payload["publish_kafka_payload_from_file_content"] = _resolve_body_file(
                        templates_dir,
                        payload_from_file,
                        "publish_kafka.payload_from_file",
                    )
        elif name == "publish_amqp":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            if not isinstance(payload.get("exchange"), str) or not payload.get("exchange"):
                raise ValidationError(f"behavior {key} publish_amqp.exchange is required")
            if not isinstance(payload.get("routing_key"), str) or not payload.get("routing_key"):
                raise ValidationError(f"behavior {key} publish_amqp.routing_key is required")
            if "payload" not in payload and "payload_from_file" not in payload:
                raise ValidationError(f"behavior {key} publish_amqp payload is required")
            if "payload" in payload and payload["payload"] is not None and not isinstance(payload["payload"], str):
                raise ValidationError(f"behavior {key} publish_amqp.payload must be a string")
            payload_from_file = payload.get("payload_from_file")
            if payload_from_file is not None:
                if not isinstance(payload_from_file, str) or not payload_from_file:
                    raise ValidationError(f"behavior {key} publish_amqp.payload_from_file must be a non-empty string")
                if templates_dir is not None:
                    payload["publish_amqp_payload_from_file_content"] = _resolve_body_file(
                        templates_dir,
                        payload_from_file,
                        "publish_amqp.payload_from_file",
                    )
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
    kafka = expect.get("kafka")
    amqp = expect.get("amqp")
    method = ""
    path = ""
    pattern = PathPattern.compile("/")
    if http is not None:
        if not isinstance(http, dict):
            raise ValidationError(f"behavior {key} expect.http must be a mapping")
        method_value = http.get("method")
        path_value = http.get("path")
        if not isinstance(method_value, str) or not method_value:
            raise ValidationError(f"behavior {key} expect.http.method is required")
        if not isinstance(path_value, str) or not path_value:
            raise ValidationError(f"behavior {key} expect.http.path is required")
        method = method_value.upper()
        path = path_value
        pattern = PathPattern.compile(path)
    kafka_topic = None
    if kafka is not None:
        if not isinstance(kafka, dict):
            raise ValidationError(f"behavior {key} expect.kafka must be a mapping")
        topic = kafka.get("topic")
        if not isinstance(topic, str) or not topic:
            raise ValidationError(f"behavior {key} expect.kafka.topic is required")
        kafka_topic = topic
    amqp_exchange = None
    amqp_routing_key = None
    amqp_queue = None
    if amqp is not None:
        if not isinstance(amqp, dict):
            raise ValidationError(f"behavior {key} expect.amqp must be a mapping")
        exchange = amqp.get("exchange")
        routing_key = amqp.get("routing_key")
        queue = amqp.get("queue", "")
        if not isinstance(exchange, str) or not exchange:
            raise ValidationError(f"behavior {key} expect.amqp.exchange is required")
        if not isinstance(routing_key, str) or not routing_key:
            raise ValidationError(f"behavior {key} expect.amqp.routing_key is required")
        if queue is None:
            queue = ""
        if not isinstance(queue, str):
            raise ValidationError(f"behavior {key} expect.amqp.queue must be a string")
        amqp_exchange = exchange
        amqp_routing_key = routing_key
        amqp_queue = queue or routing_key
    if http is None and kafka is None and amqp is None:
        raise ValidationError(f"behavior {key} expect.http, expect.kafka, or expect.amqp is required")
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


@dataclasses.dataclass
class DefinitionSnapshot:
    definitions: list[dict[str, Any]]
    behaviors: list[Behavior]


def filesystem_definition_entries(templates_dir: str | Path) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for path in discover_yaml_files(templates_dir):
        for raw in load_mock_file(path):
            if not isinstance(raw, dict):
                raise ValidationError("definition must be a mapping")
            entries.append((str(path), copy.deepcopy(raw)))
    return entries


def _definition_entries(label: str, definitions: list[Any]) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(definitions, list):
        raise ValidationError(f"{label} definitions must be a JSON array")
    entries: list[tuple[str, dict[str, Any]]] = []
    for raw in definitions:
        if not isinstance(raw, dict):
            raise ValidationError(f"{label} definition must be an object")
        entries.append((label, copy.deepcopy(raw)))
    return entries


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


def build_definition_snapshot(
    entries: list[tuple[str, dict[str, Any]]],
    templates_dir: str | Path,
    logger: JsonLogger | None = None,
) -> DefinitionSnapshot:
    logger = logger or JsonLogger("error")
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source, raw in entries:
        key, kind = _definition_kind(raw)
        if kind == "AbstractBehavior":
            _validate_abstract_definition(raw)
        if key in raw_by_key:
            order.remove(key)
            logger.warn("duplicate mock key override", key=key, file=source)
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
    return DefinitionSnapshot(definitions, behaviors)


def load_behaviors(templates_dir: str | Path, logger: JsonLogger | None = None) -> list[Behavior]:
    return build_definition_snapshot(filesystem_definition_entries(templates_dir), templates_dir, logger).behaviors


def _quote_redis_arg(value: Any) -> str:
    return shlex.quote(str(value))


def _load_json_array_from_key(store: RedisStore, key: str) -> list[Any]:
    raw = store.do(f"GET {_quote_redis_arg(key)}")
    if raw == "":
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid persisted JSON at {key}") from exc
    if not isinstance(value, list):
        raise ValidationError(f"persisted definitions at {key} must be an array")
    return value


def _store_json_array_at_key(store: RedisStore, key: str, definitions: list[Any]) -> None:
    store.do(
        "SET "
        + _quote_redis_arg(key)
        + " "
        + _quote_redis_arg(json.dumps(definitions, separators=(",", ":")))
    )


def load_base_api_definitions(store: RedisStore) -> list[Any]:
    return _load_json_array_from_key(store, INTERNAL_TEMPLATES_KEY)


def replace_base_api_definitions(store: RedisStore, definitions: list[Any]) -> None:
    _store_json_array_at_key(store, INTERNAL_TEMPLATES_KEY, definitions)


def clear_base_api_definitions(store: RedisStore) -> None:
    store.do(f"DEL {_quote_redis_arg(INTERNAL_TEMPLATES_KEY)}")


def template_set_storage_key(set_key: str) -> str:
    return INTERNAL_TEMPLATE_SET_PREFIX + set_key


def list_template_set_keys(store: RedisStore) -> list[str]:
    raw = store.do(f"KEYS {_quote_redis_arg(INTERNAL_TEMPLATE_SET_PREFIX + '*')}")
    if raw == "":
        return []
    keys = raw.split(";;")
    return sorted(key[len(INTERNAL_TEMPLATE_SET_PREFIX) :] for key in keys if key.startswith(INTERNAL_TEMPLATE_SET_PREFIX))


def load_template_set_definitions(store: RedisStore, set_key: str) -> list[Any]:
    return _load_json_array_from_key(store, template_set_storage_key(set_key))


def replace_template_set_definitions(store: RedisStore, set_key: str, definitions: list[Any]) -> None:
    _store_json_array_at_key(store, template_set_storage_key(set_key), definitions)


def delete_template_set_definitions(store: RedisStore, set_key: str) -> None:
    store.do(f"DEL {_quote_redis_arg(template_set_storage_key(set_key))}")


def persisted_definition_entries(
    store: RedisStore,
    base_definitions: list[Any] | None = None,
    template_sets: dict[str, list[Any]] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    base = load_base_api_definitions(store) if base_definitions is None else base_definitions
    sets = {
        set_key: load_template_set_definitions(store, set_key)
        for set_key in list_template_set_keys(store)
    }
    if template_sets is not None:
        sets = {key: copy.deepcopy(value) for key, value in template_sets.items()}
    entries = _definition_entries("api:templates", base)
    for set_key in sorted(sets):
        entries.extend(_definition_entries(f"api:template_set:{set_key}", sets[set_key]))
    return entries


def load_active_snapshot(
    config: Config,
    logger: JsonLogger,
    store: RedisStore,
    base_definitions: list[Any] | None = None,
    template_sets: dict[str, list[Any]] | None = None,
    filesystem_entries_: list[tuple[str, dict[str, Any]]] | None = None,
) -> DefinitionSnapshot:
    entries = (
        copy.deepcopy(filesystem_entries_)
        if filesystem_entries_ is not None
        else filesystem_definition_entries(config.templates_dir)
    )
    entries.extend(persisted_definition_entries(store, base_definitions, template_sets))
    return build_definition_snapshot(entries, config.templates_dir, logger)


def upsert_base_definitions(existing: list[Any], submitted: list[Any]) -> list[Any]:
    result = [copy.deepcopy(raw) for raw in existing]
    for raw in submitted:
        key, _ = _definition_kind(raw)
        result = [item for item in result if isinstance(item, dict) and item.get("key") != key]
        result.append(copy.deepcopy(raw))
    return result


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


def build_kafka_template_context(
    topic: str,
    payload: str,
    redis_do: Callable[[str], str] | None = None,
    values: dict[str, Any] | None = None,
    templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "KafkaTopic": topic,
        "KafkaPayload": payload,
        "Values": dict(values or {}),
    }
    if redis_do is not None:
        context["redisDo"] = redis_do
    if templates is not None:
        context["__templates"] = templates
    return context


def build_amqp_template_context(
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_do: Callable[[str], str] | None = None,
    values: dict[str, Any] | None = None,
    templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "AMQPExchange": exchange,
        "AMQPRoutingKey": routing_key,
        "AMQPQueue": queue,
        "AMQPPayload": payload,
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
class ResponseInfo:
    status_code: int
    headers: dict[str, str]
    body: str | bytes


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Credentials": "true",
}


def _body_bytes(body: str | bytes) -> bytes:
    return body if isinstance(body, bytes) else str(body).encode()


def _body_log_value(body: str | bytes) -> str:
    return body.decode(errors="replace") if isinstance(body, bytes) else str(body)


def _has_header(headers: dict[str, str], name: str) -> bool:
    return any(key.lower() == name.lower() for key in headers)


def _set_header_if_missing(headers: dict[str, str], name: str, value: str) -> None:
    if not _has_header(headers, name):
        headers[name] = value


def finalize_mock_response(response: ResponseInfo, config: Config) -> ResponseInfo:
    if not config.cors_enabled:
        return response
    headers = dict(response.headers)
    for key, value in CORS_HEADERS.items():
        _set_header_if_missing(headers, key, value)
    return ResponseInfo(response.status_code, headers, response.body)


def find_behavior(
    behaviors: list[Behavior],
    request: RequestInfo,
    redis_store: RedisStore | None = None,
) -> tuple[Behavior, dict[str, str]] | tuple[None, dict[str, str]]:
    redis_do = (
        (lambda command: guarded_redis_do(redis_store, command))
        if redis_store is not None
        else None
    )
    for behavior in behaviors:
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
            redis_do,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                return behavior, params
        except TemplateError:
            continue
    return None, {}


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
    elif payload.get("send_http_body_from_file_content") is not None:
        body_source = payload.get("send_http_body_from_file_content")
        data = render_template(str(body_source), context).encode()
    elif payload.get("send_http_body_from_binary_file_content") is not None:
        binary_body = payload["send_http_body_from_binary_file_content"]
        if method == "POST":
            data, headers = _multipart_file_body(payload, binary_body, headers)
        else:
            data = binary_body
    else:
        data = None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
    except Exception as exc:
        if logger is not None:
            logger.warn("send_http request failed", url=url, method=method, error=str(exc))


def _render_publish_payload(payload: dict[str, Any], context: dict[str, Any], file_content_key: str) -> str:
    body_source = payload.get("payload")
    if body_source is not None and body_source != "":
        return render_template(str(body_source), context)
    if payload.get(file_content_key) is not None:
        return render_template(str(payload[file_content_key]), context)
    return render_template(str(body_source or ""), context)


def _publish_kafka(
    payload: dict[str, Any],
    context: dict[str, Any],
    kafka_adapter: KafkaAdapter | None,
    logger: JsonLogger | None = None,
) -> None:
    topic = render_template(str(payload["topic"]), context)
    message_payload = _render_publish_payload(payload, context, "publish_kafka_payload_from_file_content")
    if kafka_adapter is None:
        if logger is not None:
            logger.warn("publish_kafka skipped", topic=topic, error="Kafka is not enabled")
        return
    try:
        kafka_adapter.publish(topic, message_payload)
    except Exception as exc:
        if logger is not None:
            logger.warn("publish_kafka failed", topic=topic, error=str(exc))


def _publish_amqp(
    payload: dict[str, Any],
    context: dict[str, Any],
    amqp_adapter: AMQPAdapter | None,
    logger: JsonLogger | None = None,
) -> None:
    exchange = render_template(str(payload["exchange"]), context)
    routing_key = render_template(str(payload["routing_key"]), context)
    message_payload = _render_publish_payload(payload, context, "publish_amqp_payload_from_file_content")
    if amqp_adapter is None:
        if logger is not None:
            logger.warn("publish_amqp skipped", exchange=exchange, routing_key=routing_key, error="AMQP is not enabled")
        return
    try:
        amqp_adapter.publish(exchange, routing_key, message_payload)
    except Exception as exc:
        if logger is not None:
            logger.warn("publish_amqp failed", exchange=exchange, routing_key=routing_key, error=str(exc))


def _header_value(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _without_header(headers: dict[str, str], name: str) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() != name.lower()}


def _quote_multipart_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _multipart_file_body(
    payload: dict[str, Any],
    binary_body: bytes,
    headers: dict[str, str],
) -> tuple[bytes, dict[str, str]]:
    boundary = "hmock-" + uuid.uuid4().hex
    filename = str(payload.get("binary_file_name") or Path(str(payload.get("body_from_binary_file"))).name)
    part_content_type = _header_value(headers, "Content-Type") or "application/octet-stream"
    request_headers = _without_header(headers, "Content-Type")
    request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{_quote_multipart_value(filename)}"\r\n'
        f"Content-Type: {part_content_type}\r\n"
        "\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()
    return prefix + binary_body + suffix, request_headers


def execute_behavior(
    behavior: Behavior,
    request: RequestInfo,
    params: dict[str, str],
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = lambda command: guarded_redis_do(redis_store, command)
    context = build_template_context(
        request.headers,
        request.body,
        request.path,
        request.query,
        params,
        redis_do,
        behavior.values,
        behavior.templates,
    )
    response = execute_behavior_actions(
        behavior,
        context,
        redis_do,
        logger,
        kafka_adapter,
        amqp_adapter,
        collect_response=True,
    )
    return response or ResponseInfo(204, {"Content-Length": "0"}, "")


def execute_behavior_actions(
    behavior: Behavior,
    context: dict[str, Any],
    redis_do: Callable[[str], str],
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
    collect_response: bool = False,
) -> ResponseInfo | None:
    response: ResponseInfo | None = None
    for action in behavior.actions:
        name, payload = _action_name_payload(action, behavior.key)
        if name == "sleep":
            time.sleep(parse_duration(str(payload["duration"])))
        elif name == "redis":
            for command_template in payload:
                redis_do(render_template(command_template, context))
        elif name == "send_http":
            _send_http(payload, context, logger)
        elif name == "publish_kafka":
            _publish_kafka(payload, context, kafka_adapter, logger)
        elif name == "publish_amqp":
            _publish_amqp(payload, context, amqp_adapter, logger)
        elif name == "reply_http":
            if not collect_response:
                continue
            body_source = payload.get("body")
            binary_body = None
            if body_source is not None and body_source != "":
                body: str | bytes = render_template(str(body_source), context)
            elif payload.get("body_from_binary_file_content") is not None:
                binary_body = payload["body_from_binary_file_content"]
                body = binary_body
            else:
                body_source = payload.get("body_from_file_content", "")
                body = render_template(str(body_source), context)
            headers = {
                str(key): render_template(str(value), context)
                for key, value in (payload.get("headers") or {}).items()
            }
            if not _has_header(headers, "Content-Type"):
                headers["Content-Type"] = "application/json"
            if binary_body is not None and payload.get("binary_file_name"):
                headers["Content-Disposition"] = f'inline; filename="{payload["binary_file_name"]}"'
            headers["Content-Length"] = str(len(_body_bytes(body)))
            response = ResponseInfo(int(payload["status_code"]), headers, body)
    return response


def _kafka_security_protocol(endpoint: KafkaEndpointConfig) -> str:
    if endpoint.sasl_enabled and endpoint.tls_enabled:
        return "SASL_SSL"
    if endpoint.sasl_enabled:
        return "SASL_PLAINTEXT"
    if endpoint.tls_enabled:
        return "SSL"
    return "PLAINTEXT"


class ConfluentKafkaAdapter:
    def __init__(self, config: Config) -> None:
        try:
            import confluent_kafka  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValidationError("Kafka support requires confluent_kafka when HM_KAFKA_ENABLED=true") from exc
        self._module = confluent_kafka
        producer_config = {
            "bootstrap.servers": ",".join(config.kafka_producer.seed_brokers),
            "client.id": config.kafka_client_id,
            "security.protocol": _kafka_security_protocol(config.kafka_producer),
        }
        consumer_config = {
            "bootstrap.servers": ",".join(config.kafka_consumer.seed_brokers),
            "client.id": config.kafka_client_id,
            "group.id": config.kafka_client_id,
            "auto.offset.reset": "earliest",
            "security.protocol": _kafka_security_protocol(config.kafka_consumer),
        }
        if config.kafka_producer.sasl_enabled:
            producer_config.update(
                {
                    "sasl.mechanism": "PLAIN",
                    "sasl.username": config.kafka_producer.sasl_username,
                    "sasl.password": config.kafka_producer.sasl_password,
                }
            )
        if config.kafka_consumer.sasl_enabled:
            consumer_config.update(
                {
                    "sasl.mechanism": "PLAIN",
                    "sasl.username": config.kafka_consumer.sasl_username,
                    "sasl.password": config.kafka_consumer.sasl_password,
                }
            )
        self._producer = confluent_kafka.Producer(producer_config)
        self._consumer = confluent_kafka.Consumer(consumer_config)
        self._topics: tuple[str, ...] = ()

    def publish(self, topic: str, payload: str) -> None:
        self._producer.produce(topic, payload.encode())
        self._producer.flush()

    def subscribe(self, topics: Iterable[str]) -> None:
        self._topics = tuple(sorted(set(topics)))
        if self._topics:
            self._consumer.subscribe(list(self._topics))

    def consume(self, callback: Callable[[KafkaMessage], None], stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            message = self._consumer.poll(0.2)
            if message is None:
                continue
            if message.error():
                raise HMockError(str(message.error()))
            callback(KafkaMessage(str(message.topic()), message.value().decode()))

    def close(self) -> None:
        self._consumer.close()


class PikaAMQPAdapter:
    def __init__(self, config: Config) -> None:
        try:
            import pika  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValidationError("AMQP support requires pika when HM_AMQP_ENABLED=true") from exc
        self._pika = pika
        self._url = config.amqp_url
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._connect()

    def _connect(self) -> None:
        self._connection = self._pika.BlockingConnection(self._pika.URLParameters(self._url))
        self._channel = self._connection.channel()

    def _ensure_channel(self) -> Any:
        if self._connection is None or self._connection.is_closed:
            self._connect()
        if self._channel is None or self._channel.is_closed:
            self._channel = self._connection.channel()
        return self._channel

    def setup_bindings(self, bindings: Iterable[AMQPBinding]) -> None:
        channel = self._ensure_channel()
        for binding in sorted(set(bindings)):
            if binding.exchange:
                channel.exchange_declare(exchange=binding.exchange, durable=True)
            channel.queue_declare(queue=binding.queue, durable=True)
            channel.queue_bind(
                exchange=binding.exchange,
                queue=binding.queue,
                routing_key=binding.routing_key,
            )

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        self._ensure_channel().basic_publish(exchange=exchange, routing_key=routing_key, body=payload.encode())

    def consume(self, bindings: Iterable[AMQPBinding], callback: Callable[[AMQPMessage], None], stop_event: threading.Event) -> None:
        channel = self._ensure_channel()
        queue_to_binding = {binding.queue: binding for binding in bindings}
        for queue_name in queue_to_binding:
            def on_message(ch: Any, method: Any, props: Any, body: bytes, queue: str = queue_name) -> None:
                callback(AMQPMessage(method.exchange, method.routing_key, queue, body.decode()))

            channel.basic_consume(queue=queue_name, auto_ack=True, on_message_callback=on_message)
        while not stop_event.is_set():
            self._connection.process_data_events(time_limit=0.2)

    def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            self._connection.close()


def build_kafka_adapter(config: Config) -> KafkaAdapter | None:
    if not config.kafka_enabled:
        return None
    return ConfluentKafkaAdapter(config)


def build_amqp_adapter(config: Config) -> AMQPAdapter | None:
    if not config.amqp_enabled:
        return None
    return PikaAMQPAdapter(config)


def kafka_topics_for_behaviors(behaviors: Iterable[Behavior]) -> tuple[str, ...]:
    return tuple(sorted({behavior.kafka_topic for behavior in behaviors if behavior.kafka_topic}))


def amqp_bindings_for_behaviors(behaviors: Iterable[Behavior]) -> tuple[AMQPBinding, ...]:
    return tuple(
        sorted(
            {
                AMQPBinding(str(behavior.amqp_exchange), str(behavior.amqp_routing_key), str(behavior.amqp_queue))
                for behavior in behaviors
                if behavior.amqp_exchange and behavior.amqp_routing_key and behavior.amqp_queue
            }
        )
    )


def matching_kafka_behaviors(
    behaviors: Iterable[Behavior],
    message: KafkaMessage,
    redis_store: RedisStore,
) -> list[Behavior]:
    redis_do = lambda command: guarded_redis_do(redis_store, command)
    matches: list[Behavior] = []
    for behavior in behaviors:
        if behavior.kafka_topic != message.topic:
            continue
        if not behavior.condition:
            matches.append(behavior)
            continue
        context = build_kafka_template_context(
            message.topic,
            message.payload,
            redis_do,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                matches.append(behavior)
        except TemplateError:
            continue
    return matches


def matching_amqp_behaviors(
    behaviors: Iterable[Behavior],
    message: AMQPMessage,
    redis_store: RedisStore,
) -> list[Behavior]:
    redis_do = lambda command: guarded_redis_do(redis_store, command)
    matches: list[Behavior] = []
    for behavior in behaviors:
        if (
            behavior.amqp_exchange != message.exchange
            or behavior.amqp_routing_key != message.routing_key
            or behavior.amqp_queue != message.queue
        ):
            continue
        if not behavior.condition:
            matches.append(behavior)
            continue
        context = build_amqp_template_context(
            message.exchange,
            message.routing_key,
            message.queue,
            message.payload,
            redis_do,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                matches.append(behavior)
        except TemplateError:
            continue
    return matches


class BrokerRuntime:
    def __init__(
        self,
        state: "HMockRuntimeState",
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
    ) -> None:
        self.state = state
        self.kafka_adapter = kafka_adapter
        self.amqp_adapter = amqp_adapter
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.kafka_topics: tuple[str, ...] = ()
        self.amqp_bindings: tuple[AMQPBinding, ...] = ()

    def start(self) -> None:
        if self.state.config.kafka_enabled and self.kafka_adapter is None:
            self.kafka_adapter = build_kafka_adapter(self.state.config)
        if self.state.config.amqp_enabled and self.amqp_adapter is None:
            self.amqp_adapter = build_amqp_adapter(self.state.config)
        self.refresh_from_snapshot()
        if self.state.config.kafka_enabled and self.kafka_adapter is not None:
            self._start_thread(self.kafka_adapter.consume, self.handle_kafka_message)
        if self.state.config.amqp_enabled and self.amqp_adapter is not None:
            self._start_thread(self._consume_amqp_with_reconnect)

    def _start_thread(self, target: Callable[..., None], *args: Any) -> None:
        thread = threading.Thread(target=target, args=(*args, self.stop_event), daemon=True)
        thread.start()
        self.threads.append(thread)

    def refresh_from_snapshot(self) -> None:
        behaviors, _ = self.state.snapshot()
        topics = kafka_topics_for_behaviors(behaviors)
        bindings = amqp_bindings_for_behaviors(behaviors)
        if self.kafka_adapter is not None and topics != self.kafka_topics:
            self.kafka_adapter.subscribe(topics)
            self.kafka_topics = topics
        if self.amqp_adapter is not None and bindings != self.amqp_bindings:
            self.amqp_adapter.setup_bindings(bindings)
            self.amqp_bindings = bindings

    def _consume_amqp_with_reconnect(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set() and self.amqp_adapter is not None:
            try:
                self.refresh_from_snapshot()
                self.amqp_adapter.consume(self.amqp_bindings, self.handle_amqp_message, stop_event)
            except Exception as exc:
                if stop_event.is_set():
                    break
                self.state.logger.warn("amqp consume disconnected", error=str(exc))
                self.reconnect_amqp()
                time.sleep(0.1)

    def reconnect_amqp(self) -> None:
        if self.amqp_adapter is not None:
            self.amqp_adapter.setup_bindings(self.amqp_bindings)

    def handle_kafka_message(self, message: KafkaMessage) -> None:
        if not self.state.config.kafka_enabled:
            return
        self.refresh_from_snapshot()
        behaviors, _ = self.state.snapshot()
        redis_do = lambda command: guarded_redis_do(self.state.redis_store, command)
        for behavior in matching_kafka_behaviors(behaviors, message, self.state.redis_store):
            context = build_kafka_template_context(
                message.topic,
                message.payload,
                redis_do,
                behavior.values,
                behavior.templates,
            )
            execute_behavior_actions(
                behavior,
                context,
                redis_do,
                self.state.logger,
                self.kafka_adapter,
                self.amqp_adapter,
                collect_response=False,
            )

    def handle_amqp_message(self, message: AMQPMessage) -> None:
        if not self.state.config.amqp_enabled:
            return
        self.refresh_from_snapshot()
        behaviors, _ = self.state.snapshot()
        redis_do = lambda command: guarded_redis_do(self.state.redis_store, command)
        for behavior in matching_amqp_behaviors(behaviors, message, self.state.redis_store):
            context = build_amqp_template_context(
                message.exchange,
                message.routing_key,
                message.queue,
                message.payload,
                redis_do,
                behavior.values,
                behavior.templates,
            )
            execute_behavior_actions(
                behavior,
                context,
                redis_do,
                self.state.logger,
                self.kafka_adapter,
                self.amqp_adapter,
                collect_response=False,
            )

    def stop(self) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=2)
        if self.kafka_adapter is not None:
            self.kafka_adapter.close()
        if self.amqp_adapter is not None:
            self.amqp_adapter.close()


def not_found_response() -> ResponseInfo:
    body = "not found"
    return ResponseInfo(
        404,
        {"Content-Type": "text/plain", "Content-Length": str(len(body.encode()))},
        body,
    )


@dataclasses.dataclass
class HMockRuntimeState:
    config: Config
    logger: JsonLogger
    redis_store: RedisStore
    active_behaviors: list[Behavior] = dataclasses.field(default_factory=list)
    active_definitions: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    filesystem_entries_: list[tuple[str, dict[str, Any]]] = dataclasses.field(default_factory=list)
    filesystem_signature_: FilesystemSignature = dataclasses.field(default_factory=tuple)
    lock: threading.RLock = dataclasses.field(default_factory=threading.RLock)
    kafka_adapter: KafkaAdapter | None = None
    amqp_adapter: AMQPAdapter | None = None
    broker_runtime: BrokerRuntime | None = None

    @classmethod
    def from_config(
        cls,
        config: Config,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
    ) -> "HMockRuntimeState":
        store = redis_store or build_redis_store(config)
        state = cls(config, logger, store, kafka_adapter=kafka_adapter, amqp_adapter=amqp_adapter)
        state.reload()
        return state

    @classmethod
    def from_behaviors(
        cls,
        behaviors: list[Behavior],
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
    ) -> "HMockRuntimeState":
        return cls(
            Config(templates_dir_hot_reload=False),
            logger,
            redis_store or MemoryRedisStore(),
            list(behaviors),
            [],
            kafka_adapter=kafka_adapter,
            amqp_adapter=amqp_adapter,
        )

    def snapshot(self) -> tuple[list[Behavior], list[dict[str, Any]]]:
        self.refresh_filesystem_if_needed()
        with self.lock:
            return list(self.active_behaviors), copy.deepcopy(self.active_definitions)

    def replace_snapshot(self, snapshot: DefinitionSnapshot) -> None:
        with self.lock:
            self.active_behaviors = list(snapshot.behaviors)
            self.active_definitions = copy.deepcopy(snapshot.definitions)
        if self.broker_runtime is not None:
            self.broker_runtime.refresh_from_snapshot()

    def reload(self) -> None:
        with self.lock:
            self.filesystem_entries_ = filesystem_definition_entries(self.config.templates_dir)
            self.filesystem_signature_ = filesystem_template_signature(self.config.templates_dir)
            snapshot = load_active_snapshot(
                self.config,
                self.logger,
                self.redis_store,
                filesystem_entries_=self.filesystem_entries_,
            )
            self.active_behaviors = list(snapshot.behaviors)
            self.active_definitions = copy.deepcopy(snapshot.definitions)

    def refresh_filesystem_if_needed(self) -> None:
        if not self.config.templates_dir_hot_reload:
            return
        with self.lock:
            signature = filesystem_template_signature(self.config.templates_dir)
            if signature == self.filesystem_signature_:
                return
            entries = filesystem_definition_entries(self.config.templates_dir)
            snapshot = load_active_snapshot(
                self.config,
                self.logger,
                self.redis_store,
                filesystem_entries_=entries,
            )
            self.filesystem_entries_ = entries
            self.filesystem_signature_ = signature
            self.active_behaviors = list(snapshot.behaviors)
            self.active_definitions = copy.deepcopy(snapshot.definitions)
        if self.broker_runtime is not None:
            self.broker_runtime.refresh_from_snapshot()

    def validate_candidate(
        self,
        base_definitions: list[Any] | None = None,
        template_sets: dict[str, list[Any]] | None = None,
    ) -> DefinitionSnapshot:
        self.refresh_filesystem_if_needed()
        return load_active_snapshot(
            self.config,
            self.logger,
            self.redis_store,
            base_definitions=base_definitions,
            template_sets=template_sets,
            filesystem_entries_=self.filesystem_entries_,
        )

    def start_brokers(self) -> None:
        if self.broker_runtime is not None:
            return
        if not self.config.kafka_enabled and not self.config.amqp_enabled:
            return
        self.broker_runtime = BrokerRuntime(self, self.kafka_adapter, self.amqp_adapter)
        self.broker_runtime.start()
        self.kafka_adapter = self.broker_runtime.kafka_adapter
        self.amqp_adapter = self.broker_runtime.amqp_adapter

    def stop_brokers(self) -> None:
        if self.broker_runtime is None:
            return
        self.broker_runtime.stop()
        self.broker_runtime = None


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
        behaviors, _ = self.server.runtime_state.snapshot()
        behavior, params = find_behavior(behaviors, request, self.server.runtime_state.redis_store)
        try:
            if behavior:
                response = execute_behavior(
                    behavior,
                    request,
                    params,
                    self.server.runtime_state.redis_store,
                    self.server.runtime_state.logger,
                    self.server.runtime_state.kafka_adapter,
                    self.server.runtime_state.amqp_adapter,
                )
            elif self.server.runtime_state.config.cors_enabled and request.method.upper() == "OPTIONS":
                response = ResponseInfo(200, {"Content-Length": "0"}, "")
            else:
                response = not_found_response()
        except TemplateError as exc:
            self.server.runtime_state.logger.error("template render error", error=str(exc), http_path=request.path)
            response = ResponseInfo(
                500,
                {"Content-Type": "text/plain", "Content-Length": "21"},
                "template render error",
            )
        response = finalize_mock_response(response, self.server.runtime_state.config)
        body_bytes = _body_bytes(response.body)
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if send_body:
            self.wfile.write(body_bytes)
        self.server.runtime_state.logger.info(
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
                "body": _body_log_value(response.body),
            },
        )


class HMockHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        behaviors_or_state: list[Behavior] | HMockRuntimeState,
        logger: JsonLogger | None = None,
        redis_store: RedisStore | None = None,
    ) -> None:
        super().__init__(address, MockHTTPRequestHandler)
        if isinstance(behaviors_or_state, HMockRuntimeState):
            self.runtime_state = behaviors_or_state
        else:
            if logger is None:
                raise TypeError("logger is required when constructing HMockHTTPServer with behaviors")
            self.runtime_state = HMockRuntimeState.from_behaviors(behaviors_or_state, logger, redis_store)
        self.runtime_state.start_brokers()
        self.hm_logger = self.runtime_state.logger
        self.redis_store = self.runtime_state.redis_store

    @property
    def behaviors(self) -> list[Behavior]:
        behaviors, _ = self.runtime_state.snapshot()
        return behaviors

    def server_close(self) -> None:
        self.runtime_state.stop_brokers()
        super().server_close()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _validate_submitted_definitions(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError("request body must be an array")
    for raw in value:
        if not isinstance(raw, dict):
            raise ValidationError("each mock definition must be an object")
        _definition_kind(raw)
    return copy.deepcopy(value)


def _base_definition_has_key(definitions: list[Any], key: str) -> bool:
    return any(isinstance(raw, dict) and raw.get("key") == key for raw in definitions)


class AdminHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "HMockAdminHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        self._handle_admin()

    def do_POST(self) -> None:
        self._handle_admin()

    def do_DELETE(self) -> None:
        self._handle_admin()

    def _read_request_body(self) -> str:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length).decode() if length else ""

    def _read_definition_body(self) -> Any:
        raw = self._read_request_body()
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type in {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"}:
            return parse_yaml_subset(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("request body must be valid JSON") from exc

    def _send_json(self, status: int, value: Any) -> None:
        body = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _path_parts(self) -> list[str]:
        path = urlsplit(self.path).path
        return [unquote(part) for part in path.strip("/").split("/") if part]

    def _handle_admin(self) -> None:
        try:
            self._route_admin()
        except ValidationError as exc:
            self._send_error_json(400, str(exc))
        except HMockError as exc:
            self._send_error_json(500, str(exc))

    def _route_admin(self) -> None:
        parts = self._path_parts()
        state = self.server.runtime_state
        if self.command == "GET" and parts == ["api", "v1", "health"]:
            self._send_json(200, {"status": "OK"})
            return
        if self.command == "GET" and parts == ["api", "v1", "templates"]:
            _, definitions = state.snapshot()
            self._send_json(200, definitions)
            return
        if self.command == "POST" and parts == ["api", "v1", "templates"]:
            submitted = _validate_submitted_definitions(self._read_definition_body())
            with state.lock:
                current = load_base_api_definitions(state.redis_store)
                updated = upsert_base_definitions(current, submitted)
                snapshot = state.validate_candidate(base_definitions=updated)
                replace_base_api_definitions(state.redis_store, updated)
                state.replace_snapshot(snapshot)
            self._send_json(200, submitted)
            return
        if self.command == "DELETE" and parts == ["api", "v1", "templates"]:
            with state.lock:
                snapshot = state.validate_candidate(base_definitions=[])
                clear_base_api_definitions(state.redis_store)
                state.replace_snapshot(snapshot)
            self._send_empty(204)
            return
        if self.command == "DELETE" and len(parts) == 4 and parts[:3] == ["api", "v1", "templates"]:
            template_key = parts[3]
            with state.lock:
                current = load_base_api_definitions(state.redis_store)
                if not _base_definition_has_key(current, template_key):
                    self._send_error_json(404, "template not found")
                    return
                updated = [copy.deepcopy(raw) for raw in current if not (isinstance(raw, dict) and raw.get("key") == template_key)]
                snapshot = state.validate_candidate(base_definitions=updated)
                replace_base_api_definitions(state.redis_store, updated)
                state.replace_snapshot(snapshot)
            self._send_empty(204)
            return
        if self.command == "POST" and len(parts) == 4 and parts[:3] == ["api", "v1", "template_sets"]:
            set_key = parts[3]
            submitted = _validate_submitted_definitions(self._read_definition_body())
            with state.lock:
                sets = {
                    key: load_template_set_definitions(state.redis_store, key)
                    for key in list_template_set_keys(state.redis_store)
                }
                sets[set_key] = submitted
                snapshot = state.validate_candidate(template_sets=sets)
                replace_template_set_definitions(state.redis_store, set_key, submitted)
                state.replace_snapshot(snapshot)
            self._send_json(200, submitted)
            return
        if self.command == "DELETE" and len(parts) == 4 and parts[:3] == ["api", "v1", "template_sets"]:
            set_key = parts[3]
            with state.lock:
                sets = {
                    key: load_template_set_definitions(state.redis_store, key)
                    for key in list_template_set_keys(state.redis_store)
                    if key != set_key
                }
                snapshot = state.validate_candidate(template_sets=sets)
                delete_template_set_definitions(state.redis_store, set_key)
                state.replace_snapshot(snapshot)
            self._send_empty(204)
            return
        self._send_error_json(404, "not found")


class HMockAdminHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], runtime_state: HMockRuntimeState) -> None:
        super().__init__(address, AdminHTTPRequestHandler)
        self.runtime_state = runtime_state


def build_runtime_state(config: Config | None = None, logger: JsonLogger | None = None) -> HMockRuntimeState:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    return HMockRuntimeState.from_config(config, logger)


def build_server(
    config: Config | None = None,
    logger: JsonLogger | None = None,
    runtime_state: HMockRuntimeState | None = None,
) -> HMockHTTPServer:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    state = runtime_state or HMockRuntimeState.from_config(config, logger)
    return HMockHTTPServer((config.http_host, config.http_port), state)


def build_admin_server(
    config: Config | None = None,
    logger: JsonLogger | None = None,
    runtime_state: HMockRuntimeState | None = None,
) -> HMockAdminHTTPServer | None:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    if not config.admin_http_enabled:
        return None
    state = runtime_state or HMockRuntimeState.from_config(config, logger)
    return HMockAdminHTTPServer((config.admin_http_host, config.admin_http_port), state)


def main() -> None:
    config = load_config()
    logger = JsonLogger(config.log_level)
    state = build_runtime_state(config, logger)
    server = build_server(config, logger, state)
    admin_server = build_admin_server(config, logger, state)
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


if __name__ == "__main__":
    main()
