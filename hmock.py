from __future__ import annotations

import base64
import copy
import dataclasses
import argparse
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
class KafkaEndpointConfig:
    seed_brokers: str
    sasl_username: str
    sasl_password: str
    tls_enabled: bool

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


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _env_optional_bool(value: str | None) -> bool | None:
    if value is None or value == "":
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


def kafka_producer_config(config: Config) -> KafkaEndpointConfig:
    return KafkaEndpointConfig(
        seed_brokers=config.kafka_producer_seed_brokers or config.kafka_seed_brokers,
        sasl_username=config.kafka_sasl_producer_username or config.kafka_sasl_username,
        sasl_password=config.kafka_sasl_producer_password or config.kafka_sasl_password,
        tls_enabled=config.kafka_tls_enabled if config.kafka_tls_producer_enabled is None else config.kafka_tls_producer_enabled,
    )


def kafka_consumer_config(config: Config) -> KafkaEndpointConfig:
    return KafkaEndpointConfig(
        seed_brokers=config.kafka_consumer_seed_brokers or config.kafka_seed_brokers,
        sasl_username=config.kafka_sasl_consumer_username or config.kafka_sasl_username,
        sasl_password=config.kafka_sasl_consumer_password or config.kafka_sasl_password,
        tls_enabled=config.kafka_tls_enabled if config.kafka_tls_consumer_enabled is None else config.kafka_tls_consumer_enabled,
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
class KafkaExpectation:
    topic: str


@dataclasses.dataclass
class AMQPExpectation:
    exchange: str
    routing_key: str
    queue: str


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
    kafka: KafkaExpectation | None = None
    amqp: AMQPExpectation | None = None


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)", str(value))
    if not match:
        raise ValidationError(f"unsupported duration: {value}")
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
    return amount * factors[unit]


def _resolve_body_file(templates_dir: str | Path, body_from_file: str, field_name: str = "reply_http.body_from_file") -> str:
    root = Path(templates_dir).resolve()
    path = (root / body_from_file).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {body_from_file}")
    return path.read_text()


def _resolve_binary_body_file(templates_dir: str | Path, body_from_file: str, field_name: str) -> bytes:
    root = Path(templates_dir).resolve()
    path = (root / body_from_file).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {body_from_file}")
    return path.read_bytes()


def _validate_optional_string(value: Any, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ValidationError(f"{field_name} must be a non-empty string")


def _validate_headers_mapping(headers: Any, field_name: str) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a mapping")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")


def _validate_string_field(payload: dict[str, Any], field: str, field_name: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field_name} is required")
    return value


def _validate_optional_payload_string(payload: dict[str, Any], field: str, field_name: str) -> None:
    if field in payload and payload[field] is not None and not isinstance(payload[field], str):
        raise ValidationError(f"{field_name} must be a string")


def _validate_kafka_expectation(expect: dict[str, Any], key: str) -> KafkaExpectation | None:
    kafka = expect.get("kafka")
    if kafka is None:
        return None
    if not isinstance(kafka, dict):
        raise ValidationError(f"behavior {key} expect.kafka must be a mapping")
    return KafkaExpectation(_validate_string_field(kafka, "topic", f"behavior {key} expect.kafka.topic"))


