from __future__ import annotations

import io
import json
import hashlib
import hmac
import pathlib
import struct
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import hmock


def write_yaml(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def log_stream():
    return io.StringIO()


@pytest.fixture
def logger(log_stream):
    return hmock.JsonLogger("debug", stream=log_stream)


@pytest.fixture
def server_factory(logger):
    servers = []

    def start(behaviors, level="debug"):
        active_logger = logger if level == "debug" else hmock.JsonLogger(level, stream=io.StringIO())
        server = hmock.HMockHTTPServer(("127.0.0.1", 0), behaviors, active_logger)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server, f"http://127.0.0.1:{server.server_address[1]}"

    yield start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def admin_server_factory(logger):
    servers = []

    def start(templates_dir, redis_store=None, templates_dir_hot_reload=True, cors_enabled=False):
        config = hmock.Config(
            templates_dir=str(templates_dir),
            http_port=0,
            http_host="127.0.0.1",
            log_level="debug",
            admin_http_port=0,
            admin_http_host="127.0.0.1",
            templates_dir_hot_reload=templates_dir_hot_reload,
            cors_enabled=cors_enabled,
        )
        state = hmock.HMockRuntimeState.from_config(
            config,
            logger,
            redis_store or hmock.MemoryRedisStore(),
        )
        mock_server = hmock.HMockHTTPServer(("127.0.0.1", 0), state)
        admin_server = hmock.HMockAdminHTTPServer(("127.0.0.1", 0), state)
        mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
        admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        mock_thread.start()
        admin_thread.start()
        servers.append((mock_server, mock_thread))
        servers.append((admin_server, admin_thread))
        return (
            state,
            f"http://127.0.0.1:{mock_server.server_address[1]}",
            f"http://127.0.0.1:{admin_server.server_address[1]}",
        )

    yield start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(url, method="GET", body=None, headers=None):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()


def request_bytes(url, method="GET", body=None, headers=None):
    data = body if isinstance(body, bytes) else body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def json_request(url, method="GET", payload=None):
    body = json.dumps(payload) if payload is not None else None
    return request(url, method=method, body=body, headers={"Content-Type": "application/json"})


def start_capture_server():
    records = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _handle(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length).decode() if length else ""
            records.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": {key: value for key, value in self.headers.items()},
                    "body": body,
                }
            )
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_PUT(self):
            self._handle()

    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, records, f"http://127.0.0.1:{server.server_address[1]}"


def start_capture_bytes_server():
    records = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _handle(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            records.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": {key: value for key, value in self.headers.items()},
                    "body": body,
                }
            )
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            self._handle()

        def do_PUT(self):
            self._handle()

    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, records, f"http://127.0.0.1:{server.server_address[1]}"


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def behavior(raw, *args, **kwargs):
    return hmock.validate_behavior(raw, *args, **kwargs)


def proto_varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def proto_field(number, wire_type, value):
    tag = proto_varint((number << 3) | wire_type)
    if wire_type == 2:
        data = value.encode() if isinstance(value, str) else value
        return tag + proto_varint(len(data)) + data
    raise AssertionError(f"unsupported wire type {wire_type}")


def descriptor_set_bytes(package="demo", service="Echo", method="Ping"):
    method_proto = (
        proto_field(1, 2, method)
        + proto_field(2, 2, f".{package}.PingRequest")
        + proto_field(3, 2, f".{package}.PingResponse")
    )
    service_proto = proto_field(1, 2, service) + proto_field(2, 2, method_proto)
    file_proto = proto_field(1, 2, "echo.proto") + proto_field(2, 2, package) + proto_field(6, 2, service_proto)
    return proto_field(1, 2, file_proto)


def test_config_defaults_and_environment_overrides(monkeypatch):
    assert hmock.load_config({}) == hmock.Config()

    config = hmock.load_config(
        {
            "HM_TEMPLATES_DIR": "/tmp/mocks",
            "HM_HTTP_PORT": "7777",
            "HM_HTTP_HOST": "127.0.0.1",
            "HM_LOG_LEVEL": "warn",
            "HM_REDIS_TYPE": "redis",
            "HM_REDIS_URL": "redis://localhost:6380/2",
            "HM_ADMIN_HTTP_ENABLED": "false",
            "HM_ADMIN_HTTP_PORT": "7778",
            "HM_ADMIN_HTTP_HOST": "127.0.0.2",
            "HM_TEMPLATES_DIR_HOT_RELOAD": "false",
            "HM_CORS_ENABLED": "true",
        }
    )

    assert config == hmock.Config(
        templates_dir="/tmp/mocks",
        http_port=7777,
        http_host="127.0.0.1",
        log_level="warn",
        redis_type="redis",
        redis_url="redis://localhost:6380/2",
        admin_http_enabled=False,
        admin_http_port=7778,
        admin_http_host="127.0.0.2",
        templates_dir_hot_reload=False,
        cors_enabled=True,
    )

    assert hmock.load_config({"HM_ADMIN_HTTP_ENABLED": "0"}).admin_http_enabled is False
    assert hmock.load_config({"HM_ADMIN_HTTP_ENABLED": "no"}).admin_http_enabled is False
    assert hmock.load_config({"HM_ADMIN_HTTP_ENABLED": "off"}).admin_http_enabled is False
    assert hmock.load_config({}).templates_dir_hot_reload is True
    assert hmock.load_config({}).cors_enabled is False


def test_broker_config_defaults_overrides_and_sasl_enablement():
    defaults = hmock.load_config({})

    assert defaults.kafka_enabled is False
    assert defaults.kafka_client_id == "hmock"
    assert defaults.kafka_producer == hmock.KafkaClientConfig()
    assert defaults.kafka_consumer == hmock.KafkaClientConfig()
    assert defaults.amqp == hmock.AMQPConfig()

    config = hmock.load_config(
        {
            "HM_KAFKA_ENABLED": "true",
            "HM_KAFKA_CLIENT_ID": "custom-client",
            "HM_KAFKA_SEED_BROKERS": "shared-a:9092, shared-b:9092",
            "HM_KAFKA_SASL_USERNAME": "shared-user",
            "HM_KAFKA_SASL_PASSWORD": "shared-pass",
            "HM_KAFKA_TLS_ENABLED": "true",
            "HM_KAFKA_PRODUCER_SEED_BROKERS": "producer:9092",
            "HM_KAFKA_SASL_PRODUCER_USERNAME": "producer-user",
            "HM_KAFKA_SASL_PRODUCER_PASSWORD": "producer-pass",
            "HM_KAFKA_TLS_CONSUMER_ENABLED": "false",
            "HM_AMQP_ENABLED": "true",
        }
    )

    assert config.kafka_enabled is True
    assert config.kafka_client_id == "custom-client"
    assert config.kafka_producer == hmock.KafkaClientConfig(
        seed_brokers=("producer:9092",),
        sasl_username="producer-user",
        sasl_password="producer-pass",
        sasl_enabled=True,
        tls_enabled=True,
    )
    assert config.kafka_consumer == hmock.KafkaClientConfig(
        seed_brokers=("shared-a:9092", "shared-b:9092"),
        sasl_username="shared-user",
        sasl_password="shared-pass",
        sasl_enabled=True,
        tls_enabled=False,
    )
    assert config.amqp == hmock.AMQPConfig(enabled=True)

    no_sasl = hmock.load_config(
        {
            "HM_KAFKA_ENABLED": "true",
            "HM_KAFKA_SASL_USERNAME": "user-only",
        }
    )
    assert no_sasl.kafka_producer.sasl_enabled is False
    assert no_sasl.kafka_consumer.sasl_enabled is False


def test_grpc_config_defaults_overrides_and_schema_validation(tmp_path):
    defaults = hmock.load_config({})

    assert defaults.grpc == hmock.GRPCConfig()

    config = hmock.load_config(
        {
            "HM_GRPC_ENABLED": "true",
            "HM_GRPC_HOST": "127.0.0.1",
            "HM_GRPC_PORT": "6000",
            "HM_GRPC_DESCRIPTOR_SET_PATHS": "api.pb, nested/other.pb",
        }
    )

    assert config.grpc == hmock.GRPCConfig(
        enabled=True,
        host="127.0.0.1",
        port=6000,
        descriptor_set_paths=("api.pb", "nested/other.pb"),
    )

    payload_file = tmp_path / "reply.json"
    payload_file.write_text('{"ok":true}')
    grpc_behavior = behavior(
        {
            "key": "grpc",
            "expect": {"grpc": {"service": "demo.Echo", "method": "Ping"}},
            "actions": [
                {
                    "reply_grpc": {
                        "payload_from_file": "reply.json",
                        "headers": {"x-request-id": "{{ .GRPCHeader.Get \"x-request-id\" }}"},
                    }
                }
            ],
        },
        templates_dir=tmp_path,
    )

    assert grpc_behavior.grpc_service == "demo.Echo"
    assert grpc_behavior.grpc_method == "Ping"
    assert grpc_behavior.actions[0]["reply_grpc"]["reply_grpc_payload_from_file_content"] == '{"ok":true}'

    for raw in [
        {"key": "bad-grpc", "expect": {"grpc": {"method": "Ping"}}, "actions": []},
        {"key": "bad-grpc", "expect": {"grpc": {"service": "demo.Echo"}}, "actions": []},
        {"key": "bad-reply", "expect": {"grpc": {"service": "demo.Echo", "method": "Ping"}}, "actions": [{"reply_grpc": {}}]},
        {
            "key": "bad-header",
            "expect": {"grpc": {"service": "demo.Echo", "method": "Ping"}},
            "actions": [{"reply_grpc": {"payload": "{}", "headers": {"x": 1}}}],
        },
    ]:
        with pytest.raises(hmock.ValidationError):
            behavior(raw, templates_dir=tmp_path)

    existing_http = behavior(
        {"key": "http", "expect": {"http": {"method": "GET", "path": "/ok"}}, "actions": [{"reply_http": {"status_code": 200}}]}
    )
    assert existing_http.method == "GET"


