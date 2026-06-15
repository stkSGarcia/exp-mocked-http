from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import html as html_lib
import hmac
import importlib.util
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
from concurrent.futures import ThreadPoolExecutor
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


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_bool_optional(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return _env_bool(value, False)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
    kafka_producer_seed_brokers: str | None = None
    kafka_consumer_seed_brokers: str | None = None
    kafka_sasl_producer_username: str | None = None
    kafka_sasl_producer_password: str | None = None
    kafka_sasl_consumer_username: str | None = None
    kafka_sasl_consumer_password: str | None = None
    kafka_tls_producer_enabled: bool | None = None
    kafka_tls_consumer_enabled: bool | None = None
    amqp_enabled: bool = False
    amqp_url: str = "amqp://guest:guest@rabbitmq:5672"
    grpc_enabled: bool = False
    grpc_port: int = 50051
    grpc_host: str = "0.0.0.0"
    grpc_descriptor_set_paths: str = ""


@dataclasses.dataclass(frozen=True)
class KafkaEndpointConfig:
    client_id: str
    seed_brokers: list[str]
    sasl_username: str
    sasl_password: str
    tls_enabled: bool

    @property
    def sasl_enabled(self) -> bool:
        return bool(self.sasl_username and self.sasl_password)


def resolve_kafka_endpoint_config(config: Config, endpoint: str) -> KafkaEndpointConfig:
    if endpoint not in {"producer", "consumer"}:
        raise ValidationError(f"unsupported Kafka endpoint: {endpoint}")
    if endpoint == "producer":
        seed_brokers = config.kafka_producer_seed_brokers or config.kafka_seed_brokers
        username = (
            config.kafka_sasl_producer_username
            if config.kafka_sasl_producer_username is not None
            else config.kafka_sasl_username
        )
        password = (
            config.kafka_sasl_producer_password
            if config.kafka_sasl_producer_password is not None
            else config.kafka_sasl_password
        )
        tls_enabled = (
            config.kafka_tls_producer_enabled
            if config.kafka_tls_producer_enabled is not None
            else config.kafka_tls_enabled
        )
    else:
        seed_brokers = config.kafka_consumer_seed_brokers or config.kafka_seed_brokers
        username = (
            config.kafka_sasl_consumer_username
            if config.kafka_sasl_consumer_username is not None
            else config.kafka_sasl_username
        )
        password = (
            config.kafka_sasl_consumer_password
            if config.kafka_sasl_consumer_password is not None
            else config.kafka_sasl_password
        )
        tls_enabled = (
            config.kafka_tls_consumer_enabled
            if config.kafka_tls_consumer_enabled is not None
            else config.kafka_tls_enabled
        )
    return KafkaEndpointConfig(
        client_id=config.kafka_client_id,
        seed_brokers=_split_csv(seed_brokers),
        sasl_username=username or "",
        sasl_password=password or "",
        tls_enabled=bool(tls_enabled),
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
        kafka_seed_brokers=env.get("HM_KAFKA_SEED_BROKERS", "kafka:9092"),
        kafka_sasl_username=env.get("HM_KAFKA_SASL_USERNAME", ""),
        kafka_sasl_password=env.get("HM_KAFKA_SASL_PASSWORD", ""),
        kafka_tls_enabled=_env_bool(env.get("HM_KAFKA_TLS_ENABLED"), False),
        kafka_producer_seed_brokers=env.get("HM_KAFKA_PRODUCER_SEED_BROKERS"),
        kafka_consumer_seed_brokers=env.get("HM_KAFKA_CONSUMER_SEED_BROKERS"),
        kafka_sasl_producer_username=env.get("HM_KAFKA_SASL_PRODUCER_USERNAME"),
        kafka_sasl_producer_password=env.get("HM_KAFKA_SASL_PRODUCER_PASSWORD"),
        kafka_sasl_consumer_username=env.get("HM_KAFKA_SASL_CONSUMER_USERNAME"),
        kafka_sasl_consumer_password=env.get("HM_KAFKA_SASL_CONSUMER_PASSWORD"),
        kafka_tls_producer_enabled=_env_bool_optional(env.get("HM_KAFKA_TLS_PRODUCER_ENABLED")),
        kafka_tls_consumer_enabled=_env_bool_optional(env.get("HM_KAFKA_TLS_CONSUMER_ENABLED")),
        amqp_enabled=_env_bool(env.get("HM_AMQP_ENABLED"), False),
        amqp_url=env.get("HM_AMQP_URL", "amqp://guest:guest@rabbitmq:5672"),
        grpc_enabled=_env_bool(env.get("HM_GRPC_ENABLED"), False),
        grpc_port=int(env.get("HM_GRPC_PORT", "50051")),
        grpc_host=env.get("HM_GRPC_HOST", "0.0.0.0"),
        grpc_descriptor_set_paths=env.get("HM_GRPC_DESCRIPTOR_SET_PATHS", ""),
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


INTERNAL_REDIS_PREFIX = "__hmock_internal:"
BASE_TEMPLATES_KEY = "__hmock_internal:templates"
TEMPLATE_SET_KEY_PREFIX = "__hmock_internal:template_sets:"
TEMPLATE_SET_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _redis_key_args(parts: list[str]) -> list[str]:
    name = parts[0]
    args = parts[1:]
    if name in {"GET", "SET", "RPUSH", "LPUSH", "LRANGE", "LPOP", "RPOP", "HSET", "HGET", "HGETALL", "HDEL", "KEYS"}:
        return args[:1]
    if name in {"DEL", "EXISTS"}:
        return args
    return []


def _assert_redis_command_allowed(command: str) -> None:
    parts = _parse_redis_command(command)
    for key in _redis_key_args(parts):
        if fnmatch(key, f"{INTERNAL_REDIS_PREFIX}*") or key.startswith(INTERNAL_REDIS_PREFIX):
            raise RedisError(f"Redis key is reserved for hmock internals: {key}")


def guarded_redis_do(redis_store: RedisStore) -> Callable[[str], str]:
    def do(command: str) -> str:
        _assert_redis_command_allowed(command)
        return redis_store.do(command)

    return do


def _redis_get(redis_store: RedisStore, key: str) -> str:
    return redis_store.do(f"GET {key}")


def _redis_set(redis_store: RedisStore, key: str, value: str) -> None:
    redis_store.do(f"SET {key} {shlex.quote(value)}")


def _redis_del(redis_store: RedisStore, *keys: str) -> None:
    if keys:
        redis_store.do("DEL " + " ".join(keys))


def _decode_definition_array(value: str, storage_key: str) -> list[dict[str, Any]]:
    if value == "":
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{storage_key} does not contain valid JSON") from exc
    if not isinstance(parsed, list):
        raise ValidationError(f"{storage_key} must contain a JSON array")
    definitions: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValidationError(f"{storage_key} must contain mock definition objects")
        definitions.append(copy.deepcopy(item))
    return definitions


def _encode_definition_array(definitions: list[dict[str, Any]]) -> str:
    return json.dumps(definitions, separators=(",", ":"))


def _validate_definition_array(definitions: Any) -> list[dict[str, Any]]:
    if not isinstance(definitions, list):
        raise ValidationError("request body must be a JSON array")
    validated: list[dict[str, Any]] = []
    for item in definitions:
        if not isinstance(item, dict):
            raise ValidationError("request body must contain mock definition objects")
        _definition_kind(item)
        validated.append(copy.deepcopy(item))
    return validated


def load_base_api_definitions(redis_store: RedisStore) -> list[dict[str, Any]]:
    return _decode_definition_array(_redis_get(redis_store, BASE_TEMPLATES_KEY), BASE_TEMPLATES_KEY)


def save_base_api_definitions(redis_store: RedisStore, definitions: list[dict[str, Any]]) -> None:
    if definitions:
        _redis_set(redis_store, BASE_TEMPLATES_KEY, _encode_definition_array(definitions))
    else:
        _redis_del(redis_store, BASE_TEMPLATES_KEY)


def validate_template_set_key(set_key: str) -> str:
    if not set_key or not TEMPLATE_SET_KEY_RE.fullmatch(set_key):
        raise ValidationError("template set key must contain only letters, numbers, dot, underscore, or dash")
    return set_key


def template_set_storage_key(set_key: str) -> str:
    return TEMPLATE_SET_KEY_PREFIX + validate_template_set_key(set_key)


def list_template_set_keys(redis_store: RedisStore) -> list[str]:
    result = redis_store.do(f"KEYS {TEMPLATE_SET_KEY_PREFIX}*")
    if result == "":
        return []
    keys = result.split(";;")
    return sorted(key.removeprefix(TEMPLATE_SET_KEY_PREFIX) for key in keys if key.startswith(TEMPLATE_SET_KEY_PREFIX))


def load_template_sets(redis_store: RedisStore) -> dict[str, list[dict[str, Any]]]:
    sets: dict[str, list[dict[str, Any]]] = {}
    for set_key in list_template_set_keys(redis_store):
        storage_key = template_set_storage_key(set_key)
        sets[set_key] = _decode_definition_array(_redis_get(redis_store, storage_key), storage_key)
    return sets


def save_template_set(redis_store: RedisStore, set_key: str, definitions: list[dict[str, Any]]) -> None:
    _redis_set(redis_store, template_set_storage_key(set_key), _encode_definition_array(definitions))


def delete_template_set(redis_store: RedisStore, set_key: str) -> None:
    _redis_del(redis_store, template_set_storage_key(set_key))


def _collapse_definitions_by_key(definitions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in definitions:
        key, _ = _definition_kind(raw)
        if key in raw_by_key:
            order.remove(key)
        copied = copy.deepcopy(raw)
        copied.setdefault("kind", "Behavior")
        raw_by_key[key] = copied
        order.append(key)
    return [raw_by_key[key] for key in order]


def upsert_definitions(
    current: list[dict[str, Any]],
    submitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _collapse_definitions_by_key([*current, *submitted])


def persisted_definition_sources(
    base_definitions: list[dict[str, Any]],
    template_sets: dict[str, list[dict[str, Any]]],
) -> list[tuple[dict[str, Any], str]]:
    sources: list[tuple[dict[str, Any], str]] = [
        (definition, "api:base") for definition in base_definitions
    ]
    for set_key in sorted(template_sets):
        sources.extend((definition, f"api:template_set:{set_key}") for definition in template_sets[set_key])
    return sources


def build_collection_from_persisted(
    templates_dir: str | Path,
    logger: JsonLogger,
    base_definitions: list[dict[str, Any]],
    template_sets: dict[str, list[dict[str, Any]]],
    filesystem_definitions: Iterable[tuple[dict[str, Any], str]] | None = None,
) -> MockCollection:
    return load_mock_collection(
        templates_dir,
        logger,
        persisted_definition_sources(base_definitions, template_sets),
        filesystem_definitions,
    )


def load_persisted_mock_collection(
    templates_dir: str | Path,
    redis_store: RedisStore,
    logger: JsonLogger,
    filesystem_definitions: Iterable[tuple[dict[str, Any], str]] | None = None,
) -> MockCollection:
    return build_collection_from_persisted(
        templates_dir,
        logger,
        load_base_api_definitions(redis_store),
        load_template_sets(redis_store),
        filesystem_definitions,
    )


TemplatesFingerprint = tuple[tuple[str, int, int], ...]


def templates_directory_fingerprint(templates_dir: str | Path) -> TemplatesFingerprint:
    root = Path(templates_dir).resolve()
    entries: list[tuple[str, int, int]] = []
    for path in discover_yaml_files(root):
        stat = path.stat()
        try:
            relative = str(path.resolve().relative_to(root))
        except ValueError:
            relative = str(path.resolve())
        entries.append((relative, stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


class TemplatesReloadCoordinator:
    def __init__(
        self,
        templates_dir: str | Path,
        state: MockState,
        redis_store: RedisStore,
        logger: JsonLogger,
    ) -> None:
        self.templates_dir = templates_dir
        self.state = state
        self.redis_store = redis_store
        self.logger = logger
        self._lock = threading.Lock()
        self._fingerprint = templates_directory_fingerprint(templates_dir)

    def refresh_if_needed(self) -> None:
        fingerprint = templates_directory_fingerprint(self.templates_dir)
        if fingerprint == self._fingerprint:
            return
        with self._lock:
            fingerprint = templates_directory_fingerprint(self.templates_dir)
            if fingerprint == self._fingerprint:
                return
            try:
                collection = load_persisted_mock_collection(
                    self.templates_dir,
                    self.redis_store,
                    self.logger,
                )
            except HMockError as exc:
                self.logger.error("templates hot reload failed", error=str(exc))
                return
            self.state.replace(collection)
            self._fingerprint = fingerprint


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
    trigger: str
    condition: str
    actions: list[dict[str, Any]]
    values: dict[str, Any]
    templates: dict[str, str]
    method: str = ""
    path: str = ""
    pattern: PathPattern | None = None
    kafka_topic: str = ""
    amqp_exchange: str = ""
    amqp_routing_key: str = ""
    amqp_queue: str = ""
    grpc_service: str = ""
    grpc_method: str = ""


@dataclasses.dataclass
class MockCollection:
    raw_definitions: list[dict[str, Any]]
    behaviors: list[Behavior]
    filesystem_definitions: list[tuple[dict[str, Any], str]] = dataclasses.field(default_factory=list)


class MockState:
    def __init__(
        self,
        behaviors: list[Behavior] | None = None,
        raw_definitions: list[dict[str, Any]] | None = None,
        filesystem_definitions: list[tuple[dict[str, Any], str]] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._behaviors = list(behaviors or [])
        self._raw_definitions = copy.deepcopy(raw_definitions or [])
        self._filesystem_definitions = [
            (copy.deepcopy(raw), source) for raw, source in filesystem_definitions or []
        ]

    def behavior_snapshot(self) -> list[Behavior]:
        with self._lock:
            return list(self._behaviors)

    def raw_definition_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._raw_definitions)

    def filesystem_definition_snapshot(self) -> list[tuple[dict[str, Any], str]]:
        with self._lock:
            return [(copy.deepcopy(raw), source) for raw, source in self._filesystem_definitions]

    def replace(self, collection: MockCollection) -> None:
        with self._lock:
            self._behaviors = list(collection.behaviors)
            self._raw_definitions = copy.deepcopy(collection.raw_definitions)
            self._filesystem_definitions = [
                (copy.deepcopy(raw), source) for raw, source in collection.filesystem_definitions
            ]


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


def _resolve_binary_file(
    templates_dir: str | Path,
    body_from_binary_file: str,
    field_name: str,
) -> tuple[bytes, str]:
    root = Path(templates_dir).resolve()
    path = (root / body_from_binary_file).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must stay within templates directory") from exc
    if not path.is_file():
        raise ValidationError(f"{field_name} not found: {body_from_binary_file}")
    return path.read_bytes(), path.name


def _validate_headers_mapping(headers: Any, field_name: str) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise ValidationError(f"{field_name} must be a mapping")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string map")


def _require_string_field(payload: dict[str, Any], field_name: str, error_prefix: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{error_prefix}.{field_name} is required")
    return value


def _validate_text_payload_source(
    payload: dict[str, Any],
    action_name: str,
    key: str,
    templates_dir: str | Path | None,
    content_field: str,
) -> None:
    if "payload" in payload and payload["payload"] is not None and not isinstance(payload["payload"], str):
        raise ValidationError(f"behavior {key} {action_name}.payload must be a string")
    payload_from_file = payload.get("payload_from_file")
    has_inline = isinstance(payload.get("payload"), str)
    if payload_from_file is not None:
        if not isinstance(payload_from_file, str) or not payload_from_file:
            raise ValidationError(f"behavior {key} {action_name}.payload_from_file must be a non-empty string")
        if templates_dir is not None:
            payload[content_field] = _resolve_body_file(
                templates_dir,
                payload_from_file,
                f"{action_name}.payload_from_file",
            )
    if not has_inline and payload_from_file is None:
        raise ValidationError(f"behavior {key} {action_name} payload or payload_from_file is required")


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
                    payload["body_from_binary_file_content"], payload["binary_source_file_name"] = _resolve_binary_file(
                        templates_dir,
                        body_from_binary_file,
                        "reply_http.body_from_binary_file",
                    )
            if "binary_file_name" in payload and payload["binary_file_name"] is not None and not isinstance(payload["binary_file_name"], str):
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
                    payload["send_http_body_from_binary_file_content"], payload["binary_source_file_name"] = _resolve_binary_file(
                        templates_dir,
                        body_from_binary_file,
                        "send_http.body_from_binary_file",
                    )
            if "binary_file_name" in payload and payload["binary_file_name"] is not None and not isinstance(payload["binary_file_name"], str):
                raise ValidationError(f"behavior {key} send_http.binary_file_name must be a string")
        elif name == "publish_kafka":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _require_string_field(payload, "topic", f"behavior {key} publish_kafka")
            _validate_text_payload_source(
                payload,
                "publish_kafka",
                key,
                templates_dir,
                "kafka_payload_from_file_content",
            )
        elif name == "publish_amqp":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _require_string_field(payload, "exchange", f"behavior {key} publish_amqp")
            _require_string_field(payload, "routing_key", f"behavior {key} publish_amqp")
            _validate_text_payload_source(
                payload,
                "publish_amqp",
                key,
                templates_dir,
                "amqp_payload_from_file_content",
            )
        elif name == "reply_grpc":
            if not isinstance(payload, dict):
                raise ValidationError(f"behavior {key} action {name} payload must be a mapping")
            _validate_headers_mapping(payload.get("headers", {}), f"behavior {key} reply_grpc.headers")
            _validate_text_payload_source(
                payload,
                "reply_grpc",
                key,
                templates_dir,
                "grpc_payload_from_file_content",
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
    kafka = expect.get("kafka", {})
    if kafka is not None and not isinstance(kafka, dict):
        raise ValidationError(f"behavior {key} expect.kafka must be a mapping")
    amqp = expect.get("amqp", {})
    if amqp is not None and not isinstance(amqp, dict):
        raise ValidationError(f"behavior {key} expect.amqp must be a mapping")
    grpc = expect.get("grpc", {})
    if grpc is not None and not isinstance(grpc, dict):
        raise ValidationError(f"behavior {key} expect.grpc must be a mapping")
    _validate_actions(raw.get("actions", []), key, templates_dir)


def _expect_trigger(expect: dict[str, Any], key: str) -> str:
    triggers = [name for name in ("http", "kafka", "amqp", "grpc") if name in expect and expect.get(name) is not None]
    if not triggers:
        raise ValidationError(f"behavior {key} expect.http.method is required")
    if len(triggers) != 1:
        raise ValidationError(f"behavior {key} must define exactly one expect trigger")
    return triggers[0]


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
    trigger = _expect_trigger(expect, key)
    method = ""
    path = ""
    pattern: PathPattern | None = None
    kafka_topic = ""
    amqp_exchange = ""
    amqp_routing_key = ""
    amqp_queue = ""
    grpc_service = ""
    grpc_method = ""
    if trigger == "http":
        http = expect.get("http", {})
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
        pattern = PathPattern.compile(path_value)
    elif trigger == "kafka":
        kafka = expect.get("kafka", {})
        if not isinstance(kafka, dict):
            raise ValidationError(f"behavior {key} expect.kafka must be a mapping")
        topic = kafka.get("topic")
        if not isinstance(topic, str) or not topic:
            raise ValidationError(f"behavior {key} expect.kafka.topic is required")
        kafka_topic = topic
    elif trigger == "amqp":
        amqp = expect.get("amqp", {})
        if not isinstance(amqp, dict):
            raise ValidationError(f"behavior {key} expect.amqp must be a mapping")
        exchange = amqp.get("exchange")
        routing_key = amqp.get("routing_key")
        queue = amqp.get("queue")
        if not isinstance(exchange, str) or not exchange:
            raise ValidationError(f"behavior {key} expect.amqp.exchange is required")
        if not isinstance(routing_key, str) or not routing_key:
            raise ValidationError(f"behavior {key} expect.amqp.routing_key is required")
        if queue is not None and not isinstance(queue, str):
            raise ValidationError(f"behavior {key} expect.amqp.queue must be a string")
        amqp_exchange = exchange
        amqp_routing_key = routing_key
        amqp_queue = queue or routing_key
    elif trigger == "grpc":
        grpc = expect.get("grpc", {})
        if not isinstance(grpc, dict):
            raise ValidationError(f"behavior {key} expect.grpc must be a mapping")
        service = grpc.get("service")
        method_value = grpc.get("method")
        if not isinstance(service, str) or not service:
            raise ValidationError(f"behavior {key} expect.grpc.service is required")
        if not isinstance(method_value, str) or not method_value:
            raise ValidationError(f"behavior {key} expect.grpc.method is required")
        grpc_service = service
        grpc_method = method_value
    return Behavior(
        key=key,
        kind=kind,
        trigger=trigger,
        condition=condition,
        actions=sorted_actions,
        values=dict(values),
        templates=dict(templates or {}),
        method=method,
        path=path,
        pattern=pattern,
        kafka_topic=kafka_topic,
        amqp_exchange=amqp_exchange,
        amqp_routing_key=amqp_routing_key,
        amqp_queue=amqp_queue,
        grpc_service=grpc_service,
        grpc_method=grpc_method,
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


def _build_mock_collection(
    raw_items: Iterable[tuple[Any, str]],
    templates_dir: str | Path,
    logger: JsonLogger | None = None,
    filesystem_definitions: list[tuple[dict[str, Any], str]] | None = None,
) -> MockCollection:
    logger = logger or JsonLogger("error")
    raw_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw, source in raw_items:
        key, kind = _definition_kind(raw)
        if kind == "AbstractBehavior":
            _validate_abstract_definition(raw)
        if key in raw_by_key:
            order.remove(key)
            logger.warn("duplicate mock key override", key=key, source=source)
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
    return MockCollection(
        raw_definitions=[copy.deepcopy(raw_by_key[key]) for key in order],
        behaviors=behaviors,
        filesystem_definitions=[
            (copy.deepcopy(raw), source) for raw, source in filesystem_definitions or []
        ],
    )


def load_filesystem_definitions(templates_dir: str | Path) -> list[tuple[dict[str, Any], str]]:
    raw_items: list[tuple[dict[str, Any], str]] = []
    for path in discover_yaml_files(templates_dir):
        for raw in load_mock_file(path):
            if not isinstance(raw, dict):
                raise ValidationError("definition must be a mapping")
            raw_items.append((copy.deepcopy(raw), str(path)))
    return raw_items


def load_mock_collection(
    templates_dir: str | Path,
    logger: JsonLogger | None = None,
    extra_definitions: Iterable[tuple[Any, str]] | None = None,
    filesystem_definitions: Iterable[tuple[dict[str, Any], str]] | None = None,
) -> MockCollection:
    fs_definitions = (
        [(copy.deepcopy(raw), source) for raw, source in filesystem_definitions]
        if filesystem_definitions is not None
        else load_filesystem_definitions(templates_dir)
    )
    raw_items: list[tuple[Any, str]] = [(copy.deepcopy(raw), source) for raw, source in fs_definitions]
    if extra_definitions is not None:
        raw_items.extend(extra_definitions)
    return _build_mock_collection(raw_items, templates_dir, logger, fs_definitions)


def load_behaviors(templates_dir: str | Path, logger: JsonLogger | None = None) -> list[Behavior]:
    return load_mock_collection(templates_dir, logger).behaviors


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


def _build_base_context(
    redis_do: Callable[[str], str] | None = None,
    values: dict[str, Any] | None = None,
    templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"Values": dict(values or {})}
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
    context = _build_base_context(redis_do, values, templates)
    context.update({"KafkaTopic": topic, "KafkaPayload": payload})
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
    context = _build_base_context(redis_do, values, templates)
    context.update(
        {
            "AMQPExchange": exchange,
            "AMQPRoutingKey": routing_key,
            "AMQPQueue": queue,
            "AMQPPayload": payload,
        }
    )
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
    context = _build_base_context(redis_do, values, templates)
    context.update(
        {
            "GRPCService": service,
            "GRPCMethod": method,
            "GRPCPayload": payload,
            "GRPCHeader": HeaderMap(headers),
        }
    )
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


@dataclasses.dataclass(frozen=True)
class ProtoField:
    name: str
    number: int
    label: int
    field_type: int
    type_name: str = ""


@dataclasses.dataclass(frozen=True)
class ProtoMessage:
    full_name: str
    fields: dict[int, ProtoField]
    fields_by_name: dict[str, ProtoField]


@dataclasses.dataclass(frozen=True)
class ProtoMethod:
    service: str
    name: str
    input_type: str
    output_type: str


class ProtoDescriptorSet:
    def __init__(self, messages: dict[str, ProtoMessage], methods: dict[tuple[str, str], ProtoMethod]) -> None:
        self.messages = messages
        self.methods = methods

    def method(self, service: str, method: str) -> ProtoMethod:
        try:
            return self.methods[(service, method)]
        except KeyError as exc:
            raise ValidationError(f"gRPC descriptor missing method {service}/{method}") from exc

    def message(self, name: str) -> ProtoMessage:
        normalized = _normalize_proto_type_name(name)
        try:
            return self.messages[normalized]
        except KeyError as exc:
            raise ValidationError(f"gRPC descriptor missing message {normalized}") from exc


PROTO_LABEL_REPEATED = 3
PROTO_TYPE_DOUBLE = 1
PROTO_TYPE_FLOAT = 2
PROTO_TYPE_INT64 = 3
PROTO_TYPE_UINT64 = 4
PROTO_TYPE_INT32 = 5
PROTO_TYPE_FIXED64 = 6
PROTO_TYPE_FIXED32 = 7
PROTO_TYPE_BOOL = 8
PROTO_TYPE_STRING = 9
PROTO_TYPE_MESSAGE = 11
PROTO_TYPE_BYTES = 12
PROTO_TYPE_UINT32 = 13
PROTO_TYPE_SFIXED32 = 15
PROTO_TYPE_SFIXED64 = 16
PROTO_TYPE_SINT32 = 17
PROTO_TYPE_SINT64 = 18


def _normalize_proto_type_name(name: str) -> str:
    return name[1:] if name.startswith(".") else name


def resolve_grpc_descriptor_paths(templates_dir: str | Path, descriptor_paths: str) -> list[Path]:
    root = Path(templates_dir).resolve()
    paths: list[Path] = []
    for item in _split_csv(descriptor_paths):
        path = Path(item)
        paths.append(path if path.is_absolute() else root / path)
    return paths


def behavior_needs_grpc_descriptors(behaviors: Iterable[Behavior]) -> bool:
    return any(
        behavior.trigger == "grpc"
        or any(_action_name_payload(action, behavior.key)[0] == "reply_grpc" for action in behavior.actions)
        for behavior in behaviors
    )


def _read_varint(data: bytes, index: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while index < len(data):
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7
        if shift >= 70:
            break
    raise ValidationError("invalid protobuf varint")


def _write_varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    chunks: list[int] = []
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            chunks.append(byte | 0x80)
        else:
            chunks.append(byte)
            break
    return bytes(chunks)


def _skip_proto_value(data: bytes, index: int, wire_type: int) -> int:
    if wire_type == 0:
        _, index = _read_varint(data, index)
        return index
    if wire_type == 1:
        return index + 8
    if wire_type == 2:
        length, index = _read_varint(data, index)
        return index + length
    if wire_type == 5:
        return index + 4
    raise ValidationError(f"unsupported protobuf wire type: {wire_type}")


def _iter_proto_fields(data: bytes) -> Iterable[tuple[int, int, bytes | int]]:
    index = 0
    while index < len(data):
        tag, index = _read_varint(data, index)
        number = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:
            value, index = _read_varint(data, index)
            yield number, wire_type, value
        elif wire_type == 1:
            value = data[index : index + 8]
            index += 8
            yield number, wire_type, value
        elif wire_type == 2:
            length, index = _read_varint(data, index)
            value = data[index : index + length]
            index += length
            yield number, wire_type, value
        elif wire_type == 5:
            value = data[index : index + 4]
            index += 4
            yield number, wire_type, value
        else:
            index = _skip_proto_value(data, index, wire_type)


def _descriptor_string(data: bytes) -> str:
    return data.decode()


def _parse_field_descriptor(data: bytes) -> ProtoField:
    name = ""
    number = 0
    label = 1
    field_type = 0
    type_name = ""
    for field_number, _, value in _iter_proto_fields(data):
        if not isinstance(value, bytes):
            if field_number == 3:
                number = int(value)
            elif field_number == 4:
                label = int(value)
            elif field_number == 5:
                field_type = int(value)
            continue
        if field_number == 1:
            name = _descriptor_string(value)
        elif field_number == 6:
            type_name = _normalize_proto_type_name(_descriptor_string(value))
    return ProtoField(name, number, label, field_type, type_name)


def _parse_message_descriptor(data: bytes, prefix: str, messages: dict[str, ProtoMessage]) -> None:
    name = ""
    field_payloads: list[bytes] = []
    nested_payloads: list[bytes] = []
    for field_number, _, value in _iter_proto_fields(data):
        if not isinstance(value, bytes):
            continue
        if field_number == 1:
            name = _descriptor_string(value)
        elif field_number == 2:
            field_payloads.append(value)
        elif field_number == 3:
            nested_payloads.append(value)
    full_name = ".".join(part for part in (prefix, name) if part)
    fields = [_parse_field_descriptor(payload) for payload in field_payloads]
    messages[full_name] = ProtoMessage(
        full_name=full_name,
        fields={field.number: field for field in fields if field.number},
        fields_by_name={field.name: field for field in fields if field.name},
    )
    for payload in nested_payloads:
        _parse_message_descriptor(payload, full_name, messages)


def _parse_method_descriptor(data: bytes, service: str) -> ProtoMethod:
    name = ""
    input_type = ""
    output_type = ""
    for field_number, _, value in _iter_proto_fields(data):
        if not isinstance(value, bytes):
            continue
        if field_number == 1:
            name = _descriptor_string(value)
        elif field_number == 2:
            input_type = _normalize_proto_type_name(_descriptor_string(value))
        elif field_number == 3:
            output_type = _normalize_proto_type_name(_descriptor_string(value))
    return ProtoMethod(service, name, input_type, output_type)


def _parse_service_descriptor(data: bytes, package: str) -> list[ProtoMethod]:
    name = ""
    method_payloads: list[bytes] = []
    for field_number, _, value in _iter_proto_fields(data):
        if not isinstance(value, bytes):
            continue
        if field_number == 1:
            name = _descriptor_string(value)
        elif field_number == 2:
            method_payloads.append(value)
    service = ".".join(part for part in (package, name) if part)
    return [_parse_method_descriptor(payload, service) for payload in method_payloads]


def _parse_file_descriptor(data: bytes, messages: dict[str, ProtoMessage], methods: dict[tuple[str, str], ProtoMethod]) -> None:
    package = ""
    message_payloads: list[bytes] = []
    service_payloads: list[bytes] = []
    for field_number, _, value in _iter_proto_fields(data):
        if not isinstance(value, bytes):
            continue
        if field_number == 2:
            package = _descriptor_string(value)
        elif field_number == 4:
            message_payloads.append(value)
        elif field_number == 6:
            service_payloads.append(value)
    for payload in message_payloads:
        _parse_message_descriptor(payload, package, messages)
    for payload in service_payloads:
        for method in _parse_service_descriptor(payload, package):
            methods[(method.service, method.name)] = method


def load_grpc_descriptor_set(paths: Iterable[Path]) -> ProtoDescriptorSet:
    messages: dict[str, ProtoMessage] = {}
    methods: dict[tuple[str, str], ProtoMethod] = {}
    loaded = False
    for path in paths:
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            raise ValidationError(f"gRPC descriptor set is unreadable: {path}") from exc
        try:
            for field_number, _, value in _iter_proto_fields(data):
                if field_number == 1 and isinstance(value, bytes):
                    loaded = True
                    _parse_file_descriptor(value, messages, methods)
        except Exception as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"gRPC descriptor set is invalid: {path}") from exc
    if not loaded:
        raise ValidationError("gRPC descriptor set is invalid")
    return ProtoDescriptorSet(messages, methods)


def validate_grpc_descriptor_config(config: Config, behaviors: Iterable[Behavior]) -> ProtoDescriptorSet | None:
    behavior_list = list(behaviors)
    if not config.grpc_enabled or not behavior_needs_grpc_descriptors(behavior_list):
        return None
    paths = resolve_grpc_descriptor_paths(config.templates_dir, config.grpc_descriptor_set_paths)
    if not paths:
        raise ValidationError("HM_GRPC_DESCRIPTOR_SET_PATHS is required when gRPC behaviors are loaded")
    descriptors = load_grpc_descriptor_set(paths)
    for behavior in behavior_list:
        if behavior.trigger != "grpc":
            continue
        method = descriptors.method(behavior.grpc_service, behavior.grpc_method)
        descriptors.message(method.input_type)
        descriptors.message(method.output_type)
    return descriptors


def _proto_wire_type(field_type: int) -> int:
    if field_type in {PROTO_TYPE_INT32, PROTO_TYPE_INT64, PROTO_TYPE_UINT32, PROTO_TYPE_UINT64, PROTO_TYPE_BOOL, PROTO_TYPE_SINT32, PROTO_TYPE_SINT64}:
        return 0
    if field_type in {PROTO_TYPE_DOUBLE, PROTO_TYPE_FIXED64, PROTO_TYPE_SFIXED64}:
        return 1
    if field_type in {PROTO_TYPE_STRING, PROTO_TYPE_MESSAGE, PROTO_TYPE_BYTES}:
        return 2
    if field_type in {PROTO_TYPE_FLOAT, PROTO_TYPE_FIXED32, PROTO_TYPE_SFIXED32}:
        return 5
    raise ValidationError(f"unsupported protobuf field type: {field_type}")


def _decode_zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _encode_zigzag(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def decode_proto_message(data: bytes, message: ProtoMessage, descriptors: ProtoDescriptorSet) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for number, wire_type, value in _iter_proto_fields(data):
        field = message.fields.get(number)
        if field is None:
            continue
        decoded: Any
        if field.field_type == PROTO_TYPE_STRING:
            if not isinstance(value, bytes):
                raise ValidationError(f"protobuf field {field.name} expected bytes")
            decoded = value.decode()
        elif field.field_type == PROTO_TYPE_BYTES:
            if not isinstance(value, bytes):
                raise ValidationError(f"protobuf field {field.name} expected bytes")
            decoded = base64.b64encode(value).decode()
        elif field.field_type == PROTO_TYPE_BOOL:
            decoded = bool(value)
        elif field.field_type in {PROTO_TYPE_INT32, PROTO_TYPE_INT64, PROTO_TYPE_UINT32, PROTO_TYPE_UINT64}:
            decoded = int(value)
        elif field.field_type in {PROTO_TYPE_SINT32, PROTO_TYPE_SINT64}:
            decoded = _decode_zigzag(int(value))
        elif field.field_type == PROTO_TYPE_FLOAT:
            if not isinstance(value, bytes) or wire_type != 5:
                raise ValidationError(f"protobuf field {field.name} expected float")
            decoded = struct.unpack("<f", value)[0]
        elif field.field_type == PROTO_TYPE_DOUBLE:
            if not isinstance(value, bytes) or wire_type != 1:
                raise ValidationError(f"protobuf field {field.name} expected double")
            decoded = struct.unpack("<d", value)[0]
        elif field.field_type == PROTO_TYPE_MESSAGE:
            if not isinstance(value, bytes):
                raise ValidationError(f"protobuf field {field.name} expected message")
            decoded = decode_proto_message(value, descriptors.message(field.type_name), descriptors)
        else:
            continue
        if field.label == PROTO_LABEL_REPEATED:
            result.setdefault(field.name, []).append(decoded)
        else:
            result[field.name] = decoded
    return result


def encode_proto_message(value: dict[str, Any], message: ProtoMessage, descriptors: ProtoDescriptorSet) -> bytes:
    if not isinstance(value, dict):
        raise ValidationError("protobuf JSON payload must be an object")
    chunks: list[bytes] = []
    for name, raw_value in value.items():
        field = message.fields_by_name.get(name)
        if field is None:
            continue
        values = raw_value if field.label == PROTO_LABEL_REPEATED and isinstance(raw_value, list) else [raw_value]
        for item in values:
            chunks.append(_encode_proto_field(field, item, descriptors))
    return b"".join(chunks)


def _encode_proto_field(field: ProtoField, value: Any, descriptors: ProtoDescriptorSet) -> bytes:
    wire_type = _proto_wire_type(field.field_type)
    tag = _write_varint((field.number << 3) | wire_type)
    if field.field_type == PROTO_TYPE_STRING:
        data = str(value).encode()
        return tag + _write_varint(len(data)) + data
    if field.field_type == PROTO_TYPE_BYTES:
        data = base64.b64decode(value) if isinstance(value, str) else bytes(value)
        return tag + _write_varint(len(data)) + data
    if field.field_type == PROTO_TYPE_BOOL:
        return tag + _write_varint(1 if value else 0)
    if field.field_type in {PROTO_TYPE_INT32, PROTO_TYPE_INT64, PROTO_TYPE_UINT32, PROTO_TYPE_UINT64}:
        return tag + _write_varint(int(value))
    if field.field_type in {PROTO_TYPE_SINT32, PROTO_TYPE_SINT64}:
        return tag + _write_varint(_encode_zigzag(int(value)))
    if field.field_type == PROTO_TYPE_FLOAT:
        return tag + struct.pack("<f", float(value))
    if field.field_type == PROTO_TYPE_DOUBLE:
        return tag + struct.pack("<d", float(value))
    if field.field_type == PROTO_TYPE_MESSAGE:
        data = encode_proto_message(value, descriptors.message(field.type_name), descriptors)
        return tag + _write_varint(len(data)) + data
    raise ValidationError(f"unsupported protobuf field type: {field.field_type}")


def decode_grpc_frame(frame: bytes) -> bytes:
    if len(frame) < 5:
        raise ValidationError("invalid gRPC frame")
    compressed = frame[0]
    if compressed:
        raise ValidationError("compressed gRPC frames are not supported")
    length = int.from_bytes(frame[1:5], "big")
    payload = frame[5:]
    if len(payload) != length:
        raise ValidationError("invalid gRPC frame length")
    return payload


def encode_grpc_frame(payload: bytes) -> bytes:
    return b"\x00" + len(payload).to_bytes(4, "big") + payload


def decode_grpc_request_payload(frame: bytes, descriptors: ProtoDescriptorSet, service: str, method: str) -> str:
    proto_method = descriptors.method(service, method)
    message = descriptors.message(proto_method.input_type)
    decoded = decode_proto_message(decode_grpc_frame(frame), message, descriptors)
    return json.dumps(decoded, separators=(",", ":"))


def decode_grpc_unframed_request_payload(payload: bytes, descriptors: ProtoDescriptorSet, service: str, method: str) -> str:
    proto_method = descriptors.method(service, method)
    message = descriptors.message(proto_method.input_type)
    decoded = decode_proto_message(payload, message, descriptors)
    return json.dumps(decoded, separators=(",", ":"))


def encode_grpc_response_payload(payload_json: str, descriptors: ProtoDescriptorSet, service: str, method: str) -> bytes:
    proto_method = descriptors.method(service, method)
    message = descriptors.message(proto_method.output_type)
    try:
        parsed = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValidationError("reply_grpc payload must render valid JSON") from exc
    return encode_grpc_frame(encode_proto_message(parsed, message, descriptors))


def encode_grpc_unframed_response_payload(payload_json: str, descriptors: ProtoDescriptorSet, service: str, method: str) -> bytes:
    proto_method = descriptors.method(service, method)
    message = descriptors.message(proto_method.output_type)
    try:
        parsed = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValidationError("reply_grpc payload must render valid JSON") from exc
    return encode_proto_message(parsed, message, descriptors)


class KafkaAdapter:
    def publish(self, topic: str, payload: str) -> None:
        raise NotImplementedError

    def consume(
        self,
        topics: list[str],
        handler: Callable[[str, str], None],
        stop_event: threading.Event,
    ) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return


class RealKafkaAdapter(KafkaAdapter):
    def __init__(self, producer_config: KafkaEndpointConfig, consumer_config: KafkaEndpointConfig) -> None:
        if importlib.util.find_spec("kafka") is None:
            raise ValidationError("Kafka support requires optional dependency 'kafka-python'")
        from kafka import KafkaConsumer, KafkaProducer  # type: ignore[import-not-found]

        self._producer_cls = KafkaProducer
        self._consumer_cls = KafkaConsumer
        self.producer_config = producer_config
        self.consumer_config = consumer_config
        self._producer: Any | None = None

    def _client_kwargs(self, config: KafkaEndpointConfig) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "bootstrap_servers": config.seed_brokers,
            "client_id": config.client_id,
        }
        if config.sasl_enabled:
            kwargs.update(
                {
                    "security_protocol": "SASL_SSL" if config.tls_enabled else "SASL_PLAINTEXT",
                    "sasl_mechanism": "PLAIN",
                    "sasl_plain_username": config.sasl_username,
                    "sasl_plain_password": config.sasl_password,
                }
            )
        elif config.tls_enabled:
            kwargs["security_protocol"] = "SSL"
        return kwargs

    def publish(self, topic: str, payload: str) -> None:
        if self._producer is None:
            self._producer = self._producer_cls(
                value_serializer=lambda value: str(value).encode(),
                **self._client_kwargs(self.producer_config),
            )
        future = self._producer.send(topic, payload)
        future.get(timeout=10)
        self._producer.flush()

    def consume(
        self,
        topics: list[str],
        handler: Callable[[str, str], None],
        stop_event: threading.Event,
    ) -> None:
        consumer = self._consumer_cls(
            *topics,
            value_deserializer=lambda value: value.decode(errors="replace"),
            consumer_timeout_ms=1000,
            **self._client_kwargs(self.consumer_config),
        )
        try:
            while not stop_event.is_set():
                for message in consumer:
                    handler(str(message.topic), str(message.value))
                    if stop_event.is_set():
                        break
                break
        finally:
            consumer.close()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.close()


@dataclasses.dataclass(frozen=True)
class AMQPBinding:
    exchange: str
    routing_key: str
    queue: str


class AMQPAdapter:
    def setup(self, bindings: list[AMQPBinding]) -> None:
        raise NotImplementedError

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        raise NotImplementedError

    def consume(
        self,
        bindings: list[AMQPBinding],
        handler: Callable[[str, str, str, str], None],
        stop_event: threading.Event,
    ) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return


class RealAMQPAdapter(AMQPAdapter):
    def __init__(self, url: str) -> None:
        if importlib.util.find_spec("pika") is None:
            raise ValidationError("AMQP support requires optional dependency 'pika'")
        import pika  # type: ignore[import-not-found]

        self._pika = pika
        self.url = url

    def _connection(self) -> Any:
        return self._pika.BlockingConnection(self._pika.URLParameters(self.url))

    def setup(self, bindings: list[AMQPBinding]) -> None:
        with self._connection() as conn:
            channel = conn.channel()
            for binding in bindings:
                channel.exchange_declare(exchange=binding.exchange, exchange_type="direct", durable=True)
                channel.queue_declare(queue=binding.queue, durable=True)
                channel.queue_bind(
                    queue=binding.queue,
                    exchange=binding.exchange,
                    routing_key=binding.routing_key,
                )

    def publish(self, exchange: str, routing_key: str, payload: str) -> None:
        with self._connection() as conn:
            channel = conn.channel()
            channel.basic_publish(exchange=exchange, routing_key=routing_key, body=payload.encode())

    def consume(
        self,
        bindings: list[AMQPBinding],
        handler: Callable[[str, str, str, str], None],
        stop_event: threading.Event,
    ) -> None:
        with self._connection() as conn:
            channel = conn.channel()
            while not stop_event.is_set():
                for binding in bindings:
                    method, _, body = channel.basic_get(queue=binding.queue, auto_ack=True)
                    if method is not None:
                        handler(
                            binding.exchange,
                            str(method.routing_key),
                            binding.queue,
                            body.decode(errors="replace"),
                        )
                stop_event.wait(0.2)


def kafka_topics_for_behaviors(behaviors: Iterable[Behavior]) -> list[str]:
    return sorted({behavior.kafka_topic for behavior in behaviors if behavior.trigger == "kafka" and behavior.kafka_topic})


def amqp_bindings_for_behaviors(behaviors: Iterable[Behavior]) -> list[AMQPBinding]:
    bindings = {
        AMQPBinding(behavior.amqp_exchange, behavior.amqp_routing_key, behavior.amqp_queue)
        for behavior in behaviors
        if behavior.trigger == "amqp"
    }
    return sorted(bindings, key=lambda item: (item.exchange, item.routing_key, item.queue))


class KafkaBrokerWorker:
    def __init__(
        self,
        state: MockState,
        redis_store: RedisStore,
        logger: JsonLogger,
        adapter: KafkaAdapter,
    ) -> None:
        self.state = state
        self.redis_store = redis_store
        self.logger = logger
        self.adapter = adapter
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def referenced_topics(self) -> list[str]:
        return kafka_topics_for_behaviors(self.state.behavior_snapshot())

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.adapter.close()

    def run_once(self) -> None:
        topics = self.referenced_topics()
        if not topics:
            self.stop_event.wait(0.2)
            return
        self.adapter.consume(topics, self.handle_message, self.stop_event)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                self.logger.warn("kafka consumer failed", error=str(exc))
                self.stop_event.wait(1.0)

    def handle_message(self, topic: str, payload: str) -> None:
        handle_kafka_message(
            self.state.behavior_snapshot(),
            topic,
            payload,
            self.redis_store,
            self.logger,
            self.adapter,
            None,
        )


class AMQPBrokerWorker:
    def __init__(
        self,
        state: MockState,
        redis_store: RedisStore,
        logger: JsonLogger,
        adapter: AMQPAdapter,
    ) -> None:
        self.state = state
        self.redis_store = redis_store
        self.logger = logger
        self.adapter = adapter
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def referenced_bindings(self) -> list[AMQPBinding]:
        return amqp_bindings_for_behaviors(self.state.behavior_snapshot())

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.adapter.close()

    def run_once(self) -> None:
        bindings = self.referenced_bindings()
        if not bindings:
            self.stop_event.wait(0.2)
            return
        self.adapter.setup(bindings)
        self.adapter.consume(bindings, self.handle_message, self.stop_event)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                self.logger.warn("amqp consumer failed", error=str(exc))
                self.stop_event.wait(1.0)

    def handle_message(self, exchange: str, routing_key: str, queue: str, payload: str) -> None:
        handle_amqp_message(
            self.state.behavior_snapshot(),
            exchange,
            routing_key,
            queue,
            payload,
            self.redis_store,
            self.logger,
            None,
            self.adapter,
        )


def find_behavior(
    behaviors: list[Behavior],
    request: RequestInfo,
    redis_store: RedisStore | None = None,
) -> tuple[Behavior, dict[str, str]] | tuple[None, dict[str, str]]:
    for behavior in behaviors:
        if behavior.trigger != "http":
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
            guarded_redis_do(redis_store) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        try:
            if render_template(behavior.condition, context) == "true":
                return behavior, params
        except TemplateError:
            continue
    return None, {}


def matching_kafka_behaviors(
    behaviors: Iterable[Behavior],
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
) -> list[Behavior]:
    matched: list[Behavior] = []
    for behavior in behaviors:
        if behavior.trigger != "kafka" or behavior.kafka_topic != topic:
            continue
        context = build_kafka_template_context(
            topic,
            payload,
            guarded_redis_do(redis_store) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        if not behavior.condition:
            matched.append(behavior)
            continue
        try:
            if render_template(behavior.condition, context) == "true":
                matched.append(behavior)
        except TemplateError:
            continue
    return matched


def matching_amqp_behaviors(
    behaviors: Iterable[Behavior],
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_store: RedisStore | None = None,
) -> list[Behavior]:
    matched: list[Behavior] = []
    for behavior in behaviors:
        if behavior.trigger != "amqp":
            continue
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
            guarded_redis_do(redis_store) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        if not behavior.condition:
            matched.append(behavior)
            continue
        try:
            if render_template(behavior.condition, context) == "true":
                matched.append(behavior)
        except TemplateError:
            continue
    return matched


def find_grpc_behavior(
    behaviors: Iterable[Behavior],
    service: str,
    method: str,
    payload: str,
    headers: dict[str, str] | Iterable[tuple[str, str]],
    redis_store: RedisStore | None = None,
) -> Behavior | None:
    for behavior in behaviors:
        if behavior.trigger != "grpc":
            continue
        if behavior.grpc_service != service or behavior.grpc_method != method:
            continue
        context = build_grpc_template_context(
            service,
            method,
            payload,
            headers,
            guarded_redis_do(redis_store) if redis_store is not None else None,
            behavior.values,
            behavior.templates,
        )
        if not behavior.condition:
            return behavior
        try:
            if render_template(behavior.condition, context) == "true":
                return behavior
        except TemplateError:
            continue
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
        body = render_template(str(body_source), context)
        data = body.encode()
    elif "send_http_body_from_binary_file_content" in payload:
        binary_body = payload["send_http_body_from_binary_file_content"]
        if method == "POST":
            part_content_type = headers.pop("Content-Type", headers.pop("content-type", "application/octet-stream"))
            filename = str(payload.get("binary_file_name") or payload.get("binary_source_file_name") or Path(str(payload.get("body_from_binary_file", "file"))).name)
            boundary = f"hmock-{uuid.uuid4().hex}"
            data = _multipart_file_body(boundary, "file", filename, str(part_content_type), binary_body)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            data = binary_body
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


def _payload_source(payload: dict[str, Any], context: dict[str, Any], content_field: str) -> str:
    body_source = payload.get("payload")
    if body_source is not None and body_source != "":
        return render_template(str(body_source), context)
    return render_template(str(payload.get(content_field, "")), context)


def _publish_kafka(payload: dict[str, Any], context: dict[str, Any], adapter: KafkaAdapter | None) -> None:
    if adapter is None:
        raise TemplateError("Kafka publishing is not configured")
    topic = render_template(str(payload["topic"]), context)
    adapter.publish(topic, _payload_source(payload, context, "kafka_payload_from_file_content"))


def _publish_amqp(payload: dict[str, Any], context: dict[str, Any], adapter: AMQPAdapter | None) -> None:
    if adapter is None:
        raise TemplateError("AMQP publishing is not configured")
    exchange = render_template(str(payload["exchange"]), context)
    routing_key = render_template(str(payload["routing_key"]), context)
    adapter.publish(exchange, routing_key, _payload_source(payload, context, "amqp_payload_from_file_content"))


def _render_reply_grpc(payload: dict[str, Any], context: dict[str, Any]) -> ResponseInfo:
    body = _payload_source(payload, context, "grpc_payload_from_file_content")
    headers = {
        str(key): render_template(str(value), context)
        for key, value in (payload.get("headers") or {}).items()
    }
    headers["grpc-status"] = "0"
    headers["grpc-message"] = "OK"
    if not any(key.lower() == "content-type" for key in headers):
        headers["Content-Type"] = "application/grpc"
    return ResponseInfo(200, headers, body)


def _multipart_file_body(
    boundary: str,
    field_name: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> bytes:
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode()
    footer = f"\r\n--{boundary}--\r\n".encode()
    return header + data + footer


def execute_actions(
    behavior: Behavior,
    context: dict[str, Any],
    redis_do: Callable[[str], str],
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
    allow_reply: bool = True,
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
            _publish_kafka(payload, context, kafka_adapter)
        elif name == "publish_amqp":
            _publish_amqp(payload, context, amqp_adapter)
        elif name == "reply_http" and allow_reply:
            body_source = payload.get("body")
            headers = {
                str(key): render_template(str(value), context)
                for key, value in (payload.get("headers") or {}).items()
            }
            if body_source is not None and body_source != "":
                body: str | bytes = render_template(str(body_source), context)
            elif "body_from_binary_file_content" in payload:
                body = payload["body_from_binary_file_content"]
                if payload.get("binary_file_name") is not None:
                    headers["Content-Disposition"] = f'inline; filename="{payload["binary_file_name"]}"'
            else:
                body_source = payload.get("body_from_file_content", "")
                body = render_template(str(body_source), context)
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body if isinstance(body, bytes) else body.encode()))
            response = ResponseInfo(int(payload["status_code"]), headers, body)
        elif name == "reply_grpc" and allow_reply:
            response = _render_reply_grpc(payload, context)
    return response


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
    response = execute_actions(
        behavior,
        context,
        redis_do,
        logger,
        kafka_adapter,
        amqp_adapter,
        allow_reply=True,
    )
    return response or ResponseInfo(204, {"Content-Length": "0"}, "")


def execute_kafka_behavior(
    behavior: Behavior,
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> None:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = guarded_redis_do(redis_store)
    context = build_kafka_template_context(topic, payload, redis_do, behavior.values, behavior.templates)
    execute_actions(behavior, context, redis_do, logger, kafka_adapter, amqp_adapter, allow_reply=False)


def execute_amqp_behavior(
    behavior: Behavior,
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> None:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = guarded_redis_do(redis_store)
    context = build_amqp_template_context(
        exchange,
        routing_key,
        queue,
        payload,
        redis_do,
        behavior.values,
        behavior.templates,
    )
    execute_actions(behavior, context, redis_do, logger, kafka_adapter, amqp_adapter, allow_reply=False)


def execute_grpc_behavior(
    behavior: Behavior,
    service: str,
    method: str,
    payload: str,
    headers: dict[str, str] | Iterable[tuple[str, str]],
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> ResponseInfo:
    redis_store = redis_store or MemoryRedisStore()
    redis_do = guarded_redis_do(redis_store)
    context = build_grpc_template_context(
        service,
        method,
        payload,
        headers,
        redis_do,
        behavior.values,
        behavior.templates,
    )
    response = execute_actions(
        behavior,
        context,
        redis_do,
        logger,
        kafka_adapter,
        amqp_adapter,
        allow_reply=True,
    )
    return response or ResponseInfo(
        200,
        {"grpc-status": "0", "grpc-message": "OK", "Content-Type": "application/grpc"},
        "",
    )


def handle_kafka_message(
    behaviors: list[Behavior],
    topic: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> int:
    matched = matching_kafka_behaviors(behaviors, topic, payload, redis_store)
    for behavior in matched:
        execute_kafka_behavior(behavior, topic, payload, redis_store, logger, kafka_adapter, amqp_adapter)
    return len(matched)


def handle_amqp_message(
    behaviors: list[Behavior],
    exchange: str,
    routing_key: str,
    queue: str,
    payload: str,
    redis_store: RedisStore | None = None,
    logger: JsonLogger | None = None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> int:
    matched = matching_amqp_behaviors(behaviors, exchange, routing_key, queue, payload, redis_store)
    for behavior in matched:
        execute_amqp_behavior(
            behavior,
            exchange,
            routing_key,
            queue,
            payload,
            redis_store,
            logger,
            kafka_adapter,
            amqp_adapter,
        )
    return len(matched)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field_name} must be an object")
    return value


def _string_map(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError(f"{field_name} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValidationError(f"{field_name} must be a string map")
        result[key] = item
    return result


def _evaluation_context_for_behavior(behavior: Behavior, context: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    redis_do = None
    if behavior.trigger == "http":
        http = _require_mapping(context.get("http_context"), "context.http_context")
        method = http.get("method")
        path = http.get("path")
        if not isinstance(method, str) or not isinstance(path, str):
            raise ValidationError("context.http_context.method and path are required")
        split = urlsplit(path)
        route_path = posixpath.normpath(split.path)
        if split.path.startswith("/") and not route_path.startswith("/"):
            route_path = "/" + route_path
        if split.path == "/":
            route_path = "/"
        params = behavior.pattern.match(route_path) if behavior.pattern is not None else None
        passed = behavior.method == method.upper() and params is not None
        render_context = build_template_context(
            _string_map(http.get("headers", {}), "context.http_context.headers"),
            str(http.get("body", "")),
            path,
            str(http.get("query_string", split.query)),
            params or {},
            redis_do,
            behavior.values,
            behavior.templates,
        )
    elif behavior.trigger == "kafka":
        kafka = _require_mapping(context.get("kafka_context"), "context.kafka_context")
        topic = kafka.get("topic")
        if not isinstance(topic, str):
            raise ValidationError("context.kafka_context.topic is required")
        payload = str(kafka.get("payload", ""))
        passed = behavior.kafka_topic == topic
        render_context = build_kafka_template_context(topic, payload, redis_do, behavior.values, behavior.templates)
    elif behavior.trigger == "amqp":
        amqp = _require_mapping(context.get("amqp_context"), "context.amqp_context")
        exchange = amqp.get("exchange")
        routing_key = amqp.get("routing_key")
        queue = amqp.get("queue")
        if not isinstance(exchange, str) or not isinstance(routing_key, str):
            raise ValidationError("context.amqp_context.exchange and routing_key are required")
        if queue is not None and not isinstance(queue, str):
            raise ValidationError("context.amqp_context.queue must be a string")
        queue_value = queue or routing_key
        payload = str(amqp.get("payload", ""))
        passed = (
            behavior.amqp_exchange == exchange
            and behavior.amqp_routing_key == routing_key
            and behavior.amqp_queue == queue_value
        )
        render_context = build_amqp_template_context(
            exchange,
            routing_key,
            queue_value,
            payload,
            redis_do,
            behavior.values,
            behavior.templates,
        )
    elif behavior.trigger == "grpc":
        grpc = _require_mapping(context.get("grpc_context"), "context.grpc_context")
        service = grpc.get("service")
        method = grpc.get("method")
        if not isinstance(service, str) or not isinstance(method, str):
            raise ValidationError("context.grpc_context.service and method are required")
        payload = str(grpc.get("payload", ""))
        passed = behavior.grpc_service == service and behavior.grpc_method == method
        render_context = build_grpc_template_context(
            service,
            method,
            payload,
            _string_map(grpc.get("headers", {}), "context.grpc_context.headers"),
            redis_do,
            behavior.values,
            behavior.templates,
        )
    else:
        raise ValidationError(f"unsupported trigger: {behavior.trigger}")
    _merge_optional_contexts(render_context, context)
    return render_context, passed, behavior.condition


def _merge_optional_contexts(render_context: dict[str, Any], context: dict[str, Any]) -> None:
    http = context.get("http_context")
    if isinstance(http, dict):
        render_context.setdefault("HTTPHeader", HeaderMap(_string_map(http.get("headers", {}), "context.http_context.headers")))
        render_context.setdefault("HTTPBody", str(http.get("body", "")))
        render_context.setdefault("HTTPPath", str(http.get("path", "")))
        render_context.setdefault("HTTPQueryString", str(http.get("query_string", urlsplit(str(http.get("path", ""))).query)))
    kafka = context.get("kafka_context")
    if isinstance(kafka, dict):
        render_context.setdefault("KafkaTopic", str(kafka.get("topic", "")))
        render_context.setdefault("KafkaPayload", str(kafka.get("payload", "")))
    amqp = context.get("amqp_context")
    if isinstance(amqp, dict):
        routing_key = str(amqp.get("routing_key", ""))
        render_context.setdefault("AMQPExchange", str(amqp.get("exchange", "")))
        render_context.setdefault("AMQPRoutingKey", routing_key)
        render_context.setdefault("AMQPQueue", str(amqp.get("queue") or routing_key))
        render_context.setdefault("AMQPPayload", str(amqp.get("payload", "")))
    grpc = context.get("grpc_context")
    if isinstance(grpc, dict):
        render_context.setdefault("GRPCService", str(grpc.get("service", "")))
        render_context.setdefault("GRPCMethod", str(grpc.get("method", "")))
        render_context.setdefault("GRPCPayload", str(grpc.get("payload", "")))
        render_context.setdefault("GRPCHeader", HeaderMap(_string_map(grpc.get("headers", {}), "context.grpc_context.headers")))


def _evaluated_reply_http(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    body_source = payload.get("body")
    headers = {
        str(key): render_template(str(value), context)
        for key, value in (payload.get("headers") or {}).items()
    }
    if body_source is not None and body_source != "":
        body = render_template(str(body_source), context)
    else:
        body = render_template(str(payload.get("body_from_file_content", "")), context)
    if not any(key.lower() == "content-type" for key in headers):
        headers["Content-Type"] = "application/json"
    headers["Content-Length"] = str(len(body.encode()))
    content_type = next((value for key, value in headers.items() if key.lower() == "content-type"), "application/json")
    return {
        "type": "reply_http_action_performed",
        "status_code": str(payload["status_code"]),
        "content_type": content_type,
        "body": body,
        "headers": headers,
    }


def _evaluated_publish_kafka(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "publish_kafka_action_performed",
        "topic": render_template(str(payload["topic"]), context),
        "payload": _payload_source(payload, context, "kafka_payload_from_file_content"),
    }


def evaluate_mock_definition(
    request: dict[str, Any],
    templates_dir: str | Path | None = None,
    templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    mock = _require_mapping(request.get("mock"), "mock")
    context = request.get("context")
    if isinstance(context, list):
        raise ValidationError("context must be an object")
    context = _require_mapping(context, "context")
    behavior = validate_behavior(copy.deepcopy(mock), templates_dir, templates)
    render_context, expect_passed, condition = _evaluation_context_for_behavior(behavior, context)
    result: dict[str, Any] = {
        "expect_passed": expect_passed,
        "condition_passed": False,
        "condition_rendered": "",
        "actions_performed": [],
    }
    if not expect_passed:
        return result
    if condition:
        condition_rendered = render_template(condition, render_context)
        result["condition_rendered"] = condition_rendered
        if condition_rendered != "true":
            return result
    result["condition_passed"] = True
    actions_performed: list[dict[str, Any]] = []
    for action in behavior.actions:
        name, payload = _action_name_payload(action, behavior.key)
        if name == "reply_http":
            actions_performed.append(_evaluated_reply_http(payload, render_context))
        elif name == "publish_kafka":
            actions_performed.append(_evaluated_publish_kafka(payload, render_context))
    result["actions_performed"] = actions_performed
    return result


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


def apply_cors_headers(response: ResponseInfo, enabled: bool) -> ResponseInfo:
    if not enabled:
        return response
    headers = dict(CORS_HEADERS)
    for key, value in response.headers.items():
        existing = next((name for name in headers if name.lower() == key.lower()), None)
        if existing is not None:
            del headers[existing]
        headers[key] = value
    return ResponseInfo(response.status_code, headers, response.body)


def preflight_response() -> ResponseInfo:
    return ResponseInfo(200, {"Content-Length": "0"}, "")


class AdminHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "AdminHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/v1/health":
            self._send_json(200, {"status": "OK"})
            return
        if path == "/api/v1/templates":
            self._send_json(200, self.server.state.raw_definition_snapshot())
            return
        self._send_error(404, "not found")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/api/v1/evaluate":
                self._send_json(200, evaluate_mock_definition(self._read_json_body(), self.server.templates_dir))
                return
            definitions = self._read_definition_array()
            if path == "/api/v1/templates":
                self._upsert_base_templates(definitions)
                self._send_json(200, definitions)
                return
            set_key = self._template_set_key(path)
            if set_key is not None:
                self._replace_template_set(set_key, definitions)
                self._send_json(200, definitions)
                return
            self._send_error(404, "not found")
        except ValidationError as exc:
            self._send_error(400, str(exc))
        except json.JSONDecodeError:
            self._send_error(400, "request body must be valid JSON")

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/api/v1/templates":
                self._delete_base_templates()
                self._send_empty(204)
                return
            template_key = self._template_key(path)
            if template_key is not None:
                if not self._delete_base_template(template_key):
                    self._send_error(404, "template not found")
                    return
                self._send_empty(204)
                return
            set_key = self._template_set_key(path)
            if set_key is not None:
                self._delete_template_set(set_key)
                self._send_empty(204)
                return
            self._send_error(404, "not found")
        except ValidationError as exc:
            self._send_error(400, str(exc))

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        return json.loads(body)

    def _read_definition_array(self) -> list[dict[str, Any]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode() if length else ""
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type in {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"} or content_type.endswith("+yaml"):
            return _validate_definition_array(parse_yaml_subset(body))
        return _validate_definition_array(json.loads(body))

    def _template_key(self, path: str) -> str | None:
        prefix = "/api/v1/templates/"
        if not path.startswith(prefix):
            return None
        key = unquote(path[len(prefix) :])
        return key if key else None

    def _template_set_key(self, path: str) -> str | None:
        prefix = "/api/v1/template_sets/"
        if not path.startswith(prefix):
            return None
        key = unquote(path[len(prefix) :])
        return validate_template_set_key(key)

    def _persist_and_reload(
        self,
        base_definitions: list[dict[str, Any]],
        template_sets: dict[str, list[dict[str, Any]]],
        persist: Callable[[], None],
    ) -> None:
        with self.server.admin_lock:
            collection = build_collection_from_persisted(
                self.server.templates_dir,
                self.server.hm_logger,
                base_definitions,
                template_sets,
                None if self.server.templates_hot_reload else self.server.state.filesystem_definition_snapshot(),
            )
            persist()
            self.server.state.replace(collection)

    def _upsert_base_templates(self, definitions: list[dict[str, Any]]) -> None:
        current = load_base_api_definitions(self.server.redis_store)
        updated = upsert_definitions(current, definitions)
        template_sets = load_template_sets(self.server.redis_store)
        self._persist_and_reload(
            updated,
            template_sets,
            lambda: save_base_api_definitions(self.server.redis_store, updated),
        )

    def _replace_template_set(self, set_key: str, definitions: list[dict[str, Any]]) -> None:
        base_definitions = load_base_api_definitions(self.server.redis_store)
        template_sets = load_template_sets(self.server.redis_store)
        template_sets[set_key] = copy.deepcopy(definitions)
        self._persist_and_reload(
            base_definitions,
            template_sets,
            lambda: save_template_set(self.server.redis_store, set_key, definitions),
        )

    def _delete_base_templates(self) -> None:
        template_sets = load_template_sets(self.server.redis_store)
        self._persist_and_reload(
            [],
            template_sets,
            lambda: save_base_api_definitions(self.server.redis_store, []),
        )

    def _delete_base_template(self, template_key: str) -> bool:
        current = load_base_api_definitions(self.server.redis_store)
        if not any(raw.get("key") == template_key for raw in current):
            return False
        updated = [raw for raw in current if raw.get("key") != template_key]
        template_sets = load_template_sets(self.server.redis_store)
        self._persist_and_reload(
            updated,
            template_sets,
            lambda: save_base_api_definitions(self.server.redis_store, updated),
        )
        return True

    def _delete_template_set(self, set_key: str) -> None:
        base_definitions = load_base_api_definitions(self.server.redis_store)
        template_sets = load_template_sets(self.server.redis_store)
        template_sets.pop(set_key, None)
        self._persist_and_reload(
            base_definitions,
            template_sets,
            lambda: delete_template_set(self.server.redis_store, set_key),
        )

    def _send_json(self, status: int, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":"))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def _send_error(self, status: int, message: str) -> None:
        body = message
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


class AdminHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        state: MockState,
        templates_dir: str | Path,
        logger: JsonLogger,
        redis_store: RedisStore,
        templates_hot_reload: bool = True,
    ) -> None:
        super().__init__(address, AdminHTTPRequestHandler)
        self.state = state
        self.templates_dir = templates_dir
        self.hm_logger = logger
        self.redis_store = redis_store
        self.admin_lock = threading.Lock()
        self.templates_hot_reload = templates_hot_reload


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
        self.server.refresh_templates_if_needed()
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
        behavior, params = find_behavior(self.server.state.behavior_snapshot(), request, self.server.redis_store)
        try:
            if behavior:
                response = execute_behavior(
                    behavior,
                    request,
                    params,
                    self.server.redis_store,
                    self.server.hm_logger,
                    self.server.kafka_adapter,
                    self.server.amqp_adapter,
                )
            elif self.server.cors_enabled and request.method.upper() == "OPTIONS":
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
            self.wfile.write(response.body if isinstance(response.body, bytes) else response.body.encode())
        log_body = response.body.hex() if isinstance(response.body, bytes) else response.body
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
                "body": log_body,
            },
        )


class GRPCMockHTTPRequestHandler(BaseHTTPRequestHandler):
    server: "HMockGRPCServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        split = urlsplit(self.path)
        parts = [unquote(part) for part in split.path.strip("/").split("/") if part]
        if len(parts) != 2:
            self._send_grpc_error("12", "unknown service or method")
            return
        service, method = parts
        length = int(self.headers.get("Content-Length", "0") or "0")
        frame = self.rfile.read(length) if length else b""
        try:
            if self.server.descriptors is None:
                raise ValidationError("gRPC descriptors are not configured")
            payload = decode_grpc_request_payload(frame, self.server.descriptors, service, method)
            behavior = find_grpc_behavior(
                self.server.state.behavior_snapshot(),
                service,
                method,
                payload,
                {key: value for key, value in self.headers.items()},
                self.server.redis_store,
            )
            if behavior is None:
                self._send_grpc_error("12", "not found")
                return
            response = execute_grpc_behavior(
                behavior,
                service,
                method,
                payload,
                {key: value for key, value in self.headers.items()},
                self.server.redis_store,
                self.server.hm_logger,
                self.server.kafka_adapter,
                self.server.amqp_adapter,
            )
            body = response.body.decode() if isinstance(response.body, bytes) else str(response.body)
            encoded = encode_grpc_response_payload(body, self.server.descriptors, service, method)
            headers = dict(response.headers)
            headers["Content-Length"] = str(len(encoded))
            self.send_response(200)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(encoded)
        except (HMockError, ValueError) as exc:
            self.server.hm_logger.error("grpc request failed", error=str(exc), grpc_service=service, grpc_method=method)
            self._send_grpc_error("13", str(exc))

    def _send_grpc_error(self, status: str, message: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/grpc")
        self.send_header("grpc-status", status)
        self.send_header("grpc-message", message)
        self.send_header("Content-Length", "0")
        self.end_headers()


class HMockGRPCServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        state: MockState,
        logger: JsonLogger,
        redis_store: RedisStore,
        descriptors: ProtoDescriptorSet | None = None,
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
    ) -> None:
        super().__init__(address, GRPCMockHTTPRequestHandler)
        self.state = state
        self.hm_logger = logger
        self.redis_store = redis_store
        self.descriptors = descriptors
        self.kafka_adapter = kafka_adapter
        self.amqp_adapter = amqp_adapter


class GRPCIOHMockServer:
    def __init__(
        self,
        address: tuple[str, int],
        state: MockState,
        logger: JsonLogger,
        redis_store: RedisStore,
        descriptors: ProtoDescriptorSet | None,
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
    ) -> None:
        if importlib.util.find_spec("grpc") is None:
            raise ValidationError("gRPC HTTP/2 support requires optional dependency 'grpcio'")
        import grpc  # type: ignore[import-not-found]

        self.state = state
        self.hm_logger = logger
        self.redis_store = redis_store
        self.descriptors = descriptors
        self.kafka_adapter = kafka_adapter
        self.amqp_adapter = amqp_adapter
        self._grpc = grpc
        self._server = grpc.server(ThreadPoolExecutor(max_workers=10))
        self._register_handlers()
        port = self._server.add_insecure_port(f"{address[0]}:{address[1]}")
        self.server_address = (address[0], port)

    def _register_handlers(self) -> None:
        services: dict[str, dict[str, Any]] = {}
        for behavior in self.state.behavior_snapshot():
            if behavior.trigger == "grpc":
                services.setdefault(behavior.grpc_service, {})[behavior.grpc_method] = self._handler(
                    behavior.grpc_service,
                    behavior.grpc_method,
                )
        for service, handlers in services.items():
            self._server.add_generic_rpc_handlers(
                (self._grpc.method_handlers_generic_handler(service, handlers),)
            )

    def _handler(self, service: str, method: str) -> Any:
        def handle(request_bytes: bytes, context: Any) -> bytes:
            try:
                if self.descriptors is None:
                    raise ValidationError("gRPC descriptors are not configured")
                headers = {item.key: item.value for item in context.invocation_metadata()}
                payload = decode_grpc_unframed_request_payload(request_bytes, self.descriptors, service, method)
                behavior = find_grpc_behavior(
                    self.state.behavior_snapshot(),
                    service,
                    method,
                    payload,
                    headers,
                    self.redis_store,
                )
                if behavior is None:
                    context.set_code(self._grpc.StatusCode.UNIMPLEMENTED)
                    context.set_details("not found")
                    return b""
                response = execute_grpc_behavior(
                    behavior,
                    service,
                    method,
                    payload,
                    headers,
                    self.redis_store,
                    self.hm_logger,
                    self.kafka_adapter,
                    self.amqp_adapter,
                )
                custom_headers = [
                    (key, value)
                    for key, value in response.headers.items()
                    if key.lower() not in {"content-type", "content-length", "grpc-status", "grpc-message"}
                ]
                if custom_headers:
                    context.send_initial_metadata(custom_headers)
                body = response.body.decode() if isinstance(response.body, bytes) else str(response.body)
                return encode_grpc_unframed_response_payload(body, self.descriptors, service, method)
            except Exception as exc:
                self.hm_logger.error("grpc request failed", error=str(exc), grpc_service=service, grpc_method=method)
                context.set_code(self._grpc.StatusCode.INTERNAL)
                context.set_details(str(exc))
                return b""

        return self._grpc.unary_unary_rpc_method_handler(
            handle,
            request_deserializer=lambda data: data,
            response_serializer=lambda data: data,
        )

    def start(self) -> None:
        self._server.start()

    def shutdown(self) -> None:
        self._server.stop(0)

    def server_close(self) -> None:
        return


def build_grpc_runtime_server(
    config: Config,
    state: MockState,
    logger: JsonLogger,
    redis_store: RedisStore,
    descriptors: ProtoDescriptorSet | None,
    kafka_adapter: KafkaAdapter | None = None,
    amqp_adapter: AMQPAdapter | None = None,
) -> tuple[Any, threading.Thread | None]:
    address = (config.grpc_host, config.grpc_port)
    if importlib.util.find_spec("grpc") is not None:
        server = GRPCIOHMockServer(address, state, logger, redis_store, descriptors, kafka_adapter, amqp_adapter)
        server.start()
        return server, None
    server = HMockGRPCServer(address, state, logger, redis_store, descriptors, kafka_adapter, amqp_adapter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class HMockHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        behaviors: list[Behavior] | MockState,
        logger: JsonLogger,
        redis_store: RedisStore | None = None,
        templates_dir: str | Path | None = None,
        templates_hot_reload: bool = False,
        cors_enabled: bool = False,
        kafka_adapter: KafkaAdapter | None = None,
        amqp_adapter: AMQPAdapter | None = None,
        broker_workers: list[KafkaBrokerWorker | AMQPBrokerWorker] | None = None,
        grpc_server: HMockGRPCServer | None = None,
        grpc_thread: threading.Thread | None = None,
    ) -> None:
        super().__init__(address, MockHTTPRequestHandler)
        self.state = behaviors if isinstance(behaviors, MockState) else MockState(behaviors)
        self.hm_logger = logger
        self.redis_store = redis_store or MemoryRedisStore()
        self.cors_enabled = cors_enabled
        self.kafka_adapter = kafka_adapter
        self.amqp_adapter = amqp_adapter
        self.broker_workers = list(broker_workers or [])
        self.grpc_server = grpc_server
        self.grpc_thread = grpc_thread
        self.reload_coordinator = (
            TemplatesReloadCoordinator(templates_dir, self.state, self.redis_store, logger)
            if templates_hot_reload and templates_dir is not None
            else None
        )

    def refresh_templates_if_needed(self) -> None:
        if self.reload_coordinator is not None:
            self.reload_coordinator.refresh_if_needed()

    def start_broker_workers(self) -> None:
        for worker in self.broker_workers:
            worker.start()

    def stop_broker_workers(self) -> None:
        for worker in self.broker_workers:
            worker.stop()

    def server_close(self) -> None:
        self.stop_broker_workers()
        if self.grpc_server is not None:
            self.grpc_server.shutdown()
            self.grpc_server.server_close()
        if self.grpc_thread is not None:
            self.grpc_thread.join(timeout=2)
        super().server_close()


def build_server(config: Config | None = None, logger: JsonLogger | None = None) -> HMockHTTPServer:
    config = config or load_config()
    logger = logger or JsonLogger(config.log_level)
    redis_store = build_redis_store(config)
    collection = load_persisted_mock_collection(config.templates_dir, redis_store, logger)
    state = MockState(collection.behaviors, collection.raw_definitions, collection.filesystem_definitions)
    kafka_adapter: KafkaAdapter | None = None
    amqp_adapter: AMQPAdapter | None = None
    broker_workers: list[KafkaBrokerWorker | AMQPBrokerWorker] = []
    grpc_descriptors = validate_grpc_descriptor_config(config, state.behavior_snapshot())
    if config.kafka_enabled:
        kafka_adapter = RealKafkaAdapter(
            resolve_kafka_endpoint_config(config, "producer"),
            resolve_kafka_endpoint_config(config, "consumer"),
        )
        if kafka_topics_for_behaviors(state.behavior_snapshot()):
            broker_workers.append(KafkaBrokerWorker(state, redis_store, logger, kafka_adapter))
    if config.amqp_enabled:
        amqp_adapter = RealAMQPAdapter(config.amqp_url)
        if amqp_bindings_for_behaviors(state.behavior_snapshot()):
            broker_workers.append(AMQPBrokerWorker(state, redis_store, logger, amqp_adapter))
    grpc_server: HMockGRPCServer | None = None
    grpc_thread: threading.Thread | None = None
    if config.grpc_enabled:
        grpc_server, grpc_thread = build_grpc_runtime_server(
            config,
            state,
            logger,
            redis_store,
            grpc_descriptors,
            kafka_adapter,
            amqp_adapter,
        )
        logger.info("hmock grpc server started", host=config.grpc_host, port=grpc_server.server_address[1])
    server = HMockHTTPServer(
        (config.http_host, config.http_port),
        state,
        logger,
        redis_store,
        config.templates_dir,
        config.templates_dir_hot_reload,
        config.cors_enabled,
        kafka_adapter,
        amqp_adapter,
        broker_workers,
        grpc_server,
        grpc_thread,
    )
    server.start_broker_workers()
    return server


def build_admin_server(
    config: Config,
    logger: JsonLogger,
    state: MockState,
    redis_store: RedisStore,
) -> AdminHTTPServer:
    return AdminHTTPServer(
        (config.admin_http_host, config.admin_http_port),
        state,
        config.templates_dir,
        logger,
        redis_store,
        config.templates_dir_hot_reload,
    )


def main() -> None:
    config = load_config()
    logger = JsonLogger(config.log_level)
    server = build_server(config, logger)
    admin_server: AdminHTTPServer | None = None
    admin_thread: threading.Thread | None = None
    if config.admin_http_enabled:
        admin_server = build_admin_server(config, logger, server.state, server.redis_store)
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
