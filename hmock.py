from __future__ import annotations

import argparse
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
import struct
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
from urllib.parse import quote, quote_plus, unquote, urlsplit


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
class AMQPConfig:
    enabled: bool = False
    url: str = "amqp://guest:guest@rabbitmq:5672"


@dataclasses.dataclass(frozen=True)
class GRPCConfig:
    enabled: bool = False
    port: int = 50051
    host: str = "0.0.0.0"
    descriptor_set_paths: tuple[str, ...] = ()


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
    kafka_producer: KafkaClientConfig = KafkaClientConfig()
    kafka_consumer: KafkaClientConfig = KafkaClientConfig()
    amqp: AMQPConfig = AMQPConfig()
    grpc: GRPCConfig = GRPCConfig()


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _split_env_list(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or ("",)


def _split_env_paths(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _resolve_kafka_client_config(env: dict[str, str], prefix: str) -> KafkaClientConfig:
    broker_value = env.get(f"HM_KAFKA_{prefix}_SEED_BROKERS", env.get("HM_KAFKA_SEED_BROKERS", "kafka:9092"))
    username = env.get(f"HM_KAFKA_SASL_{prefix}_USERNAME", env.get("HM_KAFKA_SASL_USERNAME", ""))
    password = env.get(f"HM_KAFKA_SASL_{prefix}_PASSWORD", env.get("HM_KAFKA_SASL_PASSWORD", ""))
    tls_enabled = _env_bool(
        env.get(f"HM_KAFKA_TLS_{prefix}_ENABLED"),
        _env_bool(env.get("HM_KAFKA_TLS_ENABLED"), False),
    )
    return KafkaClientConfig(
        seed_brokers=_split_env_list(broker_value),
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
        admin_http_enabled=_env_bool(env.get("HM_ADMIN_HTTP_ENABLED"), True),
        admin_http_port=int(env.get("HM_ADMIN_HTTP_PORT", "9998")),
        admin_http_host=env.get("HM_ADMIN_HTTP_HOST", "0.0.0.0"),
        templates_dir_hot_reload=_env_bool(env.get("HM_TEMPLATES_DIR_HOT_RELOAD"), True),
        cors_enabled=_env_bool(env.get("HM_CORS_ENABLED"), False),
        kafka_enabled=_env_bool(env.get("HM_KAFKA_ENABLED"), False),
        kafka_client_id=env.get("HM_KAFKA_CLIENT_ID", "hmock"),
        kafka_producer=_resolve_kafka_client_config(env, "PRODUCER"),
        kafka_consumer=_resolve_kafka_client_config(env, "CONSUMER"),
        amqp=AMQPConfig(
            enabled=_env_bool(env.get("HM_AMQP_ENABLED"), False),
            url=env.get("HM_AMQP_URL", "amqp://guest:guest@rabbitmq:5672"),
        ),
        grpc=GRPCConfig(
            enabled=_env_bool(env.get("HM_GRPC_ENABLED"), False),
            port=int(env.get("HM_GRPC_PORT", "50051")),
            host=env.get("HM_GRPC_HOST", "0.0.0.0"),
            descriptor_set_paths=_split_env_paths(env.get("HM_GRPC_DESCRIPTOR_SET_PATHS")),
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


def _redis_command_keys(parts: list[str]) -> list[str]:
    name = parts[0]
    args = parts[1:]
    if name in {"SET", "GET", "RPUSH", "LPUSH", "LRANGE", "LPOP", "RPOP", "HSET", "HGET", "HGETALL", "HDEL", "KEYS"}:
        return [args[0]]
    if name in {"DEL", "EXISTS"}:
        return args
    return []


def validate_user_redis_command(command: str) -> None:
    parts = _parse_redis_command(command)
    if parts[0] == "KEYS" and (
        fnmatch(BASE_TEMPLATES_KEY, parts[1])
        or fnmatch(f"{TEMPLATE_SET_KEY_PREFIX}example", parts[1])
    ):
        raise RedisError(f"Redis key pattern is reserved for internal hmock storage: {parts[1]}")
    for key in _redis_command_keys(parts):
        if key.startswith(INTERNAL_REDIS_PREFIX):
            raise RedisError(f"Redis key is reserved for internal hmock storage: {key}")


def user_redis_do(redis_store: RedisStore) -> Callable[[str], str]:
    def do(command: str) -> str:
        validate_user_redis_command(command)
        return redis_store.do(command)

    return do


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
BASE_TEMPLATES_KEY = f"{INTERNAL_REDIS_PREFIX}templates"
TEMPLATE_SET_KEY_PREFIX = f"{INTERNAL_REDIS_PREFIX}template_sets:"


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
    method: str
    path: str
    condition: str
    actions: list[dict[str, Any]]
    pattern: PathPattern | None
    values: dict[str, Any]
    templates: dict[str, str]
    kafka_topic: str = ""
    amqp_exchange: str = ""
    amqp_routing_key: str = ""
    amqp_queue: str = ""
    grpc_service: str = ""
    grpc_method: str = ""


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)", str(value))
    if not match:
        raise ValidationError(f"unsupported duration: {value}")
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
    return amount * factors[unit]


def _resolve_body_path(templates_dir: str | Path, body_from_file: str, field_name: str) -> Path:
    root = Path(templates_dir).resolve()
    path = (root / body_from_file).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {body_from_file}")
    return path


def _resolve_body_file(templates_dir: str | Path, body_from_file: str, field_name: str = "reply_http.body_from_file") -> str:
    return _resolve_body_path(templates_dir, body_from_file, field_name).read_text()


def _resolve_binary_body_file(templates_dir: str | Path, body_from_file: str, field_name: str) -> bytes:
    return _resolve_body_path(templates_dir, body_from_file, field_name).read_bytes()


def _validate_headers_mapping(headers: Any, field_name: str) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a mapping")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field_name} is required")
    return value


def _validate_text_payload_source(
    payload: dict[str, Any],
    key: str,
    action_name: str,
    templates_dir: str | Path | None,
) -> None:
    if "payload" not in payload and "payload_from_file" not in payload:
        raise ValidationError(f"behavior {key} {action_name}.payload or {action_name}.payload_from_file is required")
    if "payload" in payload and payload["payload"] is not None and not isinstance(payload["payload"], str):
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


def _validate_expect_mapping(expect: Any, key: str, *, require_target: bool) -> dict[str, Any]:
    if expect is None:
        expect = {}
    if not isinstance(expect, dict):
        raise ValidationError(f"behavior {key} expect must be a mapping")
    condition = expect.get("condition", "")
    if condition is None:
        condition = ""
    if not isinstance(condition, str):
        raise ValidationError(f"behavior {key} expect.condition must be a string")

    http = expect.get("http")
    if http is None:
        http = {}
    if not isinstance(http, dict):
        raise ValidationError(f"behavior {key} expect.http must be a mapping")
    method = ""
    path = ""
    pattern: PathPattern | None = None
    if http:
        method = _require_non_empty_string(http.get("method"), f"behavior {key} expect.http.method").upper()
        path = _require_non_empty_string(http.get("path"), f"behavior {key} expect.http.path")
        pattern = PathPattern.compile(path)

    kafka = expect.get("kafka")
    kafka_topic = ""
    if kafka is not None:
        if not isinstance(kafka, dict):
            raise ValidationError(f"behavior {key} expect.kafka must be a mapping")
        kafka_topic = _require_non_empty_string(kafka.get("topic"), f"behavior {key} expect.kafka.topic")

    amqp = expect.get("amqp")
    amqp_exchange = ""
    amqp_routing_key = ""
    amqp_queue = ""
    if amqp is not None:
        if not isinstance(amqp, dict):
            raise ValidationError(f"behavior {key} expect.amqp must be a mapping")
        amqp_exchange = _require_non_empty_string(amqp.get("exchange"), f"behavior {key} expect.amqp.exchange")
        amqp_routing_key = _require_non_empty_string(amqp.get("routing_key"), f"behavior {key} expect.amqp.routing_key")
        queue = amqp.get("queue")
        if queue is None or queue == "":
            amqp_queue = amqp_routing_key
            amqp["queue"] = amqp_queue
        elif isinstance(queue, str):
            amqp_queue = queue
        else:
            raise ValidationError(f"behavior {key} expect.amqp.queue must be a string")

    grpc = expect.get("grpc")
    grpc_service = ""
    grpc_method = ""
    if grpc is not None:
        if not isinstance(grpc, dict):
            raise ValidationError(f"behavior {key} expect.grpc must be a mapping")
        grpc_service = _require_non_empty_string(grpc.get("service"), f"behavior {key} expect.grpc.service")
        grpc_method = _require_non_empty_string(grpc.get("method"), f"behavior {key} expect.grpc.method")

    if require_target and not (pattern or kafka_topic or amqp_exchange or grpc_service):
        raise ValidationError(f"behavior {key} must define expect.http, expect.kafka, expect.amqp, or expect.grpc")
    return {
        "condition": condition,
        "method": method,
        "path": path,
        "pattern": pattern,
        "kafka_topic": kafka_topic,
        "amqp_exchange": amqp_exchange,
        "amqp_routing_key": amqp_routing_key,
        "amqp_queue": amqp_queue,
        "grpc_service": grpc_service,
        "grpc_method": grpc_method,
    }


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
            binary_file_name = payload.get("binary_file_name")
            if binary_file_name is not None and not isinstance(binary_file_name, str):
                raise ValidationError(f"behavior {key} reply_http.binary_file_name must be a string")
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
            binary_file_name = payload.get("binary_file_name")
            if binary_file_name is not None and not isinstance(binary_file_name, str):
                raise ValidationError(f"behavior {key} send_http.binary_file_name must be a string")
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
        elif name == "publish_kafka":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _require_non_empty_string(payload.get("topic"), f"behavior {key} publish_kafka.topic")
            _validate_text_payload_source(payload, key, "publish_kafka", templates_dir)
        elif name == "publish_amqp":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _require_non_empty_string(payload.get("exchange"), f"behavior {key} publish_amqp.exchange")
            _require_non_empty_string(payload.get("routing_key"), f"behavior {key} publish_amqp.routing_key")
            _validate_text_payload_source(payload, key, "publish_amqp", templates_dir)
        elif name == "reply_grpc":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _validate_text_payload_source(payload, key, "reply_grpc", templates_dir)
            _validate_headers_mapping(payload.get("headers", {}), f"behavior {key} reply_grpc.headers")
        else:
            raise ValidationError(f"behavior {key} action {name} is not supported")
    if reply_count > 1:
        raise ValidationError(f"behavior {key} has more than one reply_http action")
    return _sort_actions(actions, key)


def _validate_abstract_definition(raw: dict[str, Any], templates_dir: str | Path | None = None) -> None:
    key, kind = _definition_kind(raw)
    if kind != "AbstractBehavior":
        raise ValidationError(f"{kind} {key} cannot be used as an abstract behavior")
    _validate_expect_mapping(raw.get("expect", {}), key, require_target=False)
    _validate_actions(raw.get("actions", []), key, templates_dir)


def validate_behavior(
    raw: Any,
    templates_dir: str | Path | None = None,
    templates: dict[str, str] | None = None,
) -> Behavior:
    key, kind = _definition_kind(raw)
    if kind != "Behavior":
        raise ValidationError(f"{kind} {key} cannot be used as a concrete behavior")
    expect_info = _validate_expect_mapping(raw.get("expect", {}), key, require_target=True)
    values = raw.get("values", {})
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise ValidationError(f"behavior {key} values must be a mapping")
    sorted_actions = _validate_actions(raw.get("actions", []), key, templates_dir)
    return Behavior(
        key=key,
        kind=kind,
        method=expect_info["method"],
        path=expect_info["path"],
        condition=expect_info["condition"],
        actions=sorted_actions,
        pattern=expect_info["pattern"],
        values=dict(values),
        templates=dict(templates or {}),
        kafka_topic=expect_info["kafka_topic"],
        amqp_exchange=expect_info["amqp_exchange"],
        amqp_routing_key=expect_info["amqp_routing_key"],
        amqp_queue=expect_info["amqp_queue"],
        grpc_service=expect_info["grpc_service"],
        grpc_method=expect_info["grpc_method"],
    )


def load_mock_file(path: str | Path) -> list[Any]:
    parsed = parse_yaml_subset(Path(path).read_text())
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise ValidationError(f"{path} must contain a top-level list")
    return parsed


@dataclasses.dataclass(frozen=True)
class MockDefinitionRecord:
    raw: dict[str, Any]
    source: str


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


def load_filesystem_definition_records(templates_dir: str | Path) -> list[MockDefinitionRecord]:
    records: list[MockDefinitionRecord] = []
    for path in discover_yaml_files(templates_dir):
        for raw in load_mock_file(path):
            if not isinstance(raw, dict):
                raise ValidationError("definition must be a mapping")
            records.append(MockDefinitionRecord(copy.deepcopy(raw), str(path)))
    return records


def build_behavior_set(
    records: list[MockDefinitionRecord],
    templates_dir: str | Path,
    logger: JsonLogger | None = None,
) -> tuple[list[Behavior], list[dict[str, Any]]]:
    logger = logger or JsonLogger("error")
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        raw = record.raw
        key, kind = _definition_kind(raw)
        if kind == "AbstractBehavior":
            _validate_abstract_definition(raw)
        if key in raw_by_key:
            order.remove(key)
            logger.warn("duplicate mock key override", key=key, file=record.source)
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
    return behaviors, [copy.deepcopy(raw_by_key[key]) for key in order]


def load_behaviors(templates_dir: str | Path, logger: JsonLogger | None = None) -> list[Behavior]:
    records = load_filesystem_definition_records(templates_dir)
    behaviors, _ = build_behavior_set(records, templates_dir, logger)
    return behaviors


@dataclasses.dataclass(frozen=True)
class GRPCMethodDescriptor:
    service: str
    method: str
    request_type: str
    response_type: str


def behavior_uses_grpc(behavior: Behavior) -> bool:
    if behavior.grpc_service:
        return True
    return any(_action_name_payload(action, behavior.key)[0] == "reply_grpc" for action in behavior.actions)


def resolve_grpc_descriptor_set_paths(config: Config, behaviors: list[Behavior]) -> list[Path]:
    if not config.grpc.enabled or not any(behavior_uses_grpc(behavior) for behavior in behaviors):
        return []
    if not config.grpc.descriptor_set_paths:
        raise ValidationError("HM_GRPC_DESCRIPTOR_SET_PATHS is required when loaded behavior uses gRPC")
    root = Path(config.templates_dir)
    resolved: list[Path] = []
    for raw_path in config.grpc.descriptor_set_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise ValidationError(f"gRPC descriptor set not found: {raw_path}")
        resolved.append(path)
    return resolved


def _read_varint(data: bytes, index: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while index < len(data):
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, index
        shift += 7
        if shift > 63:
            break
    raise ValidationError("invalid protobuf varint in gRPC descriptor set")


def _iter_proto_fields(data: bytes) -> Iterable[tuple[int, int, bytes | int]]:
    index = 0
    while index < len(data):
        tag, index = _read_varint(data, index)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number <= 0:
            raise ValidationError("invalid protobuf field number in gRPC descriptor set")
        if wire_type == 0:
            value, index = _read_varint(data, index)
            yield field_number, wire_type, value
        elif wire_type == 1:
            if index + 8 > len(data):
                raise ValidationError("truncated 64-bit protobuf field in gRPC descriptor set")
            yield field_number, wire_type, data[index : index + 8]
            index += 8
        elif wire_type == 2:
            length, index = _read_varint(data, index)
            end = index + length
            if end > len(data):
                raise ValidationError("truncated length-delimited protobuf field in gRPC descriptor set")
            yield field_number, wire_type, data[index:end]
            index = end
        elif wire_type == 5:
            if index + 4 > len(data):
                raise ValidationError("truncated 32-bit protobuf field in gRPC descriptor set")
            yield field_number, wire_type, data[index : index + 4]
            index += 4
        else:
            raise ValidationError("unsupported protobuf wire type in gRPC descriptor set")


def _proto_text_fields(data: bytes, field_number: int) -> list[str]:
    values: list[str] = []
    for number, wire_type, value in _iter_proto_fields(data):
        if number == field_number and wire_type == 2 and isinstance(value, bytes):
            values.append(value.decode())
    return values


def _proto_message_fields(data: bytes, field_number: int) -> list[bytes]:
    values: list[bytes] = []
    for number, wire_type, value in _iter_proto_fields(data):
        if number == field_number and wire_type == 2 and isinstance(value, bytes):
            values.append(value)
    return values


def _parse_grpc_method_descriptor(service_name: str, data: bytes) -> GRPCMethodDescriptor:
    method_name = (_proto_text_fields(data, 1) or [""])[0]
    request_type = (_proto_text_fields(data, 2) or [""])[0].lstrip(".")
    response_type = (_proto_text_fields(data, 3) or [""])[0].lstrip(".")
    if not method_name or not request_type or not response_type:
        raise ValidationError("invalid gRPC method descriptor")
    return GRPCMethodDescriptor(service_name, method_name, request_type, response_type)


def _parse_grpc_service_descriptors(package: str, data: bytes) -> list[GRPCMethodDescriptor]:
    service_name = (_proto_text_fields(data, 1) or [""])[0]
    if not service_name:
        raise ValidationError("invalid gRPC service descriptor")
    qualified = f"{package}.{service_name}" if package else service_name
    return [
        _parse_grpc_method_descriptor(qualified, method_data)
        for method_data in _proto_message_fields(data, 2)
    ]


def _parse_file_descriptor_proto(data: bytes) -> list[GRPCMethodDescriptor]:
    package = (_proto_text_fields(data, 2) or [""])[0]
    methods: list[GRPCMethodDescriptor] = []
    for service_data in _proto_message_fields(data, 6):
        methods.extend(_parse_grpc_service_descriptors(package, service_data))
    return methods


def _parse_file_descriptor_set(data: bytes) -> dict[tuple[str, str], GRPCMethodDescriptor]:
    methods: dict[tuple[str, str], GRPCMethodDescriptor] = {}
    files = _proto_message_fields(data, 1)
    if not files:
        raise ValidationError("gRPC descriptor set does not contain file descriptors")
    for file_data in files:
        for method in _parse_file_descriptor_proto(file_data):
            methods[(method.service, method.method)] = method
    return methods


class GRPCDescriptorRegistry:
    def __init__(self, methods: dict[tuple[str, str], GRPCMethodDescriptor] | None = None) -> None:
        self._methods = methods or {}

    @classmethod
    def empty(cls) -> "GRPCDescriptorRegistry":
        return cls({})

    @classmethod
    def from_files(cls, paths: Iterable[Path]) -> "GRPCDescriptorRegistry":
        methods: dict[tuple[str, str], GRPCMethodDescriptor] = {}
        for path in paths:
            try:
                parsed = _parse_file_descriptor_set(path.read_bytes())
            except (OSError, UnicodeDecodeError, ValidationError) as exc:
                raise ValidationError(f"invalid gRPC descriptor set {path}: {exc}") from exc
            methods.update(parsed)
        return cls(methods)

    def get_method(self, service: str, method: str) -> GRPCMethodDescriptor:
        descriptor = self._methods.get((service, method))
        if descriptor is None:
            raise ValidationError(f"gRPC descriptor not found for {service}/{method}")
        return descriptor

    def validate_behaviors(self, behaviors: list[Behavior]) -> None:
        for behavior in behaviors:
            if behavior.grpc_service:
                self.get_method(behavior.grpc_service, behavior.grpc_method)

    def decode_request(self, service: str, method: str, framed_payload: bytes) -> str:
        self.get_method(service, method)
        payload = decode_grpc_frame(framed_payload)
        if not payload:
            return "{}"
        try:
            return payload.decode()
        except UnicodeDecodeError:
            return json.dumps({"base64": base64.b64encode(payload).decode()}, separators=(",", ":"))

    def encode_response(self, service: str, method: str, json_payload: str) -> bytes:
        self.get_method(service, method)
        try:
            parsed = json.loads(json_payload)
        except json.JSONDecodeError as exc:
            raise ValidationError("reply_grpc payload must render valid JSON") from exc
        payload = json.dumps(parsed, separators=(",", ":")).encode()
        return encode_grpc_frame(payload)


def build_grpc_descriptor_registry(config: Config, behaviors: list[Behavior]) -> GRPCDescriptorRegistry:
    paths = resolve_grpc_descriptor_set_paths(config, behaviors)
    if not paths:
        return GRPCDescriptorRegistry.empty()
    registry = GRPCDescriptorRegistry.from_files(paths)
    registry.validate_behaviors(behaviors)
    return registry


def decode_grpc_frame(data: bytes) -> bytes:
    if len(data) < 5:
        raise ValidationError("gRPC frame is too short")
    compressed = data[0]
    if compressed != 0:
        raise ValidationError("compressed gRPC frames are not supported")
    length = struct.unpack(">I", data[1:5])[0]
    if len(data) - 5 != length:
        raise ValidationError("gRPC frame length does not match payload")
    return data[5:]


def encode_grpc_frame(payload: bytes) -> bytes:
    return b"\x00" + struct.pack(">I", len(payload)) + payload


def _redis_arg(value: str) -> str:
    return shlex.quote(value)


def _load_json_definition_array(redis_store: RedisStore, key: str) -> list[dict[str, Any]]:
    payload = redis_store.do(f"GET {_redis_arg(key)}")
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid persisted mock JSON at {key}") from exc
    if not isinstance(parsed, list):
        raise ValidationError(f"persisted mock JSON at {key} must be an array")
    definitions: list[dict[str, Any]] = []
    for raw in parsed:
        if not isinstance(raw, dict):
            raise ValidationError(f"persisted mock JSON at {key} must contain objects")
        definitions.append(copy.deepcopy(raw))
    return definitions


def _store_json_definition_array(redis_store: RedisStore, key: str, definitions: list[dict[str, Any]]) -> None:
    payload = json.dumps(definitions, separators=(",", ":"))
    redis_store.do(f"SET {_redis_arg(key)} {_redis_arg(payload)}")


def _delete_storage_key(redis_store: RedisStore, key: str) -> None:
    redis_store.do(f"DEL {_redis_arg(key)}")


def _template_set_storage_key(set_key: str) -> str:
    if not set_key or "/" in set_key:
        raise ValidationError("template set key must be a single non-empty path segment")
    return f"{TEMPLATE_SET_KEY_PREFIX}{set_key}"


def _list_template_set_storage_keys(redis_store: RedisStore) -> list[str]:
    raw = redis_store.do(f"KEYS {_redis_arg(TEMPLATE_SET_KEY_PREFIX + '*')}")
    if not raw:
        return []
    return sorted(key for key in raw.split(";;") if key.startswith(TEMPLATE_SET_KEY_PREFIX))


def load_api_base_definitions(redis_store: RedisStore) -> list[dict[str, Any]]:
    return _load_json_definition_array(redis_store, BASE_TEMPLATES_KEY)


def store_api_base_definitions(redis_store: RedisStore, definitions: list[dict[str, Any]]) -> None:
    _store_json_definition_array(redis_store, BASE_TEMPLATES_KEY, definitions)


def load_template_set_definitions(redis_store: RedisStore, set_key: str) -> list[dict[str, Any]]:
    return _load_json_definition_array(redis_store, _template_set_storage_key(set_key))


def store_template_set_definitions(redis_store: RedisStore, set_key: str, definitions: list[dict[str, Any]]) -> None:
    _store_json_definition_array(redis_store, _template_set_storage_key(set_key), definitions)


def delete_template_set_definitions(redis_store: RedisStore, set_key: str) -> None:
    _delete_storage_key(redis_store, _template_set_storage_key(set_key))


def _records_for_definitions(definitions: list[dict[str, Any]], source: str) -> list[MockDefinitionRecord]:
    return [MockDefinitionRecord(copy.deepcopy(raw), source) for raw in definitions]


def _persisted_record_groups(redis_store: RedisStore) -> list[list[MockDefinitionRecord]]:
    groups: list[list[MockDefinitionRecord]] = []
    groups.append(_records_for_definitions(load_api_base_definitions(redis_store), BASE_TEMPLATES_KEY))
    for key in _list_template_set_storage_keys(redis_store):
        groups.append(_records_for_definitions(_load_json_definition_array(redis_store, key), key))
    return groups


def load_all_definition_records(
    config: Config,
    redis_store: RedisStore,
    logger: JsonLogger,
    *,
    skip_invalid_persisted: bool,
) -> list[MockDefinitionRecord]:
    filesystem_records = load_filesystem_definition_records(config.templates_dir)
    persisted_groups = _persisted_record_groups(redis_store)
    if not skip_invalid_persisted:
        return filesystem_records + [record for group in persisted_groups for record in group]

    accepted: list[MockDefinitionRecord] = []
    for group in persisted_groups:
        try:
            build_behavior_set(filesystem_records + accepted + group, config.templates_dir, logger)
        except ValidationError as exc:
            source = group[0].source if group else "persisted"
            logger.error("invalid persisted mock definitions skipped", source=source, error=str(exc))
            continue
        accepted.extend(group)
    return filesystem_records + accepted


FilesystemSignature = tuple[tuple[str, int, int], ...]


def filesystem_definition_signature(templates_dir: str | Path) -> FilesystemSignature:
    signature: list[tuple[str, int, int]] = []
    root = Path(templates_dir).resolve()
    for path in discover_yaml_files(root):
        stat = path.stat()
        try:
            name = str(path.resolve().relative_to(root))
        except ValueError:
            name = str(path.resolve())
        signature.append((name, stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


@dataclasses.dataclass
class HMockRuntimeState:
    config: Config
    logger: JsonLogger
    redis_store: RedisStore
    behaviors: list[Behavior] = dataclasses.field(default_factory=list)
    definitions: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    grpc_descriptors: GRPCDescriptorRegistry = dataclasses.field(default_factory=GRPCDescriptorRegistry.empty)
    broker_managers: list[Any] = dataclasses.field(default_factory=list)
    broker_publishers: Any | None = None
    _filesystem_signature: FilesystemSignature = dataclasses.field(default_factory=tuple)
    _lock: threading.RLock = dataclasses.field(default_factory=threading.RLock)

    def reload(self, *, skip_invalid_persisted: bool = False) -> None:
        filesystem_signature = filesystem_definition_signature(self.config.templates_dir)
        records = load_all_definition_records(
            self.config,
            self.redis_store,
            self.logger,
            skip_invalid_persisted=skip_invalid_persisted,
        )
        behaviors, definitions = build_behavior_set(records, self.config.templates_dir, self.logger)
        grpc_descriptors = build_grpc_descriptor_registry(self.config, behaviors)
        with self._lock:
            self.behaviors = behaviors
            self.definitions = definitions
            self.grpc_descriptors = grpc_descriptors
            self._filesystem_signature = filesystem_signature
        for manager in list(self.broker_managers):
            manager.refresh()

    def reload_if_filesystem_changed(self) -> None:
        if not self.config.templates_dir_hot_reload:
            return
        filesystem_signature = filesystem_definition_signature(self.config.templates_dir)
        with self._lock:
            if filesystem_signature == self._filesystem_signature:
                return
        self.reload(skip_invalid_persisted=True)

    def get_behaviors(self) -> list[Behavior]:
        with self._lock:
            return list(self.behaviors)

    def get_definitions(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.definitions)

    def get_grpc_descriptors(self) -> GRPCDescriptorRegistry:
        with self._lock:
            return self.grpc_descriptors

    def add_broker_manager(self, manager: Any) -> None:
        self.broker_managers.append(manager)
        manager.refresh()

    @classmethod
    def from_config(
        cls,
        config: Config,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
    ) -> "HMockRuntimeState":
        state = cls(config, logger, redis_store or build_redis_store(config))
        state.reload(skip_invalid_persisted=True)
        return state


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
    context = build_template_context({}, "", "", "", {}, redis_do, values, templates)
    context["KafkaTopic"] = topic
    context["KafkaPayload"] = payload
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
    context = build_template_context({}, "", "", "", {}, redis_do, values, templates)
    context["AMQPExchange"] = exchange
    context["AMQPRoutingKey"] = routing_key
    context["AMQPQueue"] = queue
    context["AMQPPayload"] = payload
    return context


def build_grpc_template_context(
    service: str,
    method: str,
    payload: str,
    headers: dict[str, str] | Iterable[tuple[str, str]],
    redis_do: Callable[[str], str] | None = None,
    values: dict[str, Any] | None = None,
    templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    context = build_template_context({}, "", "", "", {}, redis_do, values, templates)
    context["GRPCService"] = service
    context["GRPCMethod"] = method
    context["GRPCPayload"] = payload
    context["GRPCHeader"] = HeaderMap(headers)
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


@dataclasses.dataclass
class BrokerPublishers:
    kafka: Any | None = None
    amqp: Any | None = None


def _response_body_bytes(response: ResponseInfo) -> bytes:
    return response.body if isinstance(response.body, bytes) else response.body.encode()


def _response_body_log_value(response: ResponseInfo) -> str:
    if isinstance(response.body, bytes):
        return f"<binary {len(response.body)} bytes>"
    return response.body


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
            user_redis_do(redis_store) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                return behavior, params
        except TemplateError:
            continue
    return None, {}


def _quote_header_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _pop_header_case_insensitive(headers: dict[str, str], key: str, default: str) -> str:
    for existing in list(headers):
        if existing.lower() == key.lower():
            return headers.pop(existing)
    return default


def _multipart_file_body(filename: str, content_type: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----hmock-{uuid.uuid4().hex}"
    disposition = f'Content-Disposition: form-data; name="file"; filename="{_quote_header_value(filename)}"'
    head = (
        f"--{boundary}\r\n"
        f"{disposition}\r\n"
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + content + tail, boundary


def _send_http(payload: dict[str, Any], context: dict[str, Any], logger: JsonLogger | None = None) -> None:
    url = render_template(str(payload["url"]), context)
    method = render_template(str(payload["method"]), context).upper()
    headers = {
        str(key): render_template(str(value), context)
        for key, value in (payload.get("headers") or {}).items()
    }
    body_source = payload.get("body")
    binary_source = payload.get("send_http_body_from_binary_file_content")
    if body_source is None or body_source == "":
        body_source = payload.get("send_http_body_from_file_content")
    if (body_source is None or body_source == "") and binary_source is not None:
        if method == "POST":
            part_content_type = _pop_header_case_insensitive(headers, "Content-Type", "application/octet-stream")
            filename = payload.get("binary_file_name") or Path(str(payload.get("body_from_binary_file", "file"))).name
            data, boundary = _multipart_file_body(str(filename), part_content_type, binary_source)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            data = binary_source
    else:
        body = render_template(str(body_source), context) if body_source is not None else None
        data = body.encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
    except Exception as exc:
        if logger is not None:
            logger.warn("send_http request failed", url=url, method=method, error=str(exc))


def _render_text_payload(payload: dict[str, Any], action_name: str, context: dict[str, Any]) -> str:
    payload_source = payload.get("payload")
    if payload_source is None or payload_source == "":
        payload_source = payload.get(f"{action_name}_payload_from_file_content", "")
    return render_template(str(payload_source), context)


def _render_reply_http_response(payload: dict[str, Any], context: dict[str, Any]) -> ResponseInfo:
    body_source = payload.get("body")
    binary_source = payload.get("body_from_binary_file_content")
    body_is_binary = False
    if (body_source is None or body_source == "") and binary_source is not None:
        body = binary_source
        body_is_binary = True
    elif body_source is None or body_source == "":
        body_source = payload.get("body_from_file_content", "")
        body = render_template(str(body_source), context)
    else:
        body = render_template(str(body_source), context)
    headers = {
        str(key): render_template(str(value), context)
        for key, value in (payload.get("headers") or {}).items()
    }
    if not any(key.lower() == "content-type" for key in headers):
        headers["Content-Type"] = "application/json"
    body_length = len(body) if isinstance(body, bytes) else len(body.encode())
    headers["Content-Length"] = str(body_length)
    if body_is_binary and payload.get("binary_file_name"):
        filename = _quote_header_value(str(payload["binary_file_name"]))
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return ResponseInfo(int(payload["status_code"]), headers, body)


def _run_behavior_actions(
    behavior: Behavior,
    context: dict[str, Any],
    redis_store: RedisStore,
    logger: JsonLogger | None = None,
    publishers: BrokerPublishers | None = None,
    *,
    capture_response: bool,
) -> ResponseInfo | None:
    publishers = publishers or BrokerPublishers()
    response: ResponseInfo | None = None
    for action in behavior.actions:
        name, payload = _action_name_payload(action, behavior.key)
        if name == "sleep":
            time.sleep(parse_duration(str(payload["duration"])))
        elif name == "redis":
            for command_template in payload:
                user_redis_do(redis_store)(render_template(command_template, context))
        elif name == "send_http":
            _send_http(payload, context, logger)
        elif name == "publish_kafka":
            if publishers.kafka is None:
                raise HMockError("Kafka publisher is not configured")
            topic = render_template(str(payload["topic"]), context)
            publishers.kafka.publish(topic, _render_text_payload(payload, "publish_kafka", context))
        elif name == "publish_amqp":
            if publishers.amqp is None:
                raise HMockError("AMQP publisher is not configured")
            exchange = render_template(str(payload["exchange"]), context)
            routing_key = render_template(str(payload["routing_key"]), context)
            publishers.amqp.publish(exchange, routing_key, _render_text_payload(payload, "publish_amqp", context))
        elif name == "reply_http" and capture_response:
            response = _render_reply_http_response(payload, context)
    return response


def execute_behavior(
    behavior: Behavior,
    request: RequestInfo,
    params: dict[str, str],
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    publishers: BrokerPublishers | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    context = build_template_context(
        request.headers,
        request.body,
        request.path,
        request.query,
        params,
        user_redis_do(redis_store),
        behavior.values,
        behavior.templates,
    )
    response = _run_behavior_actions(
        behavior,
        context,
        redis_store,
        logger,
        publishers,
        capture_response=True,
    )
    return response or ResponseInfo(204, {"Content-Length": "0"}, "")


def _condition_matches(behavior: Behavior, context: dict[str, Any]) -> bool:
    if not behavior.condition:
        return True
    try:
        return render_template(behavior.condition, context) == "true"
    except TemplateError:
        return False


def dispatch_kafka_message(
    behaviors: list[Behavior],
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    publishers: BrokerPublishers | None = None,
) -> list[str]:
    redis_store = redis_store or MemoryRedisStore()
    matched: list[str] = []
    for behavior in behaviors:
        if behavior.kafka_topic != topic:
            continue
        context = build_kafka_template_context(
            topic,
            payload,
            user_redis_do(redis_store),
            behavior.values,
            behavior.templates,
        )
        if not _condition_matches(behavior, context):
            continue
        _run_behavior_actions(
            behavior,
            context,
            redis_store,
            logger,
            publishers,
            capture_response=False,
        )
        matched.append(behavior.key)
    if logger is not None and matched:
        logger.info("kafka message matched", kafka_topic=topic, behaviors=matched)
    return matched


def dispatch_amqp_message(
    behaviors: list[Behavior],
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    publishers: BrokerPublishers | None = None,
) -> list[str]:
    redis_store = redis_store or MemoryRedisStore()
    matched: list[str] = []
    for behavior in behaviors:
        if (
            behavior.amqp_exchange != exchange
            or behavior.amqp_routing_key != routing_key
            or behavior.amqp_queue != queue
        ):
            continue
        context = build_amqp_template_context(
            exchange,
            routing_key,
            queue,
            payload,
            user_redis_do(redis_store),
            behavior.values,
            behavior.templates,
        )
        if not _condition_matches(behavior, context):
            continue
        _run_behavior_actions(
            behavior,
            context,
            redis_store,
            logger,
            publishers,
            capture_response=False,
        )
        matched.append(behavior.key)
    if logger is not None and matched:
        logger.info(
            "amqp message matched",
            amqp_exchange=exchange,
            amqp_routing_key=routing_key,
            amqp_queue=queue,
            behaviors=matched,
        )
    return matched


def _render_grpc_response(
    behavior: Behavior,
    context: dict[str, Any],
    registry: GRPCDescriptorRegistry,
) -> ResponseInfo | None:
    response: ResponseInfo | None = None
    for action in behavior.actions:
        name, payload = _action_name_payload(action, behavior.key)
        if name != "reply_grpc":
            continue
        payload_json = _render_text_payload(payload, "reply_grpc", context)
        body = registry.encode_response(behavior.grpc_service, behavior.grpc_method, payload_json)
        headers = {
            str(key): render_template(str(value), context)
            for key, value in (payload.get("headers") or {}).items()
        }
        headers["grpc-status"] = "0"
        headers["grpc-message"] = "OK"
        headers["Content-Type"] = "application/grpc"
        response = ResponseInfo(200, headers, body)
    return response


def execute_grpc_behavior(
    behavior: Behavior,
    service: str,
    method: str,
    framed_payload: bytes,
    headers: dict[str, str] | Iterable[tuple[str, str]],
    registry: GRPCDescriptorRegistry,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    publishers: BrokerPublishers | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    payload = registry.decode_request(service, method, framed_payload)
    context = build_grpc_template_context(
        service,
        method,
        payload,
        headers,
        user_redis_do(redis_store),
        behavior.values,
        behavior.templates,
    )
    _run_behavior_actions(
        behavior,
        context,
        redis_store,
        logger,
        publishers,
        capture_response=False,
    )
    response = _render_grpc_response(behavior, context, registry)
    return response or ResponseInfo(
        200,
        {"grpc-status": "0", "grpc-message": "OK", "Content-Type": "application/grpc"},
        encode_grpc_frame(b""),
    )


def dispatch_grpc_request(
    behaviors: list[Behavior],
    service: str,
    method: str,
    framed_payload: bytes,
    headers: dict[str, str] | Iterable[tuple[str, str]],
    registry: GRPCDescriptorRegistry,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    publishers: BrokerPublishers | None = None,
) -> tuple[str | None, ResponseInfo | None]:
    redis_store = redis_store or MemoryRedisStore()
    for behavior in behaviors:
        if behavior.grpc_service != service or behavior.grpc_method != method:
            continue
        payload = registry.decode_request(service, method, framed_payload)
        context = build_grpc_template_context(
            service,
            method,
            payload,
            headers,
            user_redis_do(redis_store),
            behavior.values,
            behavior.templates,
        )
        if not _condition_matches(behavior, context):
            continue
        response = execute_grpc_behavior(
            behavior,
            service,
            method,
            framed_payload,
            headers,
            registry,
            redis_store,
            logger,
            publishers,
        )
        if logger is not None:
            logger.info("grpc request matched", grpc_service=service, grpc_method=method, behavior=behavior.key)
        return behavior.key, response
    return None, None


class MissingBrokerAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def start(self, callback: Callable[..., None] | None = None) -> None:
        raise ValidationError(f"{self.name} support is enabled but no {self.name} adapter is configured")

    def stop(self) -> None:
        return

    def subscribe(self, topics: Iterable[str]) -> None:
        return

    def configure(self, bindings: Iterable[tuple[str, str, str]]) -> None:
        return

    def publish(self, *args: Any) -> None:
        raise HMockError(f"{self.name} publisher is not configured")


class KafkaBrokerManager:
    def __init__(
        self,
        state: HMockRuntimeState,
        adapter: Any,
    ) -> None:
        self.state = state
        self.adapter = adapter
        self.started = False

    def start(self) -> None:
        self.adapter.start(self.handle_message)
        self.started = True
        self.refresh()

    def stop(self) -> None:
        self.started = False
        self.adapter.stop()

    def refresh(self) -> None:
        topics = sorted({behavior.kafka_topic for behavior in self.state.get_behaviors() if behavior.kafka_topic})
        self.adapter.subscribe(topics)

    def publish(self, topic: str, payload: str) -> None:
        self.adapter.publish(topic, payload)

    def handle_message(self, topic: str, payload: str) -> list[str]:
        return dispatch_kafka_message(
            self.state.get_behaviors(),
            topic,
            payload,
            self.state.redis_store,
            self.state.logger,
            self.state.broker_publishers,
        )


class AMQPBrokerManager:
    def __init__(
        self,
        state: HMockRuntimeState,
        adapter: Any,
    ) -> None:
        self.state = state
        self.adapter = adapter
        self.started = False

    def start(self) -> None:
        self.adapter.start(self.handle_message)
        self.started = True
        self.refresh()

    def stop(self) -> None:
        self.started = False
        self.adapter.stop()

    def refresh(self) -> None:
        bindings = sorted(
            {
                (behavior.amqp_exchange, behavior.amqp_routing_key, behavior.amqp_queue)
                for behavior in self.state.get_behaviors()
                if behavior.amqp_exchange
            }
        )
        self.adapter.configure(bindings)

    def recover(self) -> None:
        self.adapter.stop()
        self.adapter.start(self.handle_message)
        self.refresh()

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        self.adapter.publish(exchange, routing_key, payload)

    def handle_message(self, exchange: str, routing_key: str, queue: str, payload: str) -> list[str]:
        return dispatch_amqp_message(
            self.state.get_behaviors(),
            exchange,
            routing_key,
            queue,
            payload,
            self.state.redis_store,
            self.state.logger,
            self.state.broker_publishers,
        )


def build_broker_managers(state: HMockRuntimeState) -> list[Any]:
    managers: list[Any] = []
    publishers = BrokerPublishers()
    if state.config.kafka_enabled:
        kafka = KafkaBrokerManager(state, MissingBrokerAdapter("Kafka"))
        managers.append(kafka)
        publishers.kafka = kafka
    if state.config.amqp.enabled:
        amqp = AMQPBrokerManager(state, MissingBrokerAdapter("AMQP"))
        managers.append(amqp)
        publishers.amqp = amqp
    state.broker_publishers = publishers
    for manager in managers:
        state.add_broker_manager(manager)
    return managers


def not_found_response() -> ResponseInfo:
    body = "not found"
    return ResponseInfo(
        404,
        {"Content-Type": "text/plain", "Content-Length": str(len(body.encode()))},
        body,
    )


def _json_response(status_code: int, payload: Any) -> ResponseInfo:
    body = json.dumps(payload, separators=(",", ":"))
    return ResponseInfo(
        status_code,
        {
            "Content-Type": "application/json",
            "Content-Length": str(len(body.encode())),
        },
        body,
    )


def _empty_response(status_code: int) -> ResponseInfo:
    return ResponseInfo(status_code, {"Content-Length": "0"}, "")


def _error_response(status_code: int, message: str) -> ResponseInfo:
    return _json_response(status_code, {"error": message})


SUPPORTED_EVALUATION_MATCHERS = {"http", "kafka", "amqp", "grpc"}


def _ensure_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field_name} must be an object")
    return value


def _evaluation_context_object(context: dict[str, Any], name: str) -> dict[str, Any]:
    return _ensure_mapping(context.get(name), f"context.{name}")


def _validate_evaluation_request(payload: Any) -> tuple[Behavior, dict[str, Any]]:
    request = _ensure_mapping(payload, "request body")
    mock = _ensure_mapping(request.get("mock"), "mock")
    context = request.get("context")
    if isinstance(context, list):
        raise ValidationError("context must be an object, not an array")
    context = _ensure_mapping(context, "context")
    key = mock.get("key")
    if not isinstance(key, str) or not key:
        raise ValidationError("mock.key must be non-empty")
    expect = _ensure_mapping(mock.get("expect"), "mock.expect")
    declared = {name for name in SUPPORTED_EVALUATION_MATCHERS if name in expect and expect.get(name) is not None}
    if not declared:
        raise ValidationError("mock.expect must include http, kafka, amqp, or grpc")
    required_context = {
        "http": "http_context",
        "kafka": "kafka_context",
        "amqp": "amqp_context",
        "grpc": "grpc_context",
    }
    for matcher in declared:
        _evaluation_context_object(context, required_context[matcher])
    return validate_behavior(copy.deepcopy(mock)), context


def _context_string(mapping: dict[str, Any], field_name: str, default: str = "") -> str:
    value = mapping.get(field_name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    return value


def _context_headers(mapping: dict[str, Any], field_name: str = "headers") -> dict[str, str]:
    headers = mapping.get(field_name, {})
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a string map")
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")
        normalized[key] = value
    return normalized


def _evaluation_http_match(behavior: Behavior, context: dict[str, Any]) -> tuple[bool, dict[str, str]]:
    if behavior.pattern is None:
        return True, {}
    http = _evaluation_context_object(context, "http_context")
    method = _context_string(http, "method").upper()
    path = _context_string(http, "path")
    if method != behavior.method:
        return False, {}
    params = behavior.pattern.match(path)
    return (params is not None, params or {})


def _evaluation_kafka_match(behavior: Behavior, context: dict[str, Any]) -> bool:
    if not behavior.kafka_topic:
        return True
    kafka = _evaluation_context_object(context, "kafka_context")
    return _context_string(kafka, "topic") == behavior.kafka_topic


def _evaluation_amqp_match(behavior: Behavior, context: dict[str, Any]) -> bool:
    if not behavior.amqp_exchange:
        return True
    amqp = _evaluation_context_object(context, "amqp_context")
    queue = _context_string(amqp, "queue", "")
    if not queue:
        queue = _context_string(amqp, "routing_key")
    return (
        _context_string(amqp, "exchange") == behavior.amqp_exchange
        and _context_string(amqp, "routing_key") == behavior.amqp_routing_key
        and queue == behavior.amqp_queue
    )


def _evaluation_grpc_match(behavior: Behavior, context: dict[str, Any]) -> bool:
    if not behavior.grpc_service:
        return True
    grpc = _evaluation_context_object(context, "grpc_context")
    return (
        _context_string(grpc, "service") == behavior.grpc_service
        and _context_string(grpc, "method") == behavior.grpc_method
    )


def _evaluation_expect_match(behavior: Behavior, context: dict[str, Any]) -> tuple[bool, dict[str, str]]:
    http_passed, path_params = _evaluation_http_match(behavior, context)
    if not http_passed:
        return False, {}
    if not _evaluation_kafka_match(behavior, context):
        return False, {}
    if not _evaluation_amqp_match(behavior, context):
        return False, {}
    if not _evaluation_grpc_match(behavior, context):
        return False, {}
    return True, path_params


def build_evaluation_template_context(behavior: Behavior, context: dict[str, Any], path_params: dict[str, str]) -> dict[str, Any]:
    http = context.get("http_context") if isinstance(context.get("http_context"), dict) else {}
    merged = build_template_context(
        _context_headers(http),
        _context_string(http, "body", ""),
        _context_string(http, "path", ""),
        _context_string(http, "query_string", ""),
        path_params,
        None,
        behavior.values,
        behavior.templates,
    )
    kafka = context.get("kafka_context")
    if isinstance(kafka, dict):
        merged["KafkaTopic"] = _context_string(kafka, "topic", "")
        merged["KafkaPayload"] = _context_string(kafka, "payload", "")
    amqp = context.get("amqp_context")
    if isinstance(amqp, dict):
        routing_key = _context_string(amqp, "routing_key", "")
        queue = _context_string(amqp, "queue", "") or routing_key
        merged["AMQPExchange"] = _context_string(amqp, "exchange", "")
        merged["AMQPRoutingKey"] = routing_key
        merged["AMQPQueue"] = queue
        merged["AMQPPayload"] = _context_string(amqp, "payload", "")
    grpc = context.get("grpc_context")
    if isinstance(grpc, dict):
        merged["GRPCService"] = _context_string(grpc, "service", "")
        merged["GRPCMethod"] = _context_string(grpc, "method", "")
        merged["GRPCPayload"] = _context_string(grpc, "payload", "")
        merged["GRPCHeader"] = HeaderMap(_context_headers(grpc))
    return merged


def _header_value(headers: dict[str, str], key: str, default: str = "") -> str:
    for existing, value in headers.items():
        if existing.lower() == key.lower():
            return value
    return default


def _dry_run_action_results(behavior: Behavior, context: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for action in behavior.actions:
        name, payload = _action_name_payload(action, behavior.key)
        if name == "reply_http":
            response = _render_reply_http_response(payload, context)
            results.append(
                {
                    "type": "reply_http_action_performed",
                    "status_code": str(response.status_code),
                    "content_type": _header_value(response.headers, "Content-Type", "application/json"),
                    "body": response.body.decode() if isinstance(response.body, bytes) else response.body,
                    "headers": response.headers,
                }
            )
        elif name == "publish_kafka":
            results.append(
                {
                    "type": "publish_kafka_action_performed",
                    "topic": render_template(str(payload["topic"]), context),
                    "payload": _render_text_payload(payload, "publish_kafka", context),
                }
            )
    return results


def evaluate_mock_definition(payload: Any) -> dict[str, Any]:
    behavior, raw_context = _validate_evaluation_request(payload)
    expect_passed, path_params = _evaluation_expect_match(behavior, raw_context)
    if not expect_passed:
        return {
            "expect_passed": False,
            "condition_passed": False,
            "condition_rendered": "",
            "actions_performed": [],
        }
    context = build_evaluation_template_context(behavior, raw_context, path_params)
    condition_rendered = render_template(behavior.condition, context) if behavior.condition else "true"
    condition_passed = condition_rendered == "true"
    if not condition_passed:
        return {
            "expect_passed": True,
            "condition_passed": False,
            "condition_rendered": condition_rendered,
            "actions_performed": [],
        }
    return {
        "expect_passed": True,
        "condition_passed": True,
        "condition_rendered": condition_rendered,
        "actions_performed": _dry_run_action_results(behavior, context),
    }


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Credentials": "true",
}


def _add_header_if_absent(headers: dict[str, str], key: str, value: str) -> None:
    if not any(existing.lower() == key.lower() for existing in headers):
        headers[key] = value


def apply_cors(response: ResponseInfo, enabled: bool) -> ResponseInfo:
    if not enabled:
        return response
    headers = dict(response.headers)
    for key, value in CORS_HEADERS.items():
        _add_header_if_absent(headers, key, value)
    return ResponseInfo(response.status_code, headers, response.body)


def _normalize_definition_array(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError("request body must be a JSON array of mock definitions")
    definitions: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValidationError("mock definition must be an object")
        _definition_kind(raw)
        definitions.append(copy.deepcopy(raw))
    return definitions


def _upsert_definitions(current: list[dict[str, Any]], submitted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in current:
        key, _ = _definition_kind(raw)
        if key not in by_key:
            order.append(key)
        by_key[key] = copy.deepcopy(raw)
    for raw in submitted:
        key, _ = _definition_kind(raw)
        if key not in by_key:
            order.append(key)
        by_key[key] = copy.deepcopy(raw)
    return [by_key[key] for key in order if key in by_key]


def _remove_definition(current: list[dict[str, Any]], key: str) -> tuple[list[dict[str, Any]], bool]:
    removed = False
    kept: list[dict[str, Any]] = []
    for raw in current:
        raw_key, _ = _definition_kind(raw)
        if raw_key == key:
            removed = True
            continue
        kept.append(copy.deepcopy(raw))
    return kept, removed


def _reload_after_storage_change(state: HMockRuntimeState) -> None:
    state.reload(skip_invalid_persisted=False)


class AdminHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "HMockAdminHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def _handle(self) -> None:
        try:
            response = self._route()
        except ValidationError as exc:
            response = _error_response(400, str(exc))
        except HMockError as exc:
            response = _error_response(500, str(exc))
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if response.body:
            self.wfile.write(_response_body_bytes(response))

    def _route(self) -> ResponseInfo:
        path = urlsplit(self.path).path
        if self.command == "GET" and path == "/api/v1/health":
            return _json_response(200, {"status": "OK"})
        if self.command == "GET" and path == "/api/v1/templates":
            return _json_response(200, self.server.runtime_state.get_definitions())
        if self.command == "POST" and path == "/api/v1/evaluate":
            return self._post_evaluate()
        if self.command == "POST" and path == "/api/v1/templates":
            return self._post_templates()
        if self.command == "DELETE" and path == "/api/v1/templates":
            return self._delete_templates()
        if self.command == "DELETE" and path.startswith("/api/v1/templates/"):
            template_key = unquote(path.removeprefix("/api/v1/templates/"))
            if not template_key or "/" in template_key:
                return _error_response(404, "template not found")
            return self._delete_template(template_key)
        if self.command == "POST" and path.startswith("/api/v1/template_sets/"):
            set_key = unquote(path.removeprefix("/api/v1/template_sets/"))
            return self._post_template_set(set_key)
        if self.command == "DELETE" and path.startswith("/api/v1/template_sets/"):
            set_key = unquote(path.removeprefix("/api/v1/template_sets/"))
            return self._delete_template_set(set_key)
        return _error_response(404, "not found")

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length).decode() if length else ""
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValidationError("request body must be valid JSON") from exc

    def _post_evaluate(self) -> ResponseInfo:
        result = evaluate_mock_definition(self._read_json_body())
        return _json_response(200, result)

    def _read_definitions(self) -> list[dict[str, Any]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length).decode() if length else ""
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            if content_type not in {"application/yaml", "application/x-yaml", "text/yaml"}:
                raise ValidationError("request body must be valid JSON") from exc
            parsed = parse_yaml_subset(raw_body)
        return _normalize_definition_array(parsed)

    def _post_templates(self) -> ResponseInfo:
        submitted = self._read_definitions()
        state = self.server.runtime_state
        store = state.redis_store
        previous = load_api_base_definitions(store)
        updated = _upsert_definitions(previous, submitted)
        try:
            store_api_base_definitions(store, updated)
            _reload_after_storage_change(state)
        except HMockError:
            store_api_base_definitions(store, previous)
            state.reload(skip_invalid_persisted=True)
            raise
        state.logger.info("admin templates upserted", count=len(submitted))
        return _json_response(200, submitted)

    def _delete_templates(self) -> ResponseInfo:
        state = self.server.runtime_state
        store = state.redis_store
        previous = load_api_base_definitions(store)
        try:
            _delete_storage_key(store, BASE_TEMPLATES_KEY)
            _reload_after_storage_change(state)
        except HMockError:
            store_api_base_definitions(store, previous)
            state.reload(skip_invalid_persisted=True)
            raise
        state.logger.info("admin templates deleted")
        return _empty_response(204)

    def _delete_template(self, template_key: str) -> ResponseInfo:
        state = self.server.runtime_state
        store = state.redis_store
        previous = load_api_base_definitions(store)
        updated, removed = _remove_definition(previous, template_key)
        if not removed:
            return _error_response(404, "template not found")
        try:
            store_api_base_definitions(store, updated)
            _reload_after_storage_change(state)
        except HMockError:
            store_api_base_definitions(store, previous)
            state.reload(skip_invalid_persisted=True)
            raise
        state.logger.info("admin template deleted", key=template_key)
        return _empty_response(204)

    def _post_template_set(self, set_key: str) -> ResponseInfo:
        submitted = self._read_definitions()
        state = self.server.runtime_state
        store = state.redis_store
        storage_key = _template_set_storage_key(set_key)
        existing_keys = set(_list_template_set_storage_keys(store))
        existed = storage_key in existing_keys
        previous = _load_json_definition_array(store, storage_key) if existed else []
        try:
            store_template_set_definitions(store, set_key, submitted)
            _reload_after_storage_change(state)
        except HMockError:
            if existed:
                _store_json_definition_array(store, storage_key, previous)
            else:
                _delete_storage_key(store, storage_key)
            state.reload(skip_invalid_persisted=True)
            raise
        state.logger.info("admin template set replaced", key=set_key, count=len(submitted))
        return _json_response(200, submitted)

    def _delete_template_set(self, set_key: str) -> ResponseInfo:
        state = self.server.runtime_state
        store = state.redis_store
        _template_set_storage_key(set_key)
        delete_template_set_definitions(store, set_key)
        _reload_after_storage_change(state)
        state.logger.info("admin template set deleted", key=set_key)
        return _empty_response(204)


class HMockAdminHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], runtime_state: HMockRuntimeState) -> None:
        super().__init__(address, AdminHTTPRequestHandler)
        self.runtime_state = runtime_state


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
        try:
            self.server.runtime_state.reload_if_filesystem_changed()
            behavior, params = find_behavior(
                self.server.runtime_state.get_behaviors(),
                request,
                self.server.runtime_state.redis_store,
            )
            if behavior:
                response = execute_behavior(
                    behavior,
                    request,
                    params,
                    self.server.runtime_state.redis_store,
                    self.server.hm_logger,
                    self.server.runtime_state.broker_publishers,
                )
            elif self.command == "OPTIONS" and self.server.runtime_state.config.cors_enabled:
                response = _empty_response(200)
            else:
                response = not_found_response()
        except TemplateError as exc:
            self.server.hm_logger.error("template render error", error=str(exc), http_path=request.path)
            response = ResponseInfo(
                500,
                {"Content-Type": "text/plain", "Content-Length": "21"},
                "template render error",
            )
        except HMockError as exc:
            self.server.hm_logger.error("request handling error", error=str(exc), http_path=request.path)
            response = _error_response(500, str(exc))
        response = apply_cors(response, self.server.runtime_state.config.cors_enabled)
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if send_body:
            self.wfile.write(_response_body_bytes(response))
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
                "body": _response_body_log_value(response),
            },
        )


class HMockHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        behaviors: list[Behavior] | HMockRuntimeState,
        logger: JsonLogger | None = None,
        redis_store: RedisStore | None = None,
    ) -> None:
        super().__init__(address, MockHTTPRequestHandler)
        if isinstance(behaviors, HMockRuntimeState):
            self.runtime_state = behaviors
            self.hm_logger = behaviors.logger
        else:
            if logger is None:
                logger = JsonLogger("error")
            self.runtime_state = HMockRuntimeState(
                Config(templates_dir_hot_reload=False),
                logger,
                redis_store or MemoryRedisStore(),
                behaviors=list(behaviors),
                definitions=[],
            )
            self.hm_logger = logger


class HMockGRPCServer:
    def __init__(self, address: tuple[str, int], runtime_state: HMockRuntimeState) -> None:
        self.server_address = address
        self.runtime_state = runtime_state

    def serve_forever(self) -> None:
        raise ValidationError("gRPC network serving requires an HTTP/2 gRPC transport dependency")

    def shutdown(self) -> None:
        return

    def server_close(self) -> None:
        return


def build_server(config: Config | None = None, logger: JsonLogger | None = None) -> HMockHTTPServer:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    state = HMockRuntimeState.from_config(config, logger)
    return HMockHTTPServer((config.http_host, config.http_port), state)


def build_admin_server(
    config: Config | None = None,
    logger: JsonLogger | None = None,
    runtime_state: HMockRuntimeState | None = None,
) -> HMockAdminHTTPServer | None:
    config = config or load_config()
    if not config.admin_http_enabled:
        return None
    logger = logger or JsonLogger(config.log_level)
    state = runtime_state or HMockRuntimeState.from_config(config, logger)
    return HMockAdminHTTPServer((config.admin_http_host, config.admin_http_port), state)


def build_grpc_server(
    config: Config | None = None,
    logger: JsonLogger | None = None,
    runtime_state: HMockRuntimeState | None = None,
) -> HMockGRPCServer | None:
    config = config or load_config()
    if not config.grpc.enabled:
        return None
    logger = logger or JsonLogger(config.log_level)
    state = runtime_state or HMockRuntimeState.from_config(config, logger)
    return HMockGRPCServer((config.grpc.host, config.grpc.port), state)


def _admin_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _load_cli_definitions(directory: str | Path) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for path in discover_yaml_files(directory):
        for raw in load_mock_file(path):
            if not isinstance(raw, dict):
                raise ValidationError("definition must be a mapping")
            definitions.append(copy.deepcopy(raw))
    return definitions


def _omctl_request(url: str, method: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> int:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        return response.status


def _omctl_push(args: argparse.Namespace) -> int:
    definitions = _load_cli_definitions(args.directory)
    body = json.dumps(definitions, separators=(",", ":")).encode()
    path = (
        f"/api/v1/template_sets/{quote(args.set_key, safe='')}"
        if args.set_key
        else "/api/v1/templates"
    )
    status = _omctl_request(
        _admin_url(args.url, path),
        "POST",
        body,
        {"Content-Type": "application/yaml"},
    )
    return 0 if 200 <= status < 300 else 1


def _omctl_delete(args: argparse.Namespace) -> int:
    status = _omctl_request(
        _admin_url(args.url, f"/api/v1/template_sets/{quote(args.set_key, safe='')}"),
        "DELETE",
    )
    return 0 if status == 204 else 1


def build_omctl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push = subparsers.add_parser("push")
    push.add_argument("-d", "--directory", default="./demo_templates")
    push.add_argument("-u", "--url", default="http://localhost:9998")
    push.add_argument("-k", "--set-key", dest="set_key")
    push.set_defaults(func=_omctl_push)

    delete = subparsers.add_parser("delete")
    delete.add_argument("-u", "--url", default="http://localhost:9998")
    delete.add_argument("-k", "--set-key", dest="set_key", required=True)
    delete.set_defaults(func=_omctl_delete)
    return parser


def omctl_main(argv: list[str] | None = None) -> int:
    parser = build_omctl_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HMockError as exc:
        parser.exit(1, f"omctl: {exc}\n")
    except urllib.error.HTTPError as exc:
        parser.exit(1, f"omctl: HTTP {exc.code}\n")
    except urllib.error.URLError as exc:
        parser.exit(1, f"omctl: {exc.reason}\n")


def main() -> None:
    config = load_config()
    logger = JsonLogger(config.log_level)
    server = build_server(config, logger)
    admin_server = build_admin_server(config, logger, server.runtime_state)
    grpc_server = build_grpc_server(config, logger, server.runtime_state)
    broker_managers = build_broker_managers(server.runtime_state)
    admin_thread: threading.Thread | None = None
    grpc_thread: threading.Thread | None = None
    if admin_server is not None:
        admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        admin_thread.start()
        logger.info(
            "hmock admin server started",
            host=config.admin_http_host,
            port=config.admin_http_port,
        )
    if grpc_server is not None:
        grpc_thread = threading.Thread(target=grpc_server.serve_forever, daemon=True)
        grpc_thread.start()
        logger.info(
            "hmock grpc server started",
            host=config.grpc.host,
            port=config.grpc.port,
        )
    for manager in broker_managers:
        manager.start()
    logger.info("hmock server started", host=config.http_host, port=config.http_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("hmock server stopped")
    finally:
        for manager in broker_managers:
            manager.stop()
        if admin_server is not None:
            admin_server.shutdown()
            admin_server.server_close()
        if grpc_server is not None:
            grpc_server.shutdown()
            grpc_server.server_close()
        server.server_close()
        if admin_thread is not None:
            admin_thread.join(timeout=2)
        if grpc_thread is not None:
            grpc_thread.join(timeout=2)


if __name__ == "__main__":
    main()