def test_grpc_descriptor_resolution_registry_and_frames(tmp_path, logger):
    behavior_with_grpc = behavior(
        {
            "key": "grpc",
            "expect": {"grpc": {"service": "demo.Echo", "method": "Ping"}},
            "actions": [{"reply_grpc": {"payload": '{"message":"{{ .GRPCPayload }}"}'}}],
        }
    )
    no_grpc = behavior({"key": "http", "expect": {"http": {"method": "GET", "path": "/ok"}}, "actions": []})
    enabled_without_paths = hmock.Config(
        templates_dir=str(tmp_path),
        grpc=hmock.GRPCConfig(enabled=True),
    )

    with pytest.raises(hmock.ValidationError, match="HM_GRPC_DESCRIPTOR_SET_PATHS"):
        hmock.build_grpc_descriptor_registry(enabled_without_paths, [behavior_with_grpc])

    assert hmock.build_grpc_descriptor_registry(enabled_without_paths, [no_grpc])._methods == {}

    descriptor_path = tmp_path / "echo.pb"
    descriptor_path.write_bytes(descriptor_set_bytes())
    config = hmock.Config(
        templates_dir=str(tmp_path),
        grpc=hmock.GRPCConfig(enabled=True, descriptor_set_paths=("echo.pb",)),
    )
    resolved = hmock.resolve_grpc_descriptor_set_paths(config, [behavior_with_grpc])
    assert resolved == [descriptor_path]

    registry = hmock.build_grpc_descriptor_registry(config, [behavior_with_grpc])
    descriptor = registry.get_method("demo.Echo", "Ping")
    assert descriptor.request_type == "demo.PingRequest"
    assert descriptor.response_type == "demo.PingResponse"

    framed = hmock.encode_grpc_frame(b'{"hello":"world"}')
    assert hmock.decode_grpc_frame(framed) == b'{"hello":"world"}'
    assert framed[:5] == b"\x00" + struct.pack(">I", len(b'{"hello":"world"}'))
    assert registry.decode_request("demo.Echo", "Ping", framed) == '{"hello":"world"}'
    assert hmock.decode_grpc_frame(registry.encode_response("demo.Echo", "Ping", '{"ok":true}')) == b'{"ok":true}'

    bad_path = tmp_path / "bad.pb"
    bad_path.write_bytes(b"not a descriptor")
    bad_config = hmock.Config(
        templates_dir=str(tmp_path),
        grpc=hmock.GRPCConfig(enabled=True, descriptor_set_paths=("bad.pb",)),
    )
    with pytest.raises(hmock.ValidationError, match="invalid gRPC descriptor set"):
        hmock.build_grpc_descriptor_registry(bad_config, [behavior_with_grpc])