def _validate_amqp_expectation(expect: dict[str, Any], key: str) -> AMQPExpectation | None:
    amqp = expect.get("amqp")
    if amqp is None:
        return None
    if not isinstance(amqp, dict):
        raise ValidationError(f"behavior {key} expect.amqp must be a mapping")
    exchange = _validate_string_field(amqp, "exchange", f"behavior {key} expect.amqp.exchange")
    routing_key = _validate_string_field(amqp, "routing_key", f"behavior {key} expect.amqp.routing_key")
    queue = amqp.get("queue")
    if queue is None or queue == "":
        queue = routing_key
    if not isinstance(queue, str):
        raise ValidationError(f"behavior {key} expect.amqp.queue must be a string")
    return AMQPExpectation(exchange, routing_key, queue)


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
            binary_file = payload.get("body_from_binary_file")
            if binary_file is not None:
                if not isinstance(binary_file, str) or not binary_file:
                    raise ValidationError(f"behavior {key} reply_http.body_from_binary_file must be a non-empty string")
                if templates_dir is not None:
                    payload["body_from_binary_file_content"] = _resolve_binary_body_file(
                        templates_dir,
                        binary_file,
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
            binary_file = payload.get("body_from_binary_file")
            if binary_file is not None:
                if not isinstance(binary_file, str) or not binary_file:
                    raise ValidationError(f"behavior {key} send_http.body_from_binary_file must be a non-empty string")
                if templates_dir is not None:
                    payload["send_http_body_from_binary_file_content"] = _resolve_binary_body_file(
                        templates_dir,
                        binary_file,
                        "send_http.body_from_binary_file",
                    )
            _validate_optional_string(payload.get("binary_file_name"), f"behavior {key} send_http.binary_file_name")
        elif name == "publish_kafka":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _validate_string_field(payload, "topic", f"behavior {key} publish_kafka.topic")
            _validate_optional_payload_string(payload, "payload", f"behavior {key} publish_kafka.payload")
            body_from_file = payload.get("payload_from_file")
            if body_from_file is not None:
                if not isinstance(body_from_file, str) or not body_from_file:
                    raise ValidationError(f"behavior {key} publish_kafka.payload_from_file must be a non-empty string")
                if templates_dir is not None:
                    payload["publish_kafka_payload_from_file_content"] = _resolve_body_file(
                        templates_dir,
                        body_from_file,
                        "publish_kafka.payload_from_file",
                    )
            if payload.get("payload") is None and body_from_file is None:
                raise ValidationError(f"behavior {key} publish_kafka requires payload or payload_from_file")
        elif name == "publish_amqp":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _validate_string_field(payload, "exchange", f"behavior {key} publish_amqp.exchange")
            _validate_string_field(payload, "routing_key", f"behavior {key} publish_amqp.routing_key")
            _validate_optional_payload_string(payload, "payload", f"behavior {key} publish_amqp.payload")
            body_from_file = payload.get("payload_from_file")
            if body_from_file is not None:
                if not isinstance(body_from_file, str) or not body_from_file:
                    raise ValidationError(f"behavior {key} publish_amqp.payload_from_file must be a non-empty string")
                if templates_dir is not None:
                    payload["publish_amqp_payload_from_file_content"] = _resolve_body_file(
                        templates_dir,
                        body_from_file,
                        "publish_amqp.payload_from_file",
                    )
            if payload.get("payload") is None and body_from_file is None:
                raise ValidationError(f"behavior {key} publish_amqp requires payload or payload_from_file")
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
    _validate_kafka_expectation(expect, key)
    _validate_amqp_expectation(expect, key)
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
    if http is not None and not isinstance(http, dict):
        raise ValidationError(f"behavior {key} expect.http must be a mapping")
    method = ""
    path = ""
    pattern: PathPattern | None = None
    if http is not None:
        method = http.get("method")
        path = http.get("path")
        if not isinstance(method, str) or not method:
            raise ValidationError(f"behavior {key} expect.http.method is required")
        if not isinstance(path, str) or not path:
            raise ValidationError(f"behavior {key} expect.http.path is required")
        method = method.upper()
        pattern = PathPattern.compile(path)
    kafka = _validate_kafka_expectation(expect, key)
    amqp = _validate_amqp_expectation(expect, key)
    if http is None and kafka is None and amqp is None:
        raise ValidationError(f"behavior {key} must define expect.http, expect.kafka, or expect.amqp")
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
        kafka=kafka,
        amqp=amqp,
    )


def load_mock_file(path: str | Path) -> list[Any]:
    parsed = parse_yaml_subset(Path(path).read_text())
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise ValidationError(f"{path} must contain a top-level list")
    return parsed


def _filesystem_definition_sources(templates_dir: str | Path) -> list[tuple[str, list[Any]]]:
    return [(str(path), load_mock_file(path)) for path in discover_yaml_files(templates_dir)]


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


def _build_behaviors_from_sources(
    sources: list[tuple[str, list[Any]]],
    templates_dir: str | Path,
    logger: JsonLogger | None = None,
) -> tuple[list[Behavior], list[dict[str, Any]]]:
    logger = logger or JsonLogger("error")
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source, definitions in sources:
        if not isinstance(definitions, list):
            raise ValidationError(f"{source} must contain a top-level list")
        for raw in definitions:
            key, kind = _definition_kind(raw)
            if kind == "AbstractBehavior":
                _validate_abstract_definition(raw)
            if key in raw_by_key:
                order.remove(key)
                logger.warn("duplicate mock key override", key=key, file=source)
            raw_by_key[key] = copy.deepcopy(raw)
            raw_by_key[key].setdefault("kind", "Behavior")
            order.append(key)

    active_definitions = [copy.deepcopy(raw_by_key[key]) for key in order]
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
    return behaviors, active_definitions


def load_behaviors(templates_dir: str | Path, logger: JsonLogger | None = None) -> list[Behavior]:
    behaviors, _ = _build_behaviors_from_sources(_filesystem_definition_sources(templates_dir), templates_dir, logger)
    return behaviors


INTERNAL_REDIS_PREFIX = "__hmock_internal:"
BASE_TEMPLATES_KEY = INTERNAL_REDIS_PREFIX + "templates"
TEMPLATE_SET_KEY_PREFIX = INTERNAL_REDIS_PREFIX + "template_sets:"


def _redis_arg(value: Any) -> str:
    return shlex.quote(str(value))


def _load_json_array_from_redis(redis_store: RedisStore, key: str) -> list[Any]:
    raw = redis_store.do(f"GET {_redis_arg(key)}")
    if raw == "":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid persisted mock definitions at {key}") from exc
    if not isinstance(parsed, list):
        raise ValidationError(f"persisted mock definitions at {key} must be an array")
    return parsed


def _store_json_array_in_redis(redis_store: RedisStore, key: str, definitions: list[Any]) -> None:
    payload = json.dumps(definitions, separators=(",", ":"))
    redis_store.do(f"SET {_redis_arg(key)} {_redis_arg(payload)}")