def test_recursive_yaml_loading_validation_order_and_duplicates(tmp_path, logger, log_stream):
    write_yaml(
        tmp_path / "a.yaml",
        """
- key: first
  expect:
    http:
      method: GET
      path: /first
  actions:
    - reply_http:
        status_code: 200
        body: first
- key: duplicate
  expect:
    http:
      method: GET
      path: /old
  actions:
    - reply_http:
        status_code: 200
""",
    )
    write_yaml(tmp_path / "ignored.txt", "- key: ignored")
    write_yaml(
        tmp_path / "nested" / "b.yml",
        """
- key: duplicate
  expect:
    http:
      method: GET
      path: /new
  actions:
    - reply_http:
        status_code: 201
- key: last
  expect:
    http:
      method: GET
      path: /last
  actions:
    - reply_http:
        status_code: 202
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)

    assert [b.key for b in behaviors] == ["first", "duplicate", "last"]
    assert behaviors[1].path == "/new"
    assert json.loads(log_stream.getvalue().strip())["level"] == "warn"


def test_persisted_templates_load_with_sets_isolation_and_last_wins(tmp_path, logger):
    write_yaml(
        tmp_path / "base.yaml",
        """
- key: duplicate
  expect:
    http:
      method: GET
      path: /duplicate
  actions:
    - reply_http:
        status_code: 200
        body: filesystem
""",
    )
    store = hmock.MemoryRedisStore()
    hmock.store_api_base_definitions(
        store,
        [
            {
                "key": "duplicate",
                "expect": {"http": {"method": "GET", "path": "/duplicate"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "api-base"}}],
            },
            {
                "key": "base-only",
                "expect": {"http": {"method": "GET", "path": "/base-only"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "base-only"}}],
            },
        ],
    )
    hmock.store_template_set_definitions(
        store,
        "b",
        [
            {
                "key": "duplicate",
                "expect": {"http": {"method": "GET", "path": "/duplicate"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "set-b"}}],
            }
        ],
    )
    hmock.store_template_set_definitions(
        store,
        "a",
        [
            {
                "key": "set-a",
                "expect": {"http": {"method": "GET", "path": "/set-a"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "set-a"}}],
            }
        ],
    )

    config = hmock.Config(templates_dir=str(tmp_path))
    state = hmock.HMockRuntimeState.from_config(config, logger, store)

    request_info = hmock.RequestInfo("GET", "/duplicate", "/duplicate", "", "", {}, "")
    behavior, params = hmock.find_behavior(state.get_behaviors(), request_info, store)
    assert hmock.execute_behavior(behavior, request_info, params, store).body == "set-b"
    assert [raw["key"] for raw in state.get_definitions()] == ["base-only", "set-a", "duplicate"]

    hmock.delete_template_set_definitions(store, "b")
    state.reload(skip_invalid_persisted=False)
    behavior, params = hmock.find_behavior(state.get_behaviors(), request_info, store)
    assert hmock.execute_behavior(behavior, request_info, params, store).body == "api-base"
    assert [raw["key"] for raw in state.get_definitions()] == ["duplicate", "base-only", "set-a"]


def test_invalid_persisted_definitions_are_skipped_on_startup(tmp_path, logger):
    store = hmock.MemoryRedisStore()
    hmock.store_api_base_definitions(store, [{"key": "bad", "expect": {"http": {"method": "GET"}}}])

    state = hmock.HMockRuntimeState.from_config(hmock.Config(templates_dir=str(tmp_path)), logger, store)

    assert state.get_behaviors() == []
    assert state.get_definitions() == []


def test_admin_template_endpoints_persist_reload_and_preserve_filesystem(tmp_path, admin_server_factory):
    write_yaml(
        tmp_path / "fs.yaml",
        """
- key: fs
  expect:
    http:
      method: GET
      path: /fs
  actions:
    - reply_http:
        status_code: 200
        body: filesystem
""",
    )
    store = hmock.MemoryRedisStore()
    _, mock_base, admin_base = admin_server_factory(tmp_path, store)

    assert json_request(admin_base + "/api/v1/health")[0::2] == (200, '{"status":"OK"}')
    status, _, body = json_request(admin_base + "/api/v1/templates")
    assert status == 200
    assert [raw["key"] for raw in json.loads(body)] == ["fs"]

    api_mock = {
        "key": "api",
        "expect": {"http": {"method": "GET", "path": "/api"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", "POST", [api_mock])[0::2] == (
        200,
        json.dumps([api_mock], separators=(",", ":")),
    )
    assert request(mock_base + "/api")[0::2] == (200, "api")

    replacement = {
        "key": "fs",
        "expect": {"http": {"method": "GET", "path": "/fs"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "api-overrode-fs"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", "POST", [replacement])[0] == 200
    assert request(mock_base + "/fs")[0::2] == (200, "api-overrode-fs")
    assert request(admin_base + "/api/v1/templates/fs", method="DELETE")[0] == 204
    assert request(mock_base + "/fs")[0::2] == (200, "filesystem")
    assert request(admin_base + "/api/v1/templates/missing", method="DELETE")[0] == 404

    state_after_restart = hmock.HMockRuntimeState.from_config(
        hmock.Config(templates_dir=str(tmp_path)),
        hmock.JsonLogger("debug", stream=io.StringIO()),
        store,
    )
    assert [raw["key"] for raw in state_after_restart.get_definitions()] == ["fs", "api"]

    assert request(admin_base + "/api/v1/templates", method="DELETE")[0] == 204
    assert request(mock_base + "/api")[0::2] == (404, "not found")
    assert request(mock_base + "/fs")[0::2] == (200, "filesystem")


def test_admin_template_sets_are_replaced_deleted_and_isolated(tmp_path, admin_server_factory):
    _, mock_base, admin_base = admin_server_factory(tmp_path)
    set_a = [
        {
            "key": "set-a",
            "expect": {"http": {"method": "GET", "path": "/set-a"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "set-a"}}],
        }
    ]
    set_b = [
        {
            "key": "set-b",
            "expect": {"http": {"method": "GET", "path": "/set-b"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "set-b"}}],
        }
    ]

    assert json_request(admin_base + "/api/v1/template_sets/a", "POST", set_a)[0] == 200
    assert json_request(admin_base + "/api/v1/template_sets/b", "POST", set_b)[0] == 200
    assert request(mock_base + "/set-a")[0::2] == (200, "set-a")
    assert request(mock_base + "/set-b")[0::2] == (200, "set-b")

    assert request(admin_base + "/api/v1/template_sets/a", method="DELETE")[0] == 204
    assert request(mock_base + "/set-a")[0::2] == (404, "not found")
    assert request(mock_base + "/set-b")[0::2] == (200, "set-b")


def test_admin_accepts_yaml_template_uploads(tmp_path, admin_server_factory):
    _, mock_base, admin_base = admin_server_factory(tmp_path)
    status, _, body = request(
        admin_base + "/api/v1/templates",
        method="POST",
        body="""
- key: yaml-api
  expect:
    http:
      method: GET
      path: /yaml-api
  actions:
    - reply_http:
        status_code: 200
        body: yaml-ok
""",
        headers={"Content-Type": "application/yaml"},
    )

    assert status == 200
    assert json.loads(body)[0]["key"] == "yaml-api"
    assert request(mock_base + "/yaml-api")[0::2] == (200, "yaml-ok")


def test_omctl_push_loads_yaml_recursively_and_routes_to_admin_api(tmp_path, monkeypatch):
    demo = tmp_path / "demo_templates"
    write_yaml(
        demo / "base.yaml",
        """
- key: base
  expect:
    http:
      method: GET
      path: /base
  actions:
    - reply_http:
        status_code: 200
""",
    )
    write_yaml(
        demo / "nested" / "set.yml",
        """
- key: nested
  expect:
    http:
      method: GET
      path: /nested
  actions:
    - reply_http:
        status_code: 201
""",
    )
    calls = []

    def fake_request(url, method, body=None, headers=None):
        calls.append((url, method, body, headers))
        return 200

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hmock, "_omctl_request", fake_request)

    assert hmock.omctl_main(["push"]) == 0
    url, method, body, headers = calls[0]
    assert (url, method, headers["Content-Type"]) == (
        "http://localhost:9998/api/v1/templates",
        "POST",
        "application/yaml",
    )
    assert [raw["key"] for raw in json.loads(body.decode())] == ["base", "nested"]


def test_omctl_push_set_key_and_delete_short_aliases(tmp_path, monkeypatch):
    templates = tmp_path / "templates"
    write_yaml(
        templates / "one.yaml",
        """
- key: one
  expect:
    http:
      method: GET
      path: /one
  actions:
    - reply_http:
        status_code: 200
""",
    )
    calls = []

    def fake_request(url, method, body=None, headers=None):
        calls.append((url, method, body, headers))
        return 204 if method == "DELETE" else 200

    monkeypatch.setattr(hmock, "_omctl_request", fake_request)

    assert hmock.omctl_main(["push", "-d", str(templates), "-u", "http://admin.test/", "-k", "alpha"]) == 0
    assert calls[0][0:2] == ("http://admin.test/api/v1/template_sets/alpha", "POST")
    assert hmock.omctl_main(["delete", "-u", "http://admin.test", "-k", "alpha"]) == 0
    assert calls[1][0:2] == ("http://admin.test/api/v1/template_sets/alpha", "DELETE")

    with pytest.raises(SystemExit):
        hmock.omctl_main(["delete", "-u", "http://admin.test"])


def test_templates_hot_reload_tracks_creates_edits_and_deletes(tmp_path, admin_server_factory):
    _, mock_base, _ = admin_server_factory(tmp_path)

    assert request(mock_base + "/hot")[0::2] == (404, "not found")
    template = tmp_path / "hot.yaml"
    write_yaml(
        template,
        """
- key: hot
  expect:
    http:
      method: GET
      path: /hot
  actions:
    - reply_http:
        status_code: 200
        body: first
""",
    )
    assert request(mock_base + "/hot")[0::2] == (200, "first")

    write_yaml(
        template,
        """
- key: hot
  expect:
    http:
      method: GET
      path: /hot
  actions:
    - reply_http:
        status_code: 200
        body: second-value
""",
    )
    assert request(mock_base + "/hot")[0::2] == (200, "second-value")

    template.unlink()
    assert request(mock_base + "/hot")[0::2] == (404, "not found")


def test_templates_hot_reload_can_be_disabled_while_admin_reload_still_applies(tmp_path, admin_server_factory):
    write_yaml(
        tmp_path / "snapshot.yaml",
        """
- key: snapshot
  expect:
    http:
      method: GET
      path: /snapshot
  actions:
    - reply_http:
        status_code: 200
        body: original
""",
    )
    _, mock_base, admin_base = admin_server_factory(tmp_path, templates_dir_hot_reload=False)

    assert request(mock_base + "/snapshot")[0::2] == (200, "original")
    write_yaml(
        tmp_path / "snapshot.yaml",
        """
- key: snapshot
  expect:
    http:
      method: GET
      path: /snapshot
  actions:
    - reply_http:
        status_code: 200
        body: edited-value
""",
    )
    assert request(mock_base + "/snapshot")[0::2] == (200, "original")

    api_mock = {
        "key": "api",
        "expect": {"http": {"method": "GET", "path": "/api-hot-disabled"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "api-visible"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", "POST", [api_mock])[0] == 200
    assert request(mock_base + "/api-hot-disabled")[0::2] == (200, "api-visible")


def test_cors_headers_preflight_and_mock_header_precedence(tmp_path, admin_server_factory):
    write_yaml(
        tmp_path / "cors.yaml",
        """
- key: cors
  expect:
    http:
      method: GET
      path: /cors
  actions:
    - reply_http:
        status_code: 200
        body: cors
        headers:
          Access-Control-Allow-Origin: https://example.test
- key: options
  expect:
    http:
      method: OPTIONS
      path: /explicit
  actions:
    - reply_http:
        status_code: 202
        body: explicit
""",
    )
    _, mock_base, _ = admin_server_factory(tmp_path, cors_enabled=True)

    status, headers, body = request(mock_base + "/cors")
    assert (status, body) == (200, "cors")
    assert headers["Access-Control-Allow-Origin"] == "https://example.test"
    assert headers["Access-Control-Allow-Methods"] == "*"
    assert headers["Access-Control-Allow-Headers"] == "*"
    assert headers["Access-Control-Allow-Credentials"] == "true"

    status, headers, body = request(mock_base + "/missing")
    assert (status, body) == (404, "not found")
    assert headers["Access-Control-Allow-Origin"] == "*"

    status, headers, body = request(mock_base + "/explicit", method="OPTIONS")
    assert (status, body) == (202, "explicit")
    assert headers["Access-Control-Allow-Origin"] == "*"

    status, headers, body = request(mock_base + "/preflight", method="OPTIONS")
    assert (status, body) == (200, "")
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_unmatched_options_without_cors_uses_normal_not_found(tmp_path, admin_server_factory):
    _, mock_base, _ = admin_server_factory(tmp_path, cors_enabled=False)

    status, headers, body = request(mock_base + "/preflight", method="OPTIONS")

    assert (status, body) == (404, "not found")
    assert "Access-Control-Allow-Origin" not in headers


def test_admin_invalid_submission_returns_400_and_does_not_persist(tmp_path, admin_server_factory):
    _, mock_base, admin_base = admin_server_factory(tmp_path)
    valid = {
        "key": "valid",
        "expect": {"http": {"method": "GET", "path": "/valid"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "valid"}}],
    }

    assert json_request(admin_base + "/api/v1/templates", "POST", [valid])[0] == 200
    status, _, body = json_request(admin_base + "/api/v1/templates", "POST", [{"key": "bad"}])

    assert status == 400
    assert "error" in json.loads(body)
    assert request(mock_base + "/valid")[0::2] == (200, "valid")
    status, _, body = json_request(admin_base + "/api/v1/templates")
    assert status == 200
    assert [raw["key"] for raw in json.loads(body)] == ["valid"]


def test_validation_rejects_missing_empty_keys_and_multiple_replies():
    valid = {
        "key": "default-kind",
        "expect": {"http": {"method": "GET", "path": "/x"}},
        "actions": [{"reply_http": {"status_code": 200}}],
    }
    assert hmock.validate_behavior(valid).kind == "Behavior"

    for raw in ({}, {"key": ""}, {"key": 1}):
        with pytest.raises(hmock.ValidationError):
            hmock.validate_behavior(raw)

    with pytest.raises(hmock.ValidationError):
        hmock.validate_behavior(
            {
                "key": "twice",
                "expect": {"http": {"method": "GET", "path": "/x"}},
                "actions": [
                    {"reply_http": {"status_code": 200}},
                    {"reply_http": {"status_code": 201}},
                ],
            }
        )


def test_kind_field_values_and_action_order_validation(tmp_path, logger):
    write_yaml(
        tmp_path / "defs.yaml",
        """
- key: body-template
  kind: Template
  template: >
    value {{ .value }}
- key: abstract-base
  kind: AbstractBehavior
  values:
    value: base
  expect:
    http:
      method: GET
      path: /base
  actions:
    - reply_http:
        status_code: 200
- key: concrete
  values:
    value: child
  expect:
    http:
      method: GET
      path: /concrete
  actions:
    - order: -1
      redis:
        - SET seen yes
    - reply_http:
        status_code: 200
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)

    assert [b.key for b in behaviors] == ["concrete"]
    assert behaviors[0].values == {"value": "child"}
    assert behaviors[0].templates == {"body-template": "value {{ .value }}"}
    assert [next(key for key in action if key != "order") for action in behaviors[0].actions] == ["redis", "reply_http"]

    invalid_definitions = [
        "- key: nope\n  kind: Nope\n",
        "- key: bad-template\n  kind: Template\n  template: ok\n  expect: {}\n",
        "- key: bad-behavior\n  kind: Behavior\n  template: nope\n",
        "- key: bad-abstract\n  kind: AbstractBehavior\n  extend: other\n",
        "- key: bad-values\n  kind: Behavior\n  values: nope\n",
        """
- key: bad-order
  expect:
    http:
      method: GET
      path: /bad
  actions:
    - order: soon
      reply_http:
        status_code: 200
""",
        """
- key: too-many-actions
  expect:
    http:
      method: GET
      path: /bad
  actions:
    - order: 1
      redis:
        - SET a b
      reply_http:
        status_code: 200
""",
    ]
    for index, text in enumerate(invalid_definitions):
        invalid_dir = tmp_path / f"invalid-{index}"
        write_yaml(invalid_dir / "bad.yaml", text)
        with pytest.raises(hmock.ValidationError):
            hmock.load_behaviors(invalid_dir, logger)


def test_behavior_inheritance_merges_values_expect_actions_and_detects_cycles(tmp_path, logger):
    write_yaml(
        tmp_path / "defs.yaml",
        """
- key: purple-teapot
  kind: Behavior
  extend: teapot
  values:
    color: purple
  expect:
    http:
      path: /purple
  actions:
    - order: -10
      redis:
        - SET color "{{ .Values.color }}"
- key: teapot
  kind: AbstractBehavior
  values:
    color: blue
    size: large
  expect:
    condition: '{{ .HTTPHeader.Get "X-Token" | eq .Values.token }}'
    http:
      method: GET
      path: /teapot
  actions:
    - reply_http:
        status_code: 418
        body: '{{ .Values.color }} {{ .Values.size }}'
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)

    assert len(behaviors) == 1
    behavior = behaviors[0]
    assert behavior.key == "purple-teapot"
    assert behavior.method == "GET"
    assert behavior.path == "/purple"
    assert behavior.condition == '{{ .HTTPHeader.Get "X-Token" | eq .Values.token }}'
    assert behavior.values == {"color": "purple", "size": "large"}
    assert [next(key for key in action if key != "order") for action in behavior.actions] == ["redis", "reply_http"]

    write_yaml(
        tmp_path / "missing-parent.yaml",
        """
- key: standalone
  extend: missing
  expect:
    http:
      method: GET
      path: /standalone
  actions:
    - reply_http:
        status_code: 200
""",
    )
    assert [b.key for b in hmock.load_behaviors(tmp_path, logger)] == ["purple-teapot", "standalone"]

    incomplete_dir = tmp_path / "incomplete"
    write_yaml(
        incomplete_dir / "bad.yaml",
        """
- key: incomplete
  extend: missing
  actions:
    - reply_http:
        status_code: 200
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(incomplete_dir, logger)

    cycle_dir = tmp_path / "cycle"
    write_yaml(
        cycle_dir / "cycle.yaml",
        """
- key: a
  extend: b
  expect:
    http:
      method: GET
      path: /a
  actions:
    - reply_http:
        status_code: 200
- key: b
  extend: a
  expect:
    http:
      method: GET
      path: /b
  actions:
    - reply_http:
        status_code: 200
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(cycle_dir, logger)


def test_stateful_action_validation_and_send_http_body_file_snapshot(tmp_path, logger):
    body_file = tmp_path / "callbacks" / "body.txt"
    body_file.parent.mkdir()
    body_file.write_text("callback {{ .HTTPBody }}")
    write_yaml(
        tmp_path / "stateful.yaml",
        """
- key: stateful
  expect:
    http:
      method: POST
      path: /stateful
  actions:
    - redis:
        - SET seen yes
        - RPUSH queue '{{ .HTTPBody }}'
    - send_http:
        url: http://127.0.0.1:9999/callback
        method: POST
        body_from_file: callbacks/body.txt
        headers:
          X-Seen: '{{ redisDo "GET seen" }}'
    - reply_http:
        status_code: 200
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    body_file.write_text("changed")

    assert behaviors[0].actions[0]["redis"] == ["SET seen yes", "RPUSH queue '{{ .HTTPBody }}'"]
    payload = behaviors[0].actions[1]["send_http"]
    assert payload["send_http_body_from_file_content"] == "callback {{ .HTTPBody }}"

    invalid_actions = [
        {"redis": {"command": "SET a b"}},
        {"redis": ["SET a b", 1]},
        {"send_http": {"method": "POST"}},
        {"send_http": {"url": "http://example.test"}},
        {"send_http": {"url": "http://example.test", "method": "POST", "headers": {"X-Bad": 1}}},
    ]
    for action in invalid_actions:
        with pytest.raises(hmock.ValidationError):
            hmock.validate_behavior(
                {
                    "key": "bad",
                    "expect": {"http": {"method": "GET", "path": "/bad"}},
                    "actions": [action],
                }
            )

    write_yaml(
        tmp_path / "missing-callback.yaml",
        """
- key: missing-callback
  expect:
    http:
      method: GET
      path: /missing-callback
  actions:
    - send_http:
        url: http://127.0.0.1:9999/callback
        method: POST
        body_from_file: callbacks/missing.txt
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_broker_validation_queue_defaults_and_payload_file_snapshot(tmp_path, logger):
    payload_file = tmp_path / "payloads" / "event.txt"
    payload_file.parent.mkdir()
    payload_file.write_text("payload {{ .KafkaPayload }} {{ .AMQPPayload }}")
    write_yaml(
        tmp_path / "brokers.yaml",
        """
- key: kafka-behavior
  expect:
    kafka:
      topic: input-topic
  actions:
    - publish_kafka:
        topic: output-topic
        payload_from_file: payloads/event.txt
- key: amqp-behavior
  expect:
    amqp:
      exchange: events
      routing_key: user.created
      queue: ""
  actions:
    - publish_amqp:
        exchange: out
        routing_key: rendered
        payload_from_file: payloads/event.txt
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    payload_file.write_text("changed")

    assert behaviors[0].kafka_topic == "input-topic"
    assert behaviors[0].actions[0]["publish_kafka"]["publish_kafka_payload_from_file_content"] == (
        "payload {{ .KafkaPayload }} {{ .AMQPPayload }}"
    )
    assert behaviors[1].amqp_exchange == "events"
    assert behaviors[1].amqp_routing_key == "user.created"
    assert behaviors[1].amqp_queue == "user.created"
    assert behaviors[1].actions[0]["publish_amqp"]["publish_amqp_payload_from_file_content"] == (
        "payload {{ .KafkaPayload }} {{ .AMQPPayload }}"
    )

    invalid_definitions = [
        {"key": "missing-topic", "expect": {"kafka": {}}, "actions": []},
        {"key": "bad-amqp", "expect": {"amqp": {"exchange": "events"}}, "actions": []},
        {
            "key": "missing-kafka-payload",
            "expect": {"kafka": {"topic": "events"}},
            "actions": [{"publish_kafka": {"topic": "out"}}],
        },
        {
            "key": "missing-amqp-payload",
            "expect": {"amqp": {"exchange": "e", "routing_key": "r"}},
            "actions": [{"publish_amqp": {"exchange": "out", "routing_key": "r"}}],
        },
    ]
    for raw in invalid_definitions:
        with pytest.raises(hmock.ValidationError):
            hmock.validate_behavior(raw)

    write_yaml(
        tmp_path / "missing-payload.yaml",
        """
- key: missing-payload
  expect:
    kafka:
      topic: events
  actions:
    - publish_kafka:
        topic: out
        payload_from_file: payloads/missing.txt
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_broker_payload_files_reject_paths_outside_templates_dir(tmp_path, logger):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside")
    write_yaml(
        tmp_path / "outside.yaml",
        f"""
- key: outside-kafka-payload
  expect:
    kafka:
      topic: events
  actions:
    - publish_kafka:
        topic: out
        payload_from_file: ../{outside.name}
""",
    )

    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_template_context_preprocessing_syntax_and_strict_errors(monkeypatch):
    monkeypatch.setenv("HM_TEST_VALUE", "from-env")
    ctx = hmock.build_template_context(
        {"X-Token": "t1234"},
        "hello",
        "/api/42?foo=bar",
        "foo=bar",
        {"id": "42"},
    )
    ctx["Collection"] = ["a", "b"]

    assert hmock.render_template('{{ .HTTPHeader.Get "x-token" }}', ctx) == "t1234"
    assert hmock.render_template("{{ .HTTPBody }} {{ .HTTPPath }} {{ .HTTPQueryString }}", ctx) == "hello /api/42?foo=bar foo=bar"
    assert hmock.render_template('{{ .HTTPPathParams.Get "id" }}', ctx) == "42"
    assert hmock.render_template("a\r\n{{\t.HTTPBody\n}}\tb", ctx) == "a hello b"
    assert hmock.render_template("{{ .HTTPBody | upper }}", ctx) == "HELLO"
    assert hmock.render_template('{{ if eq .HTTPBody "hello" }}yes{{ else }}no{{ end }}', ctx) == "yes"
    assert hmock.render_template("{{ range $i, $v := .Collection }}{{ $i }}:{{ $v }};{{ end }}", ctx) == "0:a;1:b;"
    assert hmock.render_template("{{ $x := .HTTPBody }}{{ $x | title }}", ctx) == "Hello"
    assert hmock.render_template("{{ `literal text` }}", ctx) == "literal text"
    assert hmock.render_template("{{- .HTTPBody -}}", ctx) == "hello"

    with pytest.raises(hmock.TemplateError):
        hmock.render_template("{{ .Missing }}", ctx)


def test_template_builtin_and_extended_functions(monkeypatch):
    monkeypatch.setenv("HM_FUNC_VALUE", "env-value")
    ctx = hmock.build_template_context({}, "", "/", "", {})
    ctx["Items"] = ["x", "y"]
    ctx["Fn"] = lambda value: f"called-{value}"

    assert hmock.render_template('{{ eq 2 2 }} {{ ne 2 3 }} {{ lt 1 2 }} {{ gt 2 1 }} {{ le 2 2 }} {{ ge 2 2 }}', ctx) == "true true true true true true"
    assert hmock.render_template("{{ and true true }} {{ or false true }} {{ not false }}", ctx) == "true true true"
    assert hmock.render_template('{{ print "a" "b" }} {{ printf "%s-%s" "a" "b" }}', ctx) == "ab a-b"
    assert hmock.render_template('{{ html "<x>" }} {{ js "a\\b" }} {{ urlquery "a b" }}', ctx) == "&lt;x&gt; a\\\\b a+b"
    assert hmock.render_template('{{ len .Items }} {{ index .Items 1 }} {{ call .Fn "ok" }}', ctx) == "2 y called-ok"
    assert hmock.render_template('{{ contains "ell" "hello" }} {{ hasPrefix "he" "hello" }} {{ hasSuffix "lo" "hello" }}', ctx) == "true true true"
    assert hmock.render_template('{{ replace "l" "x" "hello" }} {{ trim " hi " }} {{ lower "HI" }} {{ split "," "a,b" | join "-" }}', ctx) == "hexxo hi hi a-b"
    assert hmock.render_template('{{ repeat 3 "ha" }} {{ nospace "a b c" }} {{ toString 12 }}', ctx) == "hahaha abc 12"
    assert hmock.render_template('{{ default "fallback" "" }} {{ empty "" }} {{ coalesce "" "ok" }} {{ ternary "yes" "no" true }}', ctx) == "fallback true ok yes"
    assert hmock.render_template('{{ b64enc "hi" | b64dec }} {{ env "HM_FUNC_VALUE" }}', ctx) == "hi env-value"
    assert hmock.render_template("{{ add 1 2 3 }} {{ sub 10 3 }} {{ mul 2 3 }} {{ div 8 2 }} {{ mod 7 4 }} {{ max 1 9 3 }} {{ min 1 9 3 }}", ctx) == "6 7 6 4 3 9 1"

    generated = hmock.render_template("{{ uuidv4 }}", ctx)
    assert len(generated) == 36


def test_template_rich_helper_functions():
    ctx = hmock.build_template_context(
        {},
        '{"foo":"bar","context":{"type":"event"},"items":[{"id":"a"},{"id":"b"}],"nested":{"bar":"deep"}}',
        "/",
        "",
        {},
    )
    ctx["XML"] = "<root><user><name>Ada</name></user></root>"
    ctx["Items"] = ["x", "y"]
    ctx["HTML"] = "<tag>&'\""

    assert hmock.render_template('{{ jsonPath "foo" .HTTPBody }} {{ jsonPath "//bar" .HTTPBody }}', ctx) == "bar deep"
    assert hmock.render_template('{{ gJsonPath "context.type" .HTTPBody }} {{ gJsonPath "items.0.id" .HTTPBody }}', ctx) == "event a"
    assert hmock.render_template('{{ gJsonPath "items.#.id" .HTTPBody }} {{ gJsonPath "items.#" .HTTPBody }}', ctx) == '["a","b"] 2'
    assert hmock.render_template('{{ xmlPath "//name" .XML }}', ctx) == "Ada"

    first_uuid = hmock.render_template('{{ uuidv5 "stable-input" }}', ctx)
    second_uuid = hmock.render_template('{{ uuidv5 "stable-input" }}', ctx)
    assert first_uuid == second_uuid
    assert len(first_uuid) == 36

    assert hmock.render_template('{{ $m := regexFindAllSubmatch "([a-z]+)-([0-9]+)" "abc-123" }}{{ index $m 0 }} {{ index $m 1 }} {{ index $m 2 }}', ctx) == "abc-123 abc 123"
    assert hmock.render_template('{{ regexFindFirstSubmatch "id=([0-9]+)" "id=42" }}', ctx) == "42"
    assert hmock.render_template('{{ regexFindFirstSubmatch "id=[0-9]+" "id=42" }}', ctx) == ""

    expected_hmac = hmac.new(b"secret", b"data", hashlib.sha256).hexdigest()
    assert hmock.render_template('{{ hmacSHA256 "secret" "data" }}', ctx) == expected_hmac
    assert hmock.render_template("{{ isLastIndex 1 .Items }} {{ isLastIndex 0 .Items }}", ctx) == "true false"
    assert hmock.render_template("{{ htmlEscapeString .HTML }}", ctx) == "&lt;tag&gt;&amp;&#x27;&quot;"


def test_template_path_helpers_empty_no_match_and_invalid_json():
    ctx = hmock.build_template_context({}, "", "/", "", {})
    ctx["JSON"] = '{"items":[{"id":"a"}]}'
    ctx["XML"] = "<root><item>A</item></root>"
    ctx["BadJSON"] = "not-json"

    assert hmock.render_template('{{ jsonPath "missing" .JSON }}x{{ jsonPath "foo" .HTTPBody }}', ctx) == "x"
    assert hmock.render_template('{{ gJsonPath "items.9.id" .JSON }}x{{ gJsonPath "foo" .HTTPBody }}', ctx) == "x"
    assert hmock.render_template('{{ xmlPath "//missing" .XML }}x{{ xmlPath "//item" .HTTPBody }}', ctx) == "x"

    with pytest.raises(hmock.TemplateError):
        hmock.render_template('{{ gJsonPath "foo" .BadJSON }}', ctx)


def test_memory_redis_store_commands_and_return_formatting():
    store = hmock.MemoryRedisStore()

    assert store.do("SET name Ada") == "OK"
    assert store.do("GET name") == "Ada"
    assert store.do("GET missing") == ""
    assert store.do("RPUSH queue a b") == "2"
    assert store.do("LPUSH queue first") == "3"
    assert store.do("LRANGE queue 0 -1") == "first;;a;;b"
    assert store.do("LPOP queue") == "first"
    assert store.do("RPOP queue") == "b"
    assert store.do("HSET user name Ada role admin") == "2"
    assert store.do("HGET user role") == "admin"
    assert store.do("HGETALL user") == "name;;Ada;;role;;admin"
    assert store.do("HDEL user role missing") == "1"
    assert store.do("EXISTS name queue missing") == "2"
    assert store.do("KEYS q*") == "queue"
    assert store.do("DEL name queue user") == "3"
    assert store.do("EXISTS name queue user") == "0"

    with pytest.raises(hmock.RedisError):
        store.do("NOPE key")
    with pytest.raises(hmock.RedisError):
        store.do("GET")


def test_redis_do_template_function_and_split_list():
    store = hmock.MemoryRedisStore()
    ctx = hmock.build_template_context({}, "", "/", "", {}, hmock.user_redis_do(store))

    assert hmock.render_template('{{ redisDo "SET color blue" }}', ctx) == "OK"
    assert hmock.render_template('{{ redisDo "GET color" }}', ctx) == "blue"
    assert hmock.render_template('{{ redisDo "RPUSH letters a b c" }}', ctx) == "3"
    assert hmock.render_template('{{ range $i, $v := redisDo "LRANGE letters 0 -1" | splitList ";;" }}{{ $v }}{{ end }}', ctx) == "abc"


def test_redis_do_blocks_internal_keyspace_without_executing():
    store = hmock.MemoryRedisStore()
    ctx = hmock.build_template_context({}, "", "/", "", {}, hmock.user_redis_do(store))

    with pytest.raises(hmock.RedisError):
        hmock.render_template('{{ redisDo "SET __hmock_internal:templates touched" }}', ctx)
    with pytest.raises(hmock.RedisError):
        hmock.render_template('{{ redisDo "GET __hmock_internal:template_sets:a" }}', ctx)
    with pytest.raises(hmock.RedisError):
        hmock.render_template('{{ redisDo "KEYS *" }}', ctx)

    assert store.do("GET __hmock_internal:templates") == ""
    assert hmock.render_template('{{ redisDo "SET public-key ok" }} {{ redisDo "GET public-key" }}', ctx) == "OK ok"


def test_redis_action_blocks_internal_keyspace_as_template_render_error(server_factory):
    store = hmock.MemoryRedisStore()
    behaviors = [
        hmock.validate_behavior(
            {
                "key": "blocked",
                "expect": {"http": {"method": "GET", "path": "/blocked"}},
                "actions": [
                    {"redis": ["SET __hmock_internal:template_sets:a touched"]},
                    {"reply_http": {"status_code": 200, "body": "should-not-render"}},
                ],
            }
        )
    ]
    server, base = server_factory(behaviors)
    server.runtime_state.redis_store = store

    assert request(base + "/blocked")[0::2] == (500, "template render error")
    assert store.do("GET __hmock_internal:template_sets:a") == ""


def test_values_and_named_templates_render_everywhere(tmp_path, logger, server_factory):
    target, target_thread, records, target_base = start_capture_server()
    try:
        write_yaml(
            tmp_path / "values.yaml",
            f"""
- key: color-template
  kind: Template
  template: '{{{{ .color }}}}:{{{{ .size }}}}'
- key: path-template
  kind: Template
  template: '{{{{ .HTTPPath }}}}'
- key: values-everywhere
  values:
    color: purple
    size: large
    token: t123
  expect:
    condition: '{{{{ .HTTPHeader.Get "X-Token" | eq .Values.token }}}}'
    http:
      method: POST
      path: /values
  actions:
    - redis:
        - SET color "{{{{ .Values.color }}}}"
    - send_http:
        url: {target_base}/callback/{{{{ .Values.color }}}}
        method: POST
        body: '{{{{ template "color-template" .Values }}}}'
        headers:
          X-Color: '{{{{ .Values.color }}}}'
    - reply_http:
        status_code: 200
        headers:
          X-Path: '{{{{ template "path-template" . }}}}'
        body: '{{{{ redisDo "GET color" }}}} {{{{ template "color-template" .Values }}}}'
""",
        )
        _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

        assert request(base + "/values", method="POST", headers={"X-Token": "bad"})[0::2] == (404, "not found")
        status, headers, body = request(base + "/values?x=1", method="POST", headers={"X-Token": "t123"})
    finally:
        stop_server(target, target_thread)

    assert (status, body) == (200, "purple purple:large")
    assert headers["X-Path"] == "/values?x=1"
    assert len(records) == 1
    assert records[0]["path"] == "/callback/purple"
    assert records[0]["headers"]["X-Color"] == "purple"
    assert records[0]["body"] == "purple:large"

    ctx = hmock.build_template_context({}, "", "/", "", {}, templates={})
    with pytest.raises(hmock.TemplateError):
        hmock.render_template('{{ template "missing" . }}', ctx)


def test_body_from_file_loading_validation_and_snapshot(tmp_path, logger):
    body_file = tmp_path / "responses" / "body.txt"
    body_file.parent.mkdir()
    body_file.write_text("original {{ .HTTPBody }}")
    write_yaml(
        tmp_path / "body.yaml",
        """
- key: file-body
  expect:
    http:
      method: POST
      path: /file
  actions:
    - reply_http:
        status_code: 200
        body_from_file: responses/body.txt
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    body_file.write_text("changed")

    payload = behaviors[0].actions[0]["reply_http"]
    assert payload["body_from_file_content"] == "original {{ .HTTPBody }}"

    request_info = hmock.RequestInfo("POST", "/file", "/file", "", "", {}, "payload")
    response = hmock.execute_behavior(behaviors[0], request_info, {})
    assert response.body == "original payload"

    write_yaml(
        tmp_path / "missing.yaml",
        """
- key: missing-body
  expect:
    http:
      method: GET
      path: /missing
  actions:
    - reply_http:
        status_code: 200
        body_from_file: responses/missing.txt
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_body_from_file_rejects_paths_outside_templates_dir(tmp_path, logger):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside")
    write_yaml(
        tmp_path / "outside.yaml",
        f"""
- key: outside-body
  expect:
    http:
      method: GET
      path: /outside
  actions:
    - reply_http:
        status_code: 200
        body_from_file: ../{outside.name}
""",
    )

    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_binary_reply_http_snapshot_headers_and_precedence(tmp_path, logger, server_factory):
    binary_file = tmp_path / "responses" / "image.bin"
    binary_file.parent.mkdir()
    binary_file.write_bytes(b"\x00{{ raw }}\xff")
    write_yaml(
        tmp_path / "binary.yaml",
        """
- key: binary
  expect:
    http:
      method: GET
      path: /binary
  actions:
    - reply_http:
        status_code: 200
        body_from_binary_file: responses/image.bin
        binary_file_name: image.bin
- key: text-wins
  expect:
    http:
      method: GET
      path: /text-wins
  actions:
    - reply_http:
        status_code: 200
        body: text
        body_from_binary_file: responses/image.bin
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    binary_file.write_bytes(b"changed")
    _, base = server_factory(behaviors)

    status, headers, body = request_bytes(base + "/binary")
    assert status == 200
    assert body == b"\x00{{ raw }}\xff"
    assert headers["Content-Length"] == str(len(body))
    assert headers["Content-Disposition"] == 'inline; filename="image.bin"'
    assert request(base + "/text-wins")[0::2] == (200, "text")


def test_binary_file_validation_rejects_missing_and_outside_paths(tmp_path, logger):
    write_yaml(
        tmp_path / "missing.yaml",
        """
- key: missing-binary
  expect:
    http:
      method: GET
      path: /missing
  actions:
    - reply_http:
        status_code: 200
        body_from_binary_file: missing.bin
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)

    outside = tmp_path.parent / f"{tmp_path.name}-outside.bin"
    outside.write_bytes(b"outside")
    outside_dir = tmp_path / "outside-case"
    write_yaml(
        outside_dir / "outside.yaml",
        f"""
- key: outside-binary
  expect:
    http:
      method: GET
      path: /outside
  actions:
    - reply_http:
        status_code: 200
        body_from_binary_file: ../../{outside.name}
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(outside_dir, logger)

    send_dir = tmp_path / "send-case"
    write_yaml(
        send_dir / "missing-send.yaml",
        """
- key: missing-send-binary
  expect:
    http:
      method: GET
      path: /missing-send
  actions:
    - send_http:
        url: http://127.0.0.1:9999/upload
        method: POST
        body_from_binary_file: missing.bin
    - reply_http:
        status_code: 200
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(send_dir, logger)


def test_http_matching_actions_defaults_and_unmatched(server_factory):
    behaviors = [
        behavior(
            {
                "key": "item",
                "expect": {
                    "condition": '{{ .HTTPHeader.Get "X-Use" | eq "yes" }}',
                    "http": {"method": "POST", "path": "/items/:id"},
                },
                "actions": [
                    {"sleep": {"duration": "1ms"}},
                    {
                        "reply_http": {
                            "status_code": 201,
                            "headers": {"X-Item": '{{ .HTTPPathParams.Get "id" }}'},
                            "body": "{{ .HTTPBody | upper }}",
                        }
                    },
                ],
            }
        ),
        behavior(
            {
                "key": "fallback",
                "expect": {"http": {"method": "POST", "path": "/items/:id"}},
                "actions": [{"reply_http": {"status_code": 202}}],
            }
        ),
    ]
    _, base = server_factory(behaviors)

    status, headers, body = request(base + "/items/42?x=1", method="POST", body="abc", headers={"X-Use": "yes"})
    assert (status, body) == (201, "ABC")
    assert headers["X-Item"] == "42"
    assert headers["Content-Type"] == "application/json"
    assert headers["Content-Length"] == "3"

    status, _, body = request(base + "/items/42/extra", method="POST", body="abc", headers={"X-Use": "yes"})
    assert (status, body) == (404, "not found")

    status, _, body = request(base + "/items/42", method="GET")
    assert (status, body) == (404, "not found")

    status, headers, body = request(base + "/items/42", method="POST")
    assert (status, body) == (202, "")
    assert headers["Content-Length"] == "0"


class FakeKafkaPublisher:
    def __init__(self):
        self.records = []

    def publish(self, topic, payload):
        self.records.append((topic, payload))


class FakeAMQPPublisher:
    def __init__(self):
        self.records = []

    def publish(self, exchange, routing_key, payload):
        self.records.append((exchange, routing_key, payload))


def test_kafka_dispatch_context_multi_match_order_and_publish(tmp_path, logger):
    payload_file = tmp_path / "payloads" / "reply.txt"
    payload_file.parent.mkdir()
    payload_file.write_text("file {{ .KafkaTopic }} {{ .KafkaPayload }}")
    write_yaml(
        tmp_path / "kafka.yaml",
        """
- key: first
  expect:
    condition: '{{ .KafkaPayload | eq "go" }}'
    kafka:
      topic: in
  actions:
    - order: 2
      redis:
        - RPUSH seen second
    - order: 1
      redis:
        - RPUSH seen first
- key: skipped
  expect:
    condition: '{{ .KafkaPayload | eq "skip" }}'
    kafka:
      topic: in
  actions:
    - redis:
        - RPUSH seen skipped
- key: publisher
  expect:
    kafka:
      topic: in
  actions:
    - publish_kafka:
        topic: 'out-{{ .KafkaTopic }}'
        payload_from_file: payloads/reply.txt
""",
    )
    behaviors = hmock.load_behaviors(tmp_path, logger)
    store = hmock.MemoryRedisStore()
    kafka = FakeKafkaPublisher()

    matched = hmock.dispatch_kafka_message(
        behaviors,
        "in",
        "go",
        store,
        logger,
        hmock.BrokerPublishers(kafka=kafka),
    )

    assert matched == ["first", "publisher"]
    assert store.do("LRANGE seen 0 -1") == "first;;second"
    assert kafka.records == [("out-in", "file in go")]


def test_amqp_dispatch_context_multi_match_order_and_publish(tmp_path, logger):
    payload_file = tmp_path / "payloads" / "reply.txt"
    payload_file.parent.mkdir()
    payload_file.write_text("file {{ .AMQPExchange }} {{ .AMQPRoutingKey }} {{ .AMQPQueue }} {{ .AMQPPayload }}")
    write_yaml(
        tmp_path / "amqp.yaml",
        """
- key: first
  expect:
    condition: '{{ .AMQPPayload | eq "go" }}'
    amqp:
      exchange: in
      routing_key: user.created
      queue: q
  actions:
    - redis:
        - RPUSH seen first
- key: publisher
  expect:
    amqp:
      exchange: in
      routing_key: user.created
      queue: q
  actions:
    - publish_amqp:
        exchange: out
        routing_key: 'reply.{{ .AMQPQueue }}'
        payload_from_file: payloads/reply.txt
""",
    )
    behaviors = hmock.load_behaviors(tmp_path, logger)
    store = hmock.MemoryRedisStore()
    amqp = FakeAMQPPublisher()

    matched = hmock.dispatch_amqp_message(
        behaviors,
        "in",
        "user.created",
        "q",
        "go",
        store,
        logger,
        hmock.BrokerPublishers(amqp=amqp),
    )

    assert matched == ["first", "publisher"]
    assert store.do("LRANGE seen 0 -1") == "first"
    assert amqp.records == [("out", "reply.q", "file in user.created q go")]


def test_grpc_dispatch_context_first_match_and_response(tmp_path, logger):
    descriptor_path = tmp_path / "echo.pb"
    descriptor_path.write_bytes(descriptor_set_bytes())
    behaviors = [
        behavior(
            {
                "key": "first",
                "expect": {
                    "condition": '{{ .GRPCHeader.Get "x-use" | eq "yes" }}',
                    "grpc": {"service": "demo.Echo", "method": "Ping"},
                },
                "actions": [
                    {
                        "reply_grpc": {
                            "payload": '{"message":"{{ .GRPCService }}/{{ .GRPCMethod }} {{ .GRPCPayload | js }}"}',
                            "headers": {"x-seen": '{{ .GRPCHeader.Get "x-use" }}'},
                        }
                    }
                ],
            }
        ),
        behavior(
            {
                "key": "second",
                "expect": {"grpc": {"service": "demo.Echo", "method": "Ping"}},
                "actions": [{"reply_grpc": {"payload": '{"message":"second"}'}}],
            }
        ),
    ]
    registry = hmock.build_grpc_descriptor_registry(
        hmock.Config(
            templates_dir=str(tmp_path),
            grpc=hmock.GRPCConfig(enabled=True, descriptor_set_paths=("echo.pb",)),
        ),
        behaviors,
    )

    matched, response = hmock.dispatch_grpc_request(
        behaviors,
        "demo.Echo",
        "Ping",
        hmock.encode_grpc_frame(b'{"name":"Ada"}'),
        {"x-use": "yes"},
        registry,
        logger=logger,
    )

    assert matched == "first"
    assert response is not None
    assert response.headers["grpc-status"] == "0"
    assert response.headers["grpc-message"] == "OK"
    assert response.headers["Content-Type"] == "application/grpc"
    assert response.headers["x-seen"] == "yes"
    assert hmock.decode_grpc_frame(response.body) == b'{"message":"demo.Echo/Ping {\\"name\\":\\"Ada\\"}"}'

    unmatched, empty = hmock.dispatch_grpc_request(
        behaviors,
        "demo.Echo",
        "Other",
        hmock.encode_grpc_frame(b"{}"),
        {},
        registry,
    )
    assert (unmatched, empty) == (None, None)


def test_evaluate_validation_matching_conditions_and_context_merge():
    invalid_requests = [
        {"mock": {"key": "", "expect": {"http": {"method": "GET", "path": "/"}}}, "context": {"http_context": {}}},
        {"mock": {"key": "x", "expect": {}}, "context": {}},
        {"mock": {"key": "x", "expect": {"grpc": {"service": "demo.Echo", "method": "Ping"}}}, "context": {}},
        {"mock": {"key": "x", "expect": {"http": {"method": "GET", "path": "/"}}}, "context": []},
    ]
    for payload in invalid_requests:
        with pytest.raises(hmock.ValidationError):
            hmock.evaluate_mock_definition(payload)

    failed = hmock.evaluate_mock_definition(
        {
            "mock": {
                "key": "http",
                "expect": {"http": {"method": "POST", "path": "/items/:id"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "no"}}],
            },
            "context": {"http_context": {"method": "GET", "path": "/items/42"}},
        }
    )
    assert failed == {
        "expect_passed": False,
        "condition_passed": False,
        "condition_rendered": "",
        "actions_performed": [],
    }

    condition_failed = hmock.evaluate_mock_definition(
        {
            "mock": {
                "key": "http",
                "expect": {
                    "condition": '{{ .HTTPBody | eq "go" }}',
                    "http": {"method": "POST", "path": "/items/:id"},
                },
                "actions": [{"reply_http": {"status_code": 200, "body": "no"}}],
            },
            "context": {"http_context": {"method": "POST", "path": "/items/42", "body": "stop"}},
        }
    )
    assert condition_failed["expect_passed"] is True
    assert condition_failed["condition_passed"] is False
    assert condition_failed["condition_rendered"] == "false"
    assert condition_failed["actions_performed"] == []

    merged = hmock.evaluate_mock_definition(
        {
            "mock": {
                "key": "merged",
                "expect": {
                    "condition": '{{ .KafkaPayload | eq "event" }}',
                    "http": {"method": "POST", "path": "/items/:id"},
                    "kafka": {"topic": "events"},
                    "amqp": {"exchange": "ex", "routing_key": "rk"},
                    "grpc": {"service": "demo.Echo", "method": "Ping"},
                },
                "actions": [
                    {
                        "reply_http": {
                            "status_code": 201,
                            "headers": {"X-Route": '{{ .HTTPPathParams.Get "id" }}'},
                            "body": "{{ .HTTPBody }} {{ .KafkaPayload }} {{ .AMQPQueue }} {{ .GRPCHeader.Get \"x-id\" }}",
                        }
                    }
                ],
            },
            "context": {
                "http_context": {"method": "POST", "path": "/items/42", "body": "body"},
                "kafka_context": {"topic": "events", "payload": "event"},
                "amqp_context": {"exchange": "ex", "routing_key": "rk", "payload": "amqp"},
                "grpc_context": {"service": "demo.Echo", "method": "Ping", "payload": "{}", "headers": {"x-id": "g1"}},
            },
        }
    )
    assert merged["expect_passed"] is True
    assert merged["condition_passed"] is True
    assert merged["actions_performed"][0]["body"] == "body event rk g1"
    assert merged["actions_performed"][0]["headers"]["X-Route"] == "42"
    assert merged["actions_performed"][0]["headers"]["Content-Type"] == "application/json"


def test_evaluate_endpoint_dry_runs_actions_without_side_effects(tmp_path, logger, admin_server_factory):
    capture, thread, records, capture_url = start_capture_server()
    try:
        state, _, admin_base = admin_server_factory(tmp_path)
        payload = {
            "mock": {
                "key": "dry",
                "expect": {"http": {"method": "POST", "path": "/dry"}},
                "actions": [
                    {"order": 3, "send_http": {"url": capture_url, "method": "POST", "body": "side effect"}},
                    {"order": 1, "publish_kafka": {"topic": "out-{{ .HTTPBody }}", "payload": "payload {{ .HTTPBody }}"}},
                    {"order": 2, "reply_http": {"status_code": 202, "body": "reply {{ .HTTPBody }}"}},
                    {"order": 4, "redis": ["SET should not happen"]},
                ],
            },
            "context": {"http_context": {"method": "POST", "path": "/dry", "body": "ok"}},
        }

        status, _, body = json_request(admin_base + "/api/v1/evaluate", method="POST", payload=payload)

        assert status == 200
        parsed = json.loads(body)
        assert parsed["expect_passed"] is True
        assert parsed["condition_passed"] is True
        assert parsed["actions_performed"] == [
            {"type": "publish_kafka_action_performed", "topic": "out-ok", "payload": "payload ok"},
            {
                "type": "reply_http_action_performed",
                "status_code": "202",
                "content_type": "application/json",
                "body": "reply ok",
                "headers": {"Content-Type": "application/json", "Content-Length": "8"},
            },
        ]
        assert records == []
        assert state.redis_store.do("GET should") == ""

        status, _, body = json_request(
            admin_base + "/api/v1/evaluate",
            method="POST",
            payload={"mock": {"key": "", "expect": {"http": {"method": "GET", "path": "/"}}}, "context": {"http_context": {}}},
        )
        assert status == 400
        assert "mock.key" in body
    finally:
        stop_server(capture, thread)


class FakeKafkaAdapter:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.subscriptions = []
        self.published = []
        self.callback = None

    def start(self, callback):
        self.started += 1
        self.callback = callback

    def stop(self):
        self.stopped += 1

    def subscribe(self, topics):
        self.subscriptions.append(tuple(topics))

    def publish(self, topic, payload):
        self.published.append((topic, payload))


class FakeAMQPAdapter:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.configured = []
        self.published = []
        self.callback = None

    def start(self, callback):
        self.started += 1
        self.callback = callback

    def stop(self):
        self.stopped += 1

    def configure(self, bindings):
        self.configured.append(tuple(bindings))

    def publish(self, exchange, routing_key, payload):
        self.published.append((exchange, routing_key, payload))


def test_kafka_manager_refresh_publish_and_callback(logger):
    store = hmock.MemoryRedisStore()
    behavior = hmock.validate_behavior(
        {
            "key": "kafka",
            "expect": {"kafka": {"topic": "events"}},
            "actions": [{"redis": ["SET seen {{ .KafkaPayload }}"]}],
        }
    )
    state = hmock.HMockRuntimeState(
        hmock.Config(),
        logger,
        store,
        behaviors=[behavior],
        definitions=[],
    )
    adapter = FakeKafkaAdapter()
    manager = hmock.KafkaBrokerManager(state, adapter)
    state.broker_publishers = hmock.BrokerPublishers(kafka=manager)
    state.add_broker_manager(manager)

    manager.start()
    manager.publish("out", "payload")

    assert adapter.subscriptions[-1] == ("events",)
    assert adapter.started == 1
    assert adapter.published == [("out", "payload")]
    assert adapter.callback("events", "hello") == ["kafka"]
    assert store.do("GET seen") == "hello"


def test_amqp_manager_refresh_publish_callback_and_recover(logger):
    store = hmock.MemoryRedisStore()
    behavior = hmock.validate_behavior(
        {
            "key": "amqp",
            "expect": {"amqp": {"exchange": "events", "routing_key": "user.created"}},
            "actions": [{"redis": ["SET seen {{ .AMQPPayload }}"]}],
        }
    )
    state = hmock.HMockRuntimeState(
        hmock.Config(),
        logger,
        store,
        behaviors=[behavior],
        definitions=[],
    )
    adapter = FakeAMQPAdapter()
    manager = hmock.AMQPBrokerManager(state, adapter)
    state.broker_publishers = hmock.BrokerPublishers(amqp=manager)
    state.add_broker_manager(manager)

    manager.start()
    manager.publish("out", "reply", "payload")

    assert adapter.configured[-1] == (("events", "user.created", "user.created"),)
    assert adapter.started == 1
    assert adapter.published == [("out", "reply", "payload")]
    assert adapter.callback("events", "user.created", "user.created", "hello") == ["amqp"]
    assert store.do("GET seen") == "hello"

    manager.recover()

    assert adapter.stopped == 1
    assert adapter.started == 2
    assert adapter.configured[-1] == (("events", "user.created", "user.created"),)


def test_action_order_defaults_negative_values_stability_and_inheritance(tmp_path, logger):
    direct = behavior(
        {
            "key": "ordered",
            "expect": {"http": {"method": "GET", "path": "/ordered"}},
            "actions": [
                {"order": 5, "reply_http": {"status_code": 200}},
                {"redis": ["SET first default"]},
                {"order": -1, "sleep": {"duration": "1ms"}},
                {"order": 0, "redis": ["SET second explicit"]},
            ],
        }
    )
    assert [next(key for key in action if key != "order") for action in direct.actions] == [
        "sleep",
        "redis",
        "redis",
        "reply_http",
    ]
    assert direct.actions[1]["redis"] == ["SET first default"]
    assert direct.actions[2]["redis"] == ["SET second explicit"]

    write_yaml(
        tmp_path / "ordered.yaml",
        """
- key: child
  extend: base
  expect:
    http:
      method: GET
      path: /ordered
  actions:
    - order: -5
      redis:
        - SET child first
    - order: 0
      reply_http:
        status_code: 200
- key: base
  kind: AbstractBehavior
  actions:
    - order: 0
      redis:
        - SET base middle
    - order: 10
      redis:
        - SET base last
""",
    )

    inherited = hmock.load_behaviors(tmp_path, logger)[0]
    assert [action[next(key for key in action if key != "order")] for action in inherited.actions] == [
        ["SET child first"],
        ["SET base middle"],
        {"status_code": 200},
        ["SET base last"],
    ]


def test_file_backed_body_http_rendering_and_precedence(tmp_path, logger, server_factory):
    body_file = tmp_path / "responses" / "body.txt"
    body_file.parent.mkdir()
    body_file.write_text('file {{ .HTTPHeader.Get "X-Name" }} {{ gJsonPath "user.id" .HTTPBody }}')
    write_yaml(
        tmp_path / "file.yaml",
        """
- key: file-body
  expect:
    http:
      method: POST
      path: /file
  actions:
    - reply_http:
        status_code: 200
        body_from_file: responses/body.txt
        headers:
          X-From-Body: '{{ .HTTPHeader.Get "X-Name" }}'
- key: inline-body
  expect:
    http:
      method: GET
      path: /inline
  actions:
    - reply_http:
        status_code: 200
        body: inline
        body_from_file: responses/body.txt
- key: empty-inline-body
  expect:
    http:
      method: POST
      path: /empty
  actions:
    - reply_http:
        status_code: 200
        body: ""
        body_from_file: responses/body.txt
""",
    )
    _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

    status, headers, body = request(base + "/file", method="POST", body='{"user":{"id":"42"}}', headers={"X-Name": "Ada"})
    assert (status, body) == (200, "file Ada 42")
    assert headers["X-From-Body"] == "Ada"
    assert headers["Content-Length"] == str(len(body.encode()))

    assert request(base + "/inline")[0::2] == (200, "inline")
    assert request(base + "/empty", method="POST", body='{"user":{"id":"7"}}', headers={"X-Name": "Grace"})[0::2] == (200, "file Grace 7")


def test_condition_render_failure_falls_through(server_factory):
    behaviors = [
        behavior(
            {
                "key": "bad-condition",
                "expect": {"condition": "{{ .Missing }}", "http": {"method": "GET", "path": "/x"}},
                "actions": [{"reply_http": {"status_code": 500}}],
            }
        ),
        behavior(
            {
                "key": "good",
                "expect": {"http": {"method": "GET", "path": "/x"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "ok"}}],
            }
        ),
    ]
    _, base = server_factory(behaviors)

    status, _, body = request(base + "/x")
    assert (status, body) == (200, "ok")


def test_redis_do_conditions_headers_bodies_and_redis_actions(server_factory):
    behaviors = [
        behavior(
            {
                "key": "seed",
                "expect": {"http": {"method": "POST", "path": "/seed/:id"}},
                "actions": [
                    {
                        "redis": [
                            'SET mode "{{ .HTTPPathParams.Get "id" }}"',
                            'SET count {{ redisDo "RPUSH letters a" }}',
                            'RPUSH letters "{{ .HTTPBody }}"',
                        ]
                    },
                    {"reply_http": {"status_code": 204}},
                ],
            }
        ),
        behavior(
            {
                "key": "guard",
                "expect": {
                    "condition": '{{ redisDo "GET mode" | eq "open" }}',
                    "http": {"method": "GET", "path": "/guard"},
                },
                "actions": [
                    {
                        "reply_http": {
                            "status_code": 200,
                            "headers": {"X-Mode": '{{ redisDo "GET mode" }}'},
                            "body": '{{ redisDo "GET count" }}:{{ redisDo "LRANGE letters 0 -1" }}',
                        }
                    }
                ],
            }
        ),
    ]
    _, base = server_factory(behaviors)

    assert request(base + "/guard")[0::2] == (404, "not found")
    assert request(base + "/seed/open", method="POST", body="b")[0] == 204
    status, headers, body = request(base + "/guard")

    assert (status, body) == (200, "1:a;;b")
    assert headers["X-Mode"] == "open"


def test_duration_validation():
    assert hmock.parse_duration("2ms") == pytest.approx(0.002)
    assert hmock.parse_duration("1s") == pytest.approx(1)
    with pytest.raises(hmock.ValidationError):
        hmock.parse_duration("1day")


def test_structured_logging_levels_request_logs_and_unmatched(tmp_path, log_stream):
    logger = hmock.JsonLogger("info", stream=log_stream)
    server = hmock.HMockHTTPServer(("127.0.0.1", 0), [], logger)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(f"http://127.0.0.1:{server.server_address[1]}/missing")
        assert (status, body) == (404, "not found")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    entry = json.loads(log_stream.getvalue().strip())
    assert entry["level"] == "info"
    assert entry["http_path"] == "/missing"
    assert entry["http_method"] == "GET"
    assert "http_host" in entry
    assert entry["http_req"]["body"] == ""
    assert entry["http_res"]["status_code"] == 404

    quiet = io.StringIO()
    hmock.JsonLogger("warn", stream=quiet).info("hidden")
    assert quiet.getvalue() == ""


def test_basic_ping_example_end_to_end(tmp_path, logger, server_factory):
    write_yaml(
        tmp_path / "ping.yaml",
        """
- key: ping
  kind: Behavior
  expect:
    http:
      method: GET
      path: /ping
  actions:
    - reply_http:
        status_code: 200
        body: OK
        headers:
          Content-Type: text/plain
""",
    )
    _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

    status, headers, body = request(base + "/ping")

    assert (status, body) == (200, "OK")
    assert headers["Content-Type"] == "text/plain"
    assert headers["Content-Length"] == "2"


def test_condition_routing_example_end_to_end(tmp_path, logger, server_factory):
    write_yaml(
        tmp_path / "token.yaml",
        """
- key: header-token-200
  kind: Behavior
  expect:
    condition: '{{.HTTPHeader.Get "X-Token" | eq "t1234"}}'
    http:
      method: GET
      path: /token
  actions:
    - reply_http:
        status_code: 200
        body: OK
- key: header-token-401
  kind: Behavior
  expect:
    condition: '{{.HTTPHeader.Get "X-Token" | ne "t1234"}}'
    http:
      method: GET
      path: /token
  actions:
    - reply_http:
        status_code: 401
        body: unauthorized
""",
    )
    _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

    assert request(base + "/token", headers={"X-Token": "t1234"})[0::2] == (200, "OK")
    assert request(base + "/token", headers={"X-Token": "bad"})[0::2] == (401, "unauthorized")


def test_in_memory_redis_state_across_requests(server_factory):
    behaviors = [
        behavior(
            {
                "key": "enqueue",
                "expect": {"http": {"method": "POST", "path": "/queue"}},
                "actions": [
                    {"redis": ['RPUSH events "{{ .HTTPBody }}"']},
                    {"reply_http": {"status_code": 201, "body": '{{ redisDo "LRANGE events 0 -1" }}'}},
                ],
            }
        ),
        behavior(
            {
                "key": "dequeue",
                "expect": {"http": {"method": "GET", "path": "/queue"}},
                "actions": [{"reply_http": {"status_code": 200, "body": '{{ redisDo "LPOP events" }}'}}],
            }
        ),
    ]
    _, base = server_factory(behaviors)

    assert request(base + "/queue", method="POST", body="first")[0::2] == (201, "first")
    assert request(base + "/queue", method="POST", body="second")[0::2] == (201, "first;;second")
    assert request(base + "/queue")[0::2] == (200, "first")
    assert request(base + "/queue")[0::2] == (200, "second")


def test_send_http_receives_rendered_method_url_headers_and_body(server_factory):
    target, target_thread, records, target_base = start_capture_server()
    try:
        behaviors = [
            behavior(
                {
                    "key": "callback",
                    "expect": {"http": {"method": "POST", "path": "/items/:id"}},
                    "actions": [
                        {
                            "send_http": {
                                "url": target_base + '/callback/{{ .HTTPPathParams.Get "id" }}',
                                "method": "POST",
                                "headers": {"X-Echo": "{{ .HTTPBody | upper }}"},
                                "body": 'sent {{ .HTTPBody }} {{ .HTTPPathParams.Get "id" }}',
                            }
                        },
                        {"reply_http": {"status_code": 200, "body": "ok"}},
                    ],
                }
            )
        ]
        _, base = server_factory(behaviors)

        assert request(base + "/items/42", method="POST", body="abc")[0::2] == (200, "ok")
    finally:
        stop_server(target, target_thread)

    assert records == [
        {
            "method": "POST",
            "path": "/callback/42",
            "headers": {
                **records[0]["headers"],
                "X-Echo": "ABC",
            },
            "body": "sent abc 42",
        }
    ]


def test_send_http_file_body_and_failures_do_not_affect_inbound_response(tmp_path, logger, server_factory):
    body_file = tmp_path / "callback.txt"
    body_file.write_text('file {{ .HTTPBody }} {{ .HTTPHeader.Get "X-Name" }}')
    target, target_thread, records, target_base = start_capture_server()
    try:
        write_yaml(
            tmp_path / "callbacks.yaml",
            f"""
- key: callback-file
  expect:
    http:
      method: POST
      path: /callback-file
  actions:
    - send_http:
        url: {target_base}/file
        method: POST
        body_from_file: callback.txt
        headers:
          X-From-File: '{{{{ .HTTPHeader.Get "X-Name" }}}}'
    - reply_http:
        status_code: 200
        body: file-ok
- key: callback-fail
  expect:
    http:
      method: GET
      path: /callback-fail
  actions:
    - send_http:
        url: http://127.0.0.1:1/unavailable
        method: POST
        body: ignored
    - reply_http:
        status_code: 200
        body: still-ok
""",
        )
        _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

        assert request(base + "/callback-file", method="POST", body="payload", headers={"X-Name": "Ada"})[0::2] == (200, "file-ok")
        assert request(base + "/callback-fail")[0::2] == (200, "still-ok")
    finally:
        stop_server(target, target_thread)

    assert len(records) == 1
    assert records[0]["method"] == "POST"
    assert records[0]["path"] == "/file"
    assert records[0]["headers"]["X-From-File"] == "Ada"
    assert records[0]["body"] == "file payload Ada"


def test_send_http_binary_file_post_multipart_and_raw_non_post(tmp_path, logger, server_factory):
    upload_file = tmp_path / "upload.bin"
    upload_file.write_bytes(b"\x00upload-bytes\xff")
    raw_file = tmp_path / "raw.bin"
    raw_file.write_bytes(b"\x01raw-bytes\xfe")
    target, target_thread, records, target_base = start_capture_bytes_server()
    try:
        write_yaml(
            tmp_path / "binary-callbacks.yaml",
            f"""
- key: binary-post
  expect:
    http:
      method: GET
      path: /binary-post
  actions:
    - send_http:
        url: {target_base}/upload
        method: POST
        body_from_binary_file: upload.bin
        binary_file_name: custom.bin
        headers:
          Content-Type: image/custom
    - reply_http:
        status_code: 200
        body: posted
- key: binary-put
  expect:
    http:
      method: GET
      path: /binary-put
  actions:
    - send_http:
        url: {target_base}/raw
        method: PUT
        body_from_binary_file: raw.bin
    - reply_http:
        status_code: 200
        body: put
""",
        )
        _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

        assert request(base + "/binary-post")[0::2] == (200, "posted")
        assert request(base + "/binary-put")[0::2] == (200, "put")
    finally:
        stop_server(target, target_thread)

    assert records[0]["method"] == "POST"
    assert records[0]["path"] == "/upload"
    assert records[0]["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="custom.bin"' in records[0]["body"]
    assert b"Content-Type: image/custom" in records[0]["body"]
    assert b"\x00upload-bytes\xff" in records[0]["body"]
    assert records[1]["method"] == "PUT"
    assert records[1]["path"] == "/raw"
    assert records[1]["body"] == b"\x01raw-bytes\xfe"


def test_build_server_uses_configured_host_port_and_templates(tmp_path, logger):
    write_yaml(
        tmp_path / "ping.yaml",
        """
- key: ping
  expect:
    http:
      method: GET
      path: /ping
  actions:
    - reply_http:
        status_code: 200
        body: OK
""",
    )
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    server = hmock.build_server(config, logger)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(f"http://127.0.0.1:{server.server_address[1]}/ping")
        assert (status, body) == (200, "OK")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