def _delete_redis_key(redis_store: RedisStore, key: str) -> None:
    redis_store.do(f"DEL {_redis_arg(key)}")


def _template_set_storage_key(set_key: str) -> str:
    return TEMPLATE_SET_KEY_PREFIX + set_key


def _load_base_api_definitions(redis_store: RedisStore) -> list[Any]:
    return _load_json_array_from_redis(redis_store, BASE_TEMPLATES_KEY)


def _load_template_sets(redis_store: RedisStore) -> dict[str, list[Any]]:
    keys_text = redis_store.do(f"KEYS {_redis_arg(TEMPLATE_SET_KEY_PREFIX + '*')}")
    if not keys_text:
        return {}
    sets: dict[str, list[Any]] = {}
    for key in sorted(part for part in keys_text.split(";;") if part):
        if not key.startswith(TEMPLATE_SET_KEY_PREFIX):
            continue
        sets[key[len(TEMPLATE_SET_KEY_PREFIX) :]] = _load_json_array_from_redis(redis_store, key)
    return sets


def _merge_upsert_definitions(existing: list[Any], submitted: list[Any]) -> list[Any]:
    by_key: dict[str, Any] = {}
    order: list[str] = []
    for raw in [*existing, *submitted]:
        key, _ = _definition_kind(raw)
        if key in by_key:
            order.remove(key)
        by_key[key] = copy.deepcopy(raw)
        order.append(key)
    return [by_key[key] for key in order]


def _remove_definition_by_key(definitions: list[Any], key: str) -> tuple[list[Any], bool]:
    removed = False
    kept: list[Any] = []
    for raw in definitions:
        raw_key, _ = _definition_kind(raw)
        if raw_key == key:
            removed = True
            continue
        kept.append(raw)
    return kept, removed


def _redis_command_key_args(parts: list[str]) -> list[str]:
    name = parts[0]
    args = parts[1:]
    if name in {"GET", "SET", "RPUSH", "LPUSH", "LRANGE", "LPOP", "RPOP", "HSET", "HGET", "HGETALL", "HDEL", "KEYS"}:
        return args[:1]
    if name in {"DEL", "EXISTS"}:
        return args
    return []


def _guard_internal_redis_keyspace(command: str) -> None:
    parts = _parse_redis_command(command)
    for key in _redis_command_key_args(parts):
        if key.startswith(INTERNAL_REDIS_PREFIX):
            raise RedisError(f"Redis key is reserved: {key}")


def guarded_redis_do(redis_store: RedisStore) -> Callable[[str], str]:
    def do(command: str) -> str:
        _guard_internal_redis_keyspace(command)
        return redis_store.do(command)

    return do


class HMockRuntimeState:
    def __init__(
        self,
        templates_dir: str | Path,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        initial_behaviors: list[Behavior] | None = None,
        initial_definitions: list[dict[str, Any]] | None = None,
        hot_reload: bool = True,
    ) -> None:
        self.templates_dir = str(templates_dir)
        self.logger = logger
        self.redis_store = redis_store or MemoryRedisStore()
        self.hot_reload = hot_reload
        self._fixed_behaviors = initial_behaviors is not None
        self._filesystem_signature: tuple[tuple[str, int, int], ...] = ()
        self._lock = threading.Lock()
        self._behaviors: list[Behavior] = list(initial_behaviors or [])
        self._definitions: list[dict[str, Any]] = copy.deepcopy(initial_definitions or [])
        if initial_behaviors is None:
            self.reload()

    def get_behaviors(self) -> list[Behavior]:
        if self.hot_reload and not self._fixed_behaviors:
            self._reload_if_filesystem_changed()
        with self._lock:
            return list(self._behaviors)

    def get_definitions(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._definitions)

    def redis_do(self, command: str) -> str:
        _guard_internal_redis_keyspace(command)
        return self.redis_store.do(command)

    def reload(self) -> None:
        behaviors, definitions = self._build_from_persistence()
        filesystem_signature = self._current_filesystem_signature()
        with self._lock:
            self._behaviors = behaviors
            self._definitions = definitions
            self._filesystem_signature = filesystem_signature

    def _current_filesystem_signature(self) -> tuple[tuple[str, int, int], ...]:
        root = Path(self.templates_dir).resolve()
        signature: list[tuple[str, int, int]] = []
        for path in discover_yaml_files(root):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            try:
                key = str(path.resolve().relative_to(root))
            except ValueError:
                key = str(path.resolve())
            signature.append((key, stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def _reload_if_filesystem_changed(self) -> None:
        filesystem_signature = self._current_filesystem_signature()
        with self._lock:
            if filesystem_signature == self._filesystem_signature:
                return
        behaviors, definitions = self._build_from_persistence()
        with self._lock:
            self._behaviors = behaviors
            self._definitions = definitions
            self._filesystem_signature = filesystem_signature

    def upsert_base_definitions(self, submitted: list[Any]) -> None:
        current_base = _load_base_api_definitions(self.redis_store)
        proposed_base = _merge_upsert_definitions(current_base, submitted)
        template_sets = _load_template_sets(self.redis_store)
        self._build_from_data(proposed_base, template_sets)
        _store_json_array_in_redis(self.redis_store, BASE_TEMPLATES_KEY, proposed_base)
        self.reload()

    def delete_all_base_definitions(self) -> None:
        template_sets = _load_template_sets(self.redis_store)
        self._build_from_data([], template_sets)
        _delete_redis_key(self.redis_store, BASE_TEMPLATES_KEY)
        self.reload()

    def delete_base_definition(self, key: str) -> bool:
        current_base = _load_base_api_definitions(self.redis_store)
        proposed_base, removed = _remove_definition_by_key(current_base, key)
        if not removed:
            return False
        template_sets = _load_template_sets(self.redis_store)
        self._build_from_data(proposed_base, template_sets)
        if proposed_base:
            _store_json_array_in_redis(self.redis_store, BASE_TEMPLATES_KEY, proposed_base)
        else:
            _delete_redis_key(self.redis_store, BASE_TEMPLATES_KEY)
        self.reload()
        return True

    def replace_template_set(self, set_key: str, definitions: list[Any]) -> None:
        base = _load_base_api_definitions(self.redis_store)
        template_sets = _load_template_sets(self.redis_store)
        template_sets[set_key] = copy.deepcopy(definitions)
        self._build_from_data(base, template_sets)
        _store_json_array_in_redis(self.redis_store, _template_set_storage_key(set_key), definitions)
        self.reload()

    def delete_template_set(self, set_key: str) -> None:
        base = _load_base_api_definitions(self.redis_store)
        template_sets = _load_template_sets(self.redis_store)
        template_sets.pop(set_key, None)
        self._build_from_data(base, template_sets)
        _delete_redis_key(self.redis_store, _template_set_storage_key(set_key))
        self.reload()

    def _build_from_persistence(self) -> tuple[list[Behavior], list[dict[str, Any]]]:
        return self._build_from_data(
            _load_base_api_definitions(self.redis_store),
            _load_template_sets(self.redis_store),
        )

    def _build_from_data(
        self,
        base_definitions: list[Any],
        template_sets: dict[str, list[Any]],
    ) -> tuple[list[Behavior], list[dict[str, Any]]]:
        sources = _filesystem_definition_sources(self.templates_dir)
        sources.append(("api:base", copy.deepcopy(base_definitions)))
        for set_key in sorted(template_sets):
            sources.append((f"api:template_set:{set_key}", copy.deepcopy(template_sets[set_key])))
        return _build_behaviors_from_sources(sources, self.templates_dir, self.logger)


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
class ResponseInfo:
    status_code: int
    headers: dict[str, str]
    body: str | bytes

    def body_bytes(self) -> bytes:
        if isinstance(self.body, bytes):
            return self.body
        return self.body.encode()

    def body_for_log(self) -> str:
        if isinstance(self.body, bytes):
            return f"<binary:{len(self.body)} bytes>"
        return self.body


def find_behavior(
    behaviors: list[Behavior],
    request: RequestInfo,
    redis_store: RedisStore | None = None,
) -> tuple[Behavior, dict[str, str]] | tuple[None, dict[str, str]]:
    redis_do = guarded_redis_do(redis_store) if redis_store is not None else None
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


def _empty_broker_request() -> RequestInfo:
    return RequestInfo("", "", "", "", "", {}, "")


def _condition_passes(
    behavior: Behavior,
    context: dict[str, Any],
    logger: JsonLogger | None = None,
) -> bool:
    if not behavior.condition:
        return True
    try:
        return render_template(behavior.condition, context) == "true"
    except TemplateError as exc:
        if logger is not None:
            logger.warn("broker condition render failed", key=behavior.key, error=str(exc))
        return False


def dispatch_kafka_message(
    behaviors: list[Behavior],
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_producer: Any | None = None,
    amqp_client: Any | None = None,
) -> int:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = guarded_redis_do(redis_store)
    matched = 0
    for behavior in behaviors:
        if behavior.kafka is None or behavior.kafka.topic != topic:
            continue
        extra_context = {"KafkaTopic": topic, "KafkaPayload": payload}
        context = build_template_context(
            {},
            "",
            "",
            "",
            {},
            redis_do,
            behavior.values,
            behavior.templates,
        )
        context.update(extra_context)
        if not _condition_passes(behavior, context, logger):
            continue
        execute_behavior(
            behavior,
            _empty_broker_request(),
            {},
            redis_store,
            logger,
            kafka_producer,
            amqp_client,
            extra_context,
        )
        matched += 1
    return matched


def dispatch_amqp_message(
    behaviors: list[Behavior],
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_producer: Any | None = None,
    amqp_client: Any | None = None,
) -> int:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = guarded_redis_do(redis_store)
    matched = 0
    for behavior in behaviors:
        if behavior.amqp is None:
            continue
        if (
            behavior.amqp.exchange != exchange
            or behavior.amqp.routing_key != routing_key
            or behavior.amqp.queue != queue
        ):
            continue
        extra_context = {
            "AMQPExchange": exchange,
            "AMQPRoutingKey": routing_key,
            "AMQPQueue": queue,
            "AMQPPayload": payload,
        }
        context = build_template_context(
            {},
            "",
            "",
            "",
            {},
            redis_do,
            behavior.values,
            behavior.templates,
        )
        context.update(extra_context)
        if not _condition_passes(behavior, context, logger):
            continue
        execute_behavior(
            behavior,
            _empty_broker_request(),
            {},
            redis_store,
            logger,
            kafka_producer,
            amqp_client,
            extra_context,
        )
        matched += 1
    return matched


def _pop_header_case_insensitive(headers: dict[str, str], name: str) -> str | None:
    for key in list(headers):
        if key.lower() == name.lower():
            return headers.pop(key)
    return None


def _multipart_file_body(filename: str, content_type: str, body: bytes) -> tuple[bytes, str]:
    boundary = f"hmock-{uuid.uuid4().hex}"
    safe_filename = filename.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        f"--{boundary}\r\n",
        f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n',
        f"Content-Type: {content_type}\r\n",
        "\r\n",
    ]
    payload = "".join(lines).encode() + body + f"\r\n--{boundary}--\r\n".encode()
    return payload, f"multipart/form-data; boundary={boundary}"


def _send_http(payload: dict[str, Any], context: dict[str, Any], logger: JsonLogger | None = None) -> None:
    url = render_template(str(payload["url"]), context)
    method = render_template(str(payload["method"]), context).upper()
    headers = {
        str(key): render_template(str(value), context)
        for key, value in (payload.get("headers") or {}).items()
    }
    data: bytes | None = None
    body_source = payload.get("body")
    if body_source is not None and body_source != "":
        data = render_template(str(body_source), context).encode()
    elif payload.get("send_http_body_from_binary_file_content") is not None:
        binary_body = bytes(payload["send_http_body_from_binary_file_content"])
        if method == "POST":
            filename = payload.get("binary_file_name") or posixpath.basename(str(payload.get("body_from_binary_file", "file")))
            part_content_type = _pop_header_case_insensitive(headers, "Content-Type") or "application/octet-stream"
            data, multipart_content_type = _multipart_file_body(filename, part_content_type, binary_body)
            headers["Content-Type"] = multipart_content_type
        else:
            data = binary_body
    else:
        file_body_source = payload.get("send_http_body_from_file_content")
        if file_body_source is not None:
            data = render_template(str(file_body_source), context).encode()
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
    except Exception as exc:
        if logger is not None:
            logger.warn("send_http request failed", url=url, method=method, error=str(exc))


def execute_behavior(
    behavior: Behavior,
    request: RequestInfo,
    params: dict[str, str],
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_producer: Any | None = None,
    amqp_client: Any | None = None,
    extra_context: dict[str, Any] | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = guarded_redis_do(redis_store)
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
    if extra_context:
        context.update(extra_context)
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
            if kafka_producer is not None:
                topic = render_template(str(payload["topic"]), context)
                payload_source = payload.get("payload")
                if payload_source is not None and payload_source != "":
                    rendered_payload = render_template(str(payload_source), context)
                else:
                    rendered_payload = render_template(str(payload.get("publish_kafka_payload_from_file_content", "")), context)
                try:
                    kafka_producer.publish(topic, rendered_payload)
                except Exception as exc:
                    if logger is not None:
                        logger.warn("publish_kafka failed", topic=topic, error=str(exc))
        elif name == "publish_amqp":
            if amqp_client is not None:
                exchange = render_template(str(payload["exchange"]), context)
                routing_key = render_template(str(payload["routing_key"]), context)
                payload_source = payload.get("payload")
                if payload_source is not None and payload_source != "":
                    rendered_payload = render_template(str(payload_source), context)
                else:
                    rendered_payload = render_template(str(payload.get("publish_amqp_payload_from_file_content", "")), context)
                try:
                    amqp_client.publish(exchange, routing_key, rendered_payload)
                except Exception as exc:
                    if logger is not None:
                        logger.warn("publish_amqp failed", exchange=exchange, routing_key=routing_key, error=str(exc))
        elif name == "reply_http":
            headers = {
                str(key): render_template(str(value), context)
                for key, value in (payload.get("headers") or {}).items()
            }
            body_source = payload.get("body")
            if body_source is not None and body_source != "":
                body: str | bytes = render_template(str(body_source), context)
            elif payload.get("body_from_binary_file_content") is not None:
                body = bytes(payload["body_from_binary_file_content"])
                binary_file_name = payload.get("binary_file_name")
                if binary_file_name:
                    headers["Content-Disposition"] = f'inline; filename="{binary_file_name}"'
            else:
                body_source = payload.get("body_from_file_content", "")
                body = render_template(str(body_source), context)
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "application/json"
            body_length = len(body) if isinstance(body, bytes) else len(body.encode())
            headers["Content-Length"] = str(body_length)
            response = ResponseInfo(int(payload["status_code"]), headers, body)
    return response or ResponseInfo(204, {"Content-Length": "0"}, "")


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


def preflight_response() -> ResponseInfo:
    return ResponseInfo(200, {"Content-Length": "0"}, "")


def apply_cors_headers(response: ResponseInfo, enabled: bool) -> ResponseInfo:
    if not enabled:
        return response
    headers = dict(response.headers)
    existing = {key.lower() for key in headers}
    for key, value in CORS_HEADERS.items():
        if key.lower() not in existing:
            headers[key] = value
            existing.add(key.lower())
    return ResponseInfo(response.status_code, headers, response.body)


def kafka_topics_for_behaviors(behaviors: list[Behavior]) -> list[str]:
    return sorted({behavior.kafka.topic for behavior in behaviors if behavior.kafka is not None})


def amqp_bindings_for_behaviors(behaviors: list[Behavior]) -> list[AMQPExpectation]:
    bindings: dict[tuple[str, str, str], AMQPExpectation] = {}
    for behavior in behaviors:
        if behavior.amqp is None:
            continue
        key = (behavior.amqp.exchange, behavior.amqp.routing_key, behavior.amqp.queue)
        bindings[key] = behavior.amqp
    return [bindings[key] for key in sorted(bindings)]


class KafkaClientAdapter:
    def __init__(self, config: Config) -> None:
        try:
            from kafka import KafkaConsumer, KafkaProducer
        except ImportError as exc:
            raise ValidationError("Kafka support requires kafka-python") from exc
        producer_config = kafka_producer_config(config)
        consumer_config = kafka_consumer_config(config)
        producer_kwargs: dict[str, Any] = {
            "bootstrap_servers": [part.strip() for part in producer_config.seed_brokers.split(",") if part.strip()],
            "client_id": config.kafka_client_id,
        }
        if producer_config.tls_enabled:
            producer_kwargs["security_protocol"] = "SASL_SSL" if producer_config.sasl_enabled else "SSL"
        elif producer_config.sasl_enabled:
            producer_kwargs["security_protocol"] = "SASL_PLAINTEXT"
        if producer_config.sasl_enabled:
            producer_kwargs["sasl_plain_username"] = producer_config.sasl_username
            producer_kwargs["sasl_plain_password"] = producer_config.sasl_password
        self._producer = KafkaProducer(**producer_kwargs)
        self._consumer_class = KafkaConsumer
        self._consumer_config = consumer_config
        self._client_id = config.kafka_client_id

    def publish(self, topic: str, payload: str) -> None:
        future = self._producer.send(topic, payload.encode())
        future.get(timeout=3)

    def consume(self, topics: list[str], stop_event: threading.Event, on_message: Callable[[str, str], None]) -> None:
        if not topics:
            return
        kwargs: dict[str, Any] = {
            "bootstrap_servers": [part.strip() for part in self._consumer_config.seed_brokers.split(",") if part.strip()],
            "client_id": self._client_id,
            "enable_auto_commit": True,
            "consumer_timeout_ms": 500,
        }
        if self._consumer_config.tls_enabled:
            kwargs["security_protocol"] = "SASL_SSL" if self._consumer_config.sasl_enabled else "SSL"
        elif self._consumer_config.sasl_enabled:
            kwargs["security_protocol"] = "SASL_PLAINTEXT"
        if self._consumer_config.sasl_enabled:
            kwargs["sasl_plain_username"] = self._consumer_config.sasl_username
            kwargs["sasl_plain_password"] = self._consumer_config.sasl_password
        consumer = self._consumer_class(*topics, **kwargs)
        try:
            while not stop_event.is_set():
                for message in consumer:
                    if stop_event.is_set():
                        break
                    value = message.value.decode() if isinstance(message.value, bytes) else str(message.value)
                    on_message(str(message.topic), value)
        finally:
            consumer.close()


class AMQPClientAdapter:
    def __init__(self, config: Config) -> None:
        try:
            import pika
        except ImportError as exc:
            raise ValidationError("AMQP support requires pika") from exc
        self._pika = pika
        self._url = config.amqp_url

    def _connection(self) -> Any:
        return self._pika.BlockingConnection(self._pika.URLParameters(self._url))

    def ensure_binding(self, exchange: str, routing_key: str, queue: str) -> None:
        connection = self._connection()
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=exchange, durable=True)
            channel.queue_declare(queue=queue, durable=True)
            channel.queue_bind(exchange=exchange, queue=queue, routing_key=routing_key)
        finally:
            connection.close()

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        connection = self._connection()
        try:
            channel = connection.channel()
            channel.basic_publish(exchange=exchange, routing_key=routing_key, body=payload.encode())
        finally:
            connection.close()

    def consume(
        self,
        bindings: list[AMQPExpectation],
        stop_event: threading.Event,
        on_message: Callable[[str, str, str, str], None],
    ) -> None:
        if not bindings:
            return
        connection = self._connection()
        try:
            channel = connection.channel()

            for binding in bindings:
                def callback(ch: Any, method: Any, _properties: Any, body: bytes, queue: str = binding.queue) -> None:
                    if stop_event.is_set():
                        return
                    on_message(str(method.exchange), str(method.routing_key), queue, body.decode())
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue=binding.queue, on_message_callback=callback)
            while not stop_event.is_set():
                connection.process_data_events(time_limit=0.5)
        finally:
            connection.close()


class BrokerWorker:
    def __init__(self, target: Callable[[threading.Event], None]) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=target, args=(self._stop_event,), daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)


def start_kafka_worker(
    state: HMockRuntimeState,
    adapter: Any,
    logger: JsonLogger,
    redis_store: RedisStore,
    amqp_client: Any | None = None,
) -> BrokerWorker | None:
    topics = kafka_topics_for_behaviors(state.get_behaviors())
    if not topics:
        return None

    def run(stop_event: threading.Event) -> None:
        def handle(topic: str, payload: str) -> None:
            dispatch_kafka_message(
                state.get_behaviors(),
                topic,
                payload,
                redis_store,
                logger,
                adapter,
                amqp_client,
            )

        adapter.consume(topics, stop_event, handle)

    worker = BrokerWorker(run)
    worker.start()
    return worker


def start_amqp_worker(
    state: HMockRuntimeState,
    adapter: Any,
    logger: JsonLogger,
    redis_store: RedisStore,
    kafka_producer: Any | None = None,
    reconnect_backoff: float = 0.1,
) -> BrokerWorker | None:
    bindings = amqp_bindings_for_behaviors(state.get_behaviors())
    if not bindings:
        return None
    for binding in bindings:
        adapter.ensure_binding(binding.exchange, binding.routing_key, binding.queue)

    def run(stop_event: threading.Event) -> None:
        def handle(exchange: str, routing_key: str, queue: str, payload: str) -> None:
            dispatch_amqp_message(
                state.get_behaviors(),
                exchange,
                routing_key,
                queue,
                payload,
                redis_store,
                logger,
                kafka_producer,
                adapter,
            )

        while not stop_event.is_set():
            current_bindings = amqp_bindings_for_behaviors(state.get_behaviors())
            for binding in current_bindings:
                adapter.ensure_binding(binding.exchange, binding.routing_key, binding.queue)
            try:
                adapter.consume(current_bindings, stop_event, handle)
            except Exception as exc:
                if stop_event.is_set():
                    break
                logger.warn("amqp consume failed; reconnecting", error=str(exc))
                stop_event.wait(reconnect_backoff)
            else:
                stop_event.wait(reconnect_backoff)

    worker = BrokerWorker(run)
    worker.start()
    return worker


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
        behavior, params = find_behavior(self.server.state.get_behaviors(), request, self.server.redis_store)
        try:
            if behavior:
                response = execute_behavior(
                    behavior,
                    request,
                    params,
                    self.server.redis_store,
                    self.server.hm_logger,
                    self.server.kafka_client,
                    self.server.amqp_client,
                )
            elif self.command == "OPTIONS" and self.server.cors_enabled:
                response = preflight_response()
            else:
                response = not_found_response()
        except TemplateError as exc:
            self.server.hm_logger.error("template render error", error=str(exc), http_path=request.path)
            response = ResponseInfo(
                500,
                {"Content-Type": "text/plain", "Content-Length": "21"},
                "template render error",
            )
        response = apply_cors_headers(response, self.server.cors_enabled)
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
                "body": response.body_for_log(),
            },
        )


class HMockHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        behaviors_or_state: list[Behavior] | HMockRuntimeState,
        logger: JsonLogger | None = None,
        redis_store: RedisStore | None = None,
        cors_enabled: bool = False,
        kafka_client: Any | None = None,
        amqp_client: Any | None = None,
        broker_workers: list[BrokerWorker] | None = None,
    ) -> None:
        super().__init__(address, MockHTTPRequestHandler)
        if isinstance(behaviors_or_state, HMockRuntimeState):
            self.state = behaviors_or_state
        else:
            if logger is None:
                logger = JsonLogger("error")
            self.state = HMockRuntimeState(
                "",
                logger,
                redis_store or MemoryRedisStore(),
                initial_behaviors=behaviors_or_state,
            )
        self.hm_logger = self.state.logger
        self.redis_store = self.state.redis_store
        self.cors_enabled = cors_enabled
        self.kafka_client = kafka_client
        self.amqp_client = amqp_client
        self.broker_workers = list(broker_workers or [])

    @property
    def behaviors(self) -> list[Behavior]:
        return self.state.get_behaviors()

    def server_close(self) -> None:
        for worker in self.broker_workers:
            worker.stop()
        for worker in self.broker_workers:
            worker.join(timeout=2)
        super().server_close()


def _json_response_bytes(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


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
        path = urlsplit(self.path).path
        try:
            if self.command == "GET" and path == "/api/v1/health":
                self._send_json(200, {"status": "OK"})
                return
            if self.command == "GET" and path == "/api/v1/templates":
                self._send_json(200, self.server.state.get_definitions())
                return
            if self.command == "POST" and path == "/api/v1/templates":
                submitted = self._read_definition_array()
                self.server.state.upsert_base_definitions(submitted)
                self._send_json(200, submitted)
                return
            if self.command == "DELETE" and path == "/api/v1/templates":
                self.server.state.delete_all_base_definitions()
                self._send_no_content()
                return
            template_prefix = "/api/v1/templates/"
            if self.command == "DELETE" and path.startswith(template_prefix):
                template_key = unquote(path[len(template_prefix) :])
                if not template_key or not self.server.state.delete_base_definition(template_key):
                    self._send_text(404, "not found")
                    return
                self._send_no_content()
                return
            set_prefix = "/api/v1/template_sets/"
            if path.startswith(set_prefix):
                set_key = unquote(path[len(set_prefix) :])
                if not set_key:
                    self._send_text(404, "not found")
                    return
                if self.command == "POST":
                    submitted = self._read_definition_array()
                    self.server.state.replace_template_set(set_key, submitted)
                    self._send_json(200, submitted)
                    return
                if self.command == "DELETE":
                    self.server.state.delete_template_set(set_key)
                    self._send_no_content()
                    return
            self._send_text(404, "not found")
        except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})

    def _read_definition_array(self) -> list[Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type in {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"}:
            return self._read_yaml_array()
        return self._read_json_array()

    def _read_json_array(self) -> list[Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        parsed = json.loads(body or "null")
        if not isinstance(parsed, list):
            raise ValidationError("request body must be a JSON array")
        return parsed

    def _read_yaml_array(self) -> list[Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        parsed = parse_yaml_subset(body)
        if parsed is None:
            parsed = []
        if not isinstance(parsed, list):
            raise ValidationError("request body must be a YAML array")
        return parsed

    def _send_json(self, status: int, payload: Any) -> None:
        body = _json_response_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, body_text: str) -> None:
        body = body_text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


class HMockAdminHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], state: HMockRuntimeState) -> None:
        super().__init__(address, AdminHTTPRequestHandler)
        self.state = state


def build_server(
    config: Config | None = None,
    logger: JsonLogger | None = None,
    kafka_client: Any | None = None,
    amqp_client: Any | None = None,
) -> HMockHTTPServer:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    redis_store = build_redis_store(config)
    state = HMockRuntimeState(
        config.templates_dir,
        logger,
        redis_store,
        hot_reload=config.templates_dir_hot_reload,
    )
    if config.kafka_enabled and kafka_client is None:
        kafka_client = KafkaClientAdapter(config)
    if config.amqp_enabled and amqp_client is None:
        amqp_client = AMQPClientAdapter(config)
    workers: list[BrokerWorker] = []
    if config.kafka_enabled and kafka_client is not None:
        worker = start_kafka_worker(state, kafka_client, logger, redis_store, amqp_client)
        if worker is not None:
            workers.append(worker)
    if config.amqp_enabled and amqp_client is not None:
        worker = start_amqp_worker(state, amqp_client, logger, redis_store, kafka_client)
        if worker is not None:
            workers.append(worker)
    return HMockHTTPServer(
        (config.http_host, config.http_port),
        state,
        cors_enabled=config.cors_enabled,
        kafka_client=kafka_client,
        amqp_client=amqp_client,
        broker_workers=workers,
    )


def build_admin_server(
    config: Config,
    state: HMockRuntimeState,
) -> HMockAdminHTTPServer | None:
    if not config.admin_http_enabled:
        return None
    return HMockAdminHTTPServer((config.admin_http_host, config.admin_http_port), state)


def _omctl_yaml_payload(directory: str | Path) -> bytes:
    parts: list[str] = []
    for path in discover_yaml_files(directory):
        text = path.read_text().strip()
        if text:
            parts.append(text)
    if not parts:
        return b"[]\n"
    return ("\n".join(parts) + "\n").encode()


def _admin_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _urlopen_expect(request: urllib.request.Request, expected_status: int) -> None:
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
            if response.status != expected_status:
                raise SystemExit(f"unexpected response status: {response.status}")
    except urllib.error.HTTPError as exc:
        exc.read()
        raise SystemExit(f"unexpected response status: {exc.code}") from exc


def omctl_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("--directory", "-d", default="./demo_templates")
    push_parser.add_argument("--url", "-u", default="http://localhost:9998")
    push_parser.add_argument("--set-key", "-k")

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("--url", "-u", default="http://localhost:9998")
    delete_parser.add_argument("--set-key", "-k", required=True)

    args = parser.parse_args(argv)
    if args.command == "push":
        payload = _omctl_yaml_payload(args.directory)
        path = f"/api/v1/template_sets/{quote(args.set_key, safe='')}" if args.set_key else "/api/v1/templates"
        request = urllib.request.Request(
            _admin_url(args.url, path),
            data=payload,
            method="POST",
            headers={"Content-Type": "application/yaml"},
        )
        _urlopen_expect(request, 200)
        return 0
    if args.command == "delete":
        request = urllib.request.Request(
            _admin_url(args.url, f"/api/v1/template_sets/{quote(args.set_key, safe='')}"),
            method="DELETE",
        )
        _urlopen_expect(request, 204)
        return 0
    parser.error("unsupported command")
    return 2


def main() -> None:
    config = load_config()
    logger = JsonLogger(config.log_level)
    server = build_server(config, logger)
    admin_server = build_admin_server(config, server.state)
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
