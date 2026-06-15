from __future__ import annotations

import io
import json
import hashlib
import hmac
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import hmock
import omctl


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
def runtime_server_factory(logger):
    servers = []

    def start(config, redis_store=None):
        state = hmock.HMockRuntimeState.from_config(config, logger, redis_store)
        mock_server = hmock.build_server(config, logger, state)
        mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
        mock_thread.start()
        admin_server = hmock.build_admin_server(config, logger, state)
        admin_thread = None
        if admin_server is not None:
            admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
            admin_thread.start()
        servers.append((mock_server, mock_thread, admin_server, admin_thread))
        mock_base = f"http://127.0.0.1:{mock_server.server_address[1]}"
        admin_base = None if admin_server is None else f"http://127.0.0.1:{admin_server.server_address[1]}"
        return state, mock_base, admin_base

    yield start

    for mock_server, mock_thread, admin_server, admin_thread in servers:
        if admin_server is not None:
            admin_server.shutdown()
            admin_server.server_close()
            admin_thread.join(timeout=2)
        mock_server.shutdown()
        mock_server.server_close()
        mock_thread.join(timeout=2)


def request(url, method="GET", body=None, headers=None):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()


def raw_request(url, method="GET", body=None, headers=None):
    if isinstance(body, bytes):
        data = body
    elif body is not None:
        data = body.encode()
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def json_request(url, method="GET", value=None):
    body = None if value is None else json.dumps(value)
    status, headers, text = request(
        url,
        method=method,
        body=body,
        headers={"Content-Type": "application/json"} if value is not None else None,
    )
    parsed = json.loads(text) if text else None
    return status, headers, parsed


def yaml_request(url, method="POST", text="[]"):
    status, headers, body = request(
        url,
        method=method,
        body=text,
        headers={"Content-Type": "application/yaml"},
    )
    parsed = json.loads(body) if body else None
    return status, headers, parsed


def start_capture_server():
    records = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _handle(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            body_bytes = self.rfile.read(length) if length else b""
            records.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": {key: value for key, value in self.headers.items()},
                    "body": body_bytes.decode(errors="replace"),
                    "body_bytes": body_bytes,
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


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


class FakeKafkaAdapter:
    def __init__(self, fail_publish=False):
        self.fail_publish = fail_publish
        self.published = []
        self.subscriptions = []
        self.consume_calls = 0
        self.closed = False

    def publish(self, topic, payload):
        if self.fail_publish:
            raise RuntimeError("kafka down")
        self.published.append((topic, payload))

    def subscribe(self, topics):
        self.subscriptions.append(tuple(topics))

    def consume(self, callback, stop_event):
        self.consume_calls += 1

    def close(self):
        self.closed = True


class FakeAMQPAdapter:
    def __init__(self, fail_publish=False, fail_consume_once=False):
        self.fail_publish = fail_publish
        self.fail_consume_once = fail_consume_once
        self.published = []
        self.binding_setups = []
        self.consume_calls = 0
        self.closed = False

    def setup_bindings(self, bindings):
        self.binding_setups.append(tuple(bindings))

    def publish(self, exchange, routing_key, payload):
        if self.fail_publish:
            raise RuntimeError("amqp down")
        self.published.append((exchange, routing_key, payload))

    def consume(self, bindings, callback, stop_event):
        self.consume_calls += 1
        if self.fail_consume_once:
            self.fail_consume_once = False
            raise RuntimeError("transient disconnect")
        stop_event.wait(0.05)

    def close(self):
        self.closed = True


def behavior(raw):
    return hmock.validate_behavior(raw)


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
            "HM_KAFKA_ENABLED": "true",
            "HM_KAFKA_CLIENT_ID": "client-a",
            "HM_KAFKA_SEED_BROKERS": "kafka-a:9092, kafka-b:9092",
            "HM_KAFKA_SASL_USERNAME": "shared-user",
            "HM_KAFKA_SASL_PASSWORD": "shared-pass",
            "HM_KAFKA_TLS_ENABLED": "true",
            "HM_KAFKA_PRODUCER_SEED_BROKERS": "producer:9092",
            "HM_KAFKA_SASL_PRODUCER_USERNAME": "producer-user",
            "HM_KAFKA_SASL_PRODUCER_PASSWORD": "producer-pass",
            "HM_KAFKA_TLS_CONSUMER_ENABLED": "false",
            "HM_AMQP_ENABLED": "true",
            "HM_AMQP_URL": "amqp://user:pass@localhost:5673",
        }
    )

    assert config.templates_dir == "/tmp/mocks"
    assert config.http_port == 7777
    assert config.http_host == "127.0.0.1"
    assert config.log_level == "warn"
    assert config.redis_type == "redis"
    assert config.redis_url == "redis://localhost:6380/2"
    assert config.admin_http_enabled is False
    assert config.admin_http_port == 7778
    assert config.admin_http_host == "127.0.0.2"
    assert config.templates_dir_hot_reload is False
    assert config.cors_enabled is True
    assert config.kafka_enabled is True
    assert config.kafka_client_id == "client-a"
    assert config.kafka_seed_brokers == ("kafka-a:9092", "kafka-b:9092")
    assert config.kafka_sasl_username == "shared-user"
    assert config.kafka_sasl_password == "shared-pass"
    assert config.kafka_tls_enabled is True
    assert config.kafka_producer.seed_brokers == ("producer:9092",)
    assert config.kafka_producer.sasl_username == "producer-user"
    assert config.kafka_producer.sasl_password == "producer-pass"
    assert config.kafka_producer.tls_enabled is True
    assert config.kafka_producer.sasl_enabled is True
    assert config.kafka_consumer.seed_brokers == ("kafka-a:9092", "kafka-b:9092")
    assert config.kafka_consumer.sasl_username == "shared-user"
    assert config.kafka_consumer.sasl_password == "shared-pass"
    assert config.kafka_consumer.tls_enabled is False
    assert config.kafka_consumer.sasl_enabled is True
    assert config.amqp_enabled is True
    assert config.amqp_url == "amqp://user:pass@localhost:5673"
    assert hmock.load_config({"HM_ADMIN_HTTP_ENABLED": "0"}).admin_http_enabled is False
    assert hmock.load_config({"HM_ADMIN_HTTP_ENABLED": "yes"}).admin_http_enabled is True
    assert hmock.load_config({}).templates_dir_hot_reload is True
    assert hmock.load_config({}).cors_enabled is False
    assert hmock.load_config({}).kafka_enabled is False
    assert hmock.load_config({}).kafka_seed_brokers == ("kafka:9092",)
    assert hmock.load_config({}).kafka_producer.sasl_enabled is False
    assert hmock.load_config({"HM_KAFKA_SASL_USERNAME": "u"}).kafka_producer.sasl_enabled is False
    assert hmock.load_config({}).amqp_enabled is False
    assert hmock.load_config({}).amqp_url == "amqp://guest:guest@rabbitmq:5672"
    assert hmock.parse_kafka_seed_brokers(" a:1, ,b:2 ") == ("a:1", "b:2")
    assert hmock.build_kafka_adapter(hmock.Config()) is None
    assert hmock.build_amqp_adapter(hmock.Config()) is None


def test_admin_server_disabled_by_config(tmp_path, logger):
    config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_enabled=False,
    )
    state = hmock.HMockRuntimeState.from_config(config, logger)

    assert hmock.build_admin_server(config, logger, state) is None


def test_filesystem_hot_reload_creation_edit_and_deletion(tmp_path, logger, runtime_server_factory):
    write_yaml(
        tmp_path / "hot.yaml",
        """
- key: hot
  expect:
    http:
      method: GET
      path: /hot
  actions:
    - reply_http:
        status_code: 200
        body: old
""",
    )
    config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_enabled=False,
    )
    _, mock_base, _ = runtime_server_factory(config)

    assert request(mock_base + "/hot")[0::2] == (200, "old")

    time.sleep(0.01)
    write_yaml(
        tmp_path / "hot.yaml",
        """
- key: hot
  expect:
    http:
      method: GET
      path: /hot
  actions:
    - reply_http:
        status_code: 200
        body: new
""",
    )
    assert request(mock_base + "/hot")[0::2] == (200, "new")

    write_yaml(
        tmp_path / "created.yaml",
        """
- key: created
  expect:
    http:
      method: GET
      path: /created
  actions:
    - reply_http:
        status_code: 201
        body: created
""",
    )
    assert request(mock_base + "/created")[0::2] == (201, "created")

    (tmp_path / "created.yaml").unlink()
    assert request(mock_base + "/created")[0::2] == (404, "not found")


def test_disabled_hot_reload_keeps_filesystem_pinned_but_admin_mutations_apply(tmp_path, logger, runtime_server_factory):
    write_yaml(
        tmp_path / "pinned.yaml",
        """
- key: pinned
  expect:
    http:
      method: GET
      path: /pinned
  actions:
    - reply_http:
        status_code: 200
        body: original
""",
    )
    config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_host="127.0.0.1",
        admin_http_port=0,
        templates_dir_hot_reload=False,
    )
    _, mock_base, admin_base = runtime_server_factory(config)

    write_yaml(
        tmp_path / "pinned.yaml",
        """
- key: pinned
  expect:
    http:
      method: GET
      path: /pinned
  actions:
    - reply_http:
        status_code: 200
        body: changed
""",
    )
    write_yaml(
        tmp_path / "new.yaml",
        """
- key: new
  expect:
    http:
      method: GET
      path: /new
  actions:
    - reply_http:
        status_code: 200
        body: new
""",
    )
    assert request(mock_base + "/pinned")[0::2] == (200, "original")
    assert request(mock_base + "/new")[0::2] == (404, "not found")

    api_definition = {
        "key": "api-visible",
        "expect": {"http": {"method": "GET", "path": "/api-visible"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", method="POST", value=[api_definition])[0] == 200
    assert request(mock_base + "/api-visible")[0::2] == (200, "api")


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


def test_persisted_definition_storage_and_template_set_isolation():
    store = hmock.MemoryRedisStore()
    base = [
        {
            "key": "api",
            "expect": {"http": {"method": "GET", "path": "/api"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
        }
    ]
    set_a = [
        {
            "key": "set-a",
            "expect": {"http": {"method": "GET", "path": "/set-a"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "a"}}],
        }
    ]
    set_b = [
        {
            "key": "set-b",
            "expect": {"http": {"method": "GET", "path": "/set-b"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "b"}}],
        }
    ]

    hmock.replace_base_api_definitions(store, base)
    hmock.replace_template_set_definitions(store, "a", set_a)
    hmock.replace_template_set_definitions(store, "b", set_b)

    assert hmock.load_base_api_definitions(store) == base
    assert hmock.list_template_set_keys(store) == ["a", "b"]
    assert hmock.load_template_set_definitions(store, "a") == set_a

    hmock.delete_template_set_definitions(store, "a")

    assert hmock.list_template_set_keys(store) == ["b"]
    assert hmock.load_template_set_definitions(store, "b") == set_b


def test_combined_definition_loading_order_and_validation(tmp_path, logger, log_stream):
    write_yaml(
        tmp_path / "fs.yaml",
        """
- key: shared
  expect:
    http:
      method: GET
      path: /shared
  actions:
    - reply_http:
        status_code: 200
        body: fs
- key: filesystem-only
  expect:
    http:
      method: GET
      path: /fs
  actions:
    - reply_http:
        status_code: 200
        body: fs-only
""",
    )
    store = hmock.MemoryRedisStore()
    hmock.replace_base_api_definitions(
        store,
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/shared"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
            },
            {
                "key": "api-only",
                "expect": {"http": {"method": "GET", "path": "/api"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "api-only"}}],
            },
        ],
    )
    hmock.replace_template_set_definitions(
        store,
        "z-set",
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/shared"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "set"}}],
            }
        ],
    )
    config = hmock.Config(templates_dir=str(tmp_path), log_level="debug")

    state = hmock.HMockRuntimeState.from_config(config, logger, store)
    definitions = state.snapshot()[1]

    assert [raw["key"] for raw in definitions] == ["filesystem-only", "api-only", "shared"]
    assert definitions[-1]["actions"][0]["reply_http"]["body"] == "set"
    warnings = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert [entry["key"] for entry in warnings if entry["message"] == "duplicate mock key override"] == ["shared", "shared"]

    invalid = [
        {
            "key": "bad",
            "expect": {"http": {"method": "GET", "path": "/bad"}},
            "actions": [{"reply_http": {"status_code": "200"}}],
        }
    ]
    with pytest.raises(hmock.ValidationError):
        state.validate_candidate(base_definitions=invalid)
    assert hmock.load_base_api_definitions(store)[0]["key"] == "shared"


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


def test_broker_expectation_validation_actions_and_file_snapshot(tmp_path, logger):
    payload_file = tmp_path / "messages" / "payload.txt"
    payload_file.parent.mkdir()
    payload_file.write_text("file {{ .KafkaPayload }}")
    write_yaml(
        tmp_path / "broker.yaml",
        """
- key: kafka
  expect:
    kafka:
      topic: orders
  actions:
    - publish_kafka:
        topic: out-{{ .KafkaTopic }}
        payload_from_file: messages/payload.txt
- key: amqp
  expect:
    amqp:
      exchange: events
      routing_key: order.created
  actions:
    - publish_amqp:
        exchange: outbound
        routing_key: mirrored
        payload: '{{ .AMQPPayload }}'
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    payload_file.write_text("changed")

    assert behaviors[0].kafka_topic == "orders"
    assert behaviors[0].method == ""
    assert behaviors[0].actions[0]["publish_kafka"]["publish_kafka_payload_from_file_content"] == "file {{ .KafkaPayload }}"
    assert behaviors[1].amqp_exchange == "events"
    assert behaviors[1].amqp_routing_key == "order.created"
    assert behaviors[1].amqp_queue == "order.created"

    invalid_behaviors = [
        {"key": "missing-topic", "expect": {"kafka": {}}, "actions": []},
        {"key": "bad-topic", "expect": {"kafka": {"topic": 123}}, "actions": []},
        {"key": "missing-exchange", "expect": {"amqp": {"routing_key": "rk"}}, "actions": []},
        {"key": "missing-routing", "expect": {"amqp": {"exchange": "ex"}}, "actions": []},
        {"key": "bad-queue", "expect": {"amqp": {"exchange": "ex", "routing_key": "rk", "queue": 1}}, "actions": []},
        {
            "key": "bad-kafka-publish",
            "expect": {"http": {"method": "GET", "path": "/bad"}},
            "actions": [{"publish_kafka": {"topic": "out"}}],
        },
        {
            "key": "bad-amqp-publish",
            "expect": {"http": {"method": "GET", "path": "/bad"}},
            "actions": [{"publish_amqp": {"exchange": "ex", "routing_key": "rk"}}],
        },
    ]
    for raw in invalid_behaviors:
        with pytest.raises(hmock.ValidationError):
            hmock.validate_behavior(raw, tmp_path)

    write_yaml(
        tmp_path / "missing-payload.yaml",
        """
- key: missing-file
  expect:
    kafka:
      topic: missing
  actions:
    - publish_kafka:
        topic: out
        payload_from_file: messages/missing.txt
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)

    outside = tmp_path.parent / f"{tmp_path.name}-outside-payload.txt"
    outside.write_text("outside")
    outside_dir = tmp_path / "outside"
    write_yaml(
        outside_dir / "outside.yaml",
        f"""
- key: outside-file
  expect:
    amqp:
      exchange: ex
      routing_key: rk
  actions:
    - publish_amqp:
        exchange: out
        routing_key: rk
        payload_from_file: ../../{outside.name}
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(outside_dir, logger)


def test_broker_template_contexts_and_named_templates():
    kafka_context = hmock.build_kafka_template_context(
        "orders",
        '{"id":"42"}',
        values={"suffix": "done"},
        templates={"summary": "{{ .KafkaTopic }}:{{ gJsonPath \"id\" .KafkaPayload }}:{{ .Values.suffix }}"},
    )
    assert hmock.render_template('{{ template "summary" . }}', kafka_context) == "orders:42:done"
    assert hmock.render_template('{{ upper .KafkaPayload }}', kafka_context) == '{"ID":"42"}'

    amqp_context = hmock.build_amqp_template_context(
        "events",
        "order.created",
        "orders",
        "payload",
        values={"prefix": "seen"},
        templates={"summary": "{{ .Values.prefix }}:{{ .AMQPExchange }}:{{ .AMQPRoutingKey }}:{{ .AMQPQueue }}:{{ .AMQPPayload }}"},
    )
    assert hmock.render_template('{{ template "summary" . }}', amqp_context) == "seen:events:order.created:orders:payload"


def test_http_broker_publish_actions_order_failures_and_response(tmp_path, logger):
    payload_file = tmp_path / "payload.txt"
    payload_file.write_text("file {{ .HTTPBody }}")
    kafka = FakeKafkaAdapter()
    amqp = FakeAMQPAdapter()
    store = hmock.MemoryRedisStore()
    behavior = hmock.validate_behavior(
        {
            "key": "publish",
            "expect": {"http": {"method": "POST", "path": "/publish"}},
            "actions": [
                {"order": 2, "reply_http": {"status_code": 200, "body": "ok"}},
                {"order": 0, "publish_kafka": {"topic": "k-{{ .HTTPBody }}", "payload": "inline {{ .HTTPBody }}", "payload_from_file": "payload.txt"}},
                {"order": 1, "redis": ["SET marker before-amqp"]},
                {"order": 1, "publish_amqp": {"exchange": "ex", "routing_key": "rk-{{ redisDo \"GET marker\" }}", "payload_from_file": "payload.txt"}},
            ],
        },
        tmp_path,
    )
    response = hmock.execute_behavior(
        behavior,
        hmock.RequestInfo("POST", "/publish", "/publish", "", "", {}, "body"),
        {},
        store,
        logger,
        kafka,
        amqp,
    )

    assert response.status_code == 200
    assert response.body == "ok"
    assert kafka.published == [("k-body", "inline body")]
    assert amqp.published == [("ex", "rk-before-amqp", "file body")]

    failing_response = hmock.execute_behavior(
        hmock.validate_behavior(
            {
                "key": "failing-publish",
                "expect": {"http": {"method": "GET", "path": "/fail"}},
                "actions": [
                    {"publish_kafka": {"topic": "out", "payload": "payload"}},
                    {"publish_amqp": {"exchange": "ex", "routing_key": "rk", "payload": "payload"}},
                    {"reply_http": {"status_code": 201, "body": "still-ok"}},
                ],
            }
        ),
        hmock.RequestInfo("GET", "/fail", "/fail", "", "", {}, ""),
        {},
        hmock.MemoryRedisStore(),
        logger,
        FakeKafkaAdapter(fail_publish=True),
        FakeAMQPAdapter(fail_publish=True),
    )
    assert (failing_response.status_code, failing_response.body) == (201, "still-ok")


def test_kafka_runtime_matching_loaded_order_subscription_refresh_and_disabled(logger):
    kafka = FakeKafkaAdapter()
    amqp = FakeAMQPAdapter()
    store = hmock.MemoryRedisStore()
    behaviors = [
        behavior(
            {
                "key": "first",
                "values": {"target": "go"},
                "expect": {"condition": '{{ gJsonPath "status" .KafkaPayload | eq .Values.target }}', "kafka": {"topic": "orders"}},
                "actions": [
                    {"redis": ["RPUSH seen first"]},
                    {"publish_kafka": {"topic": "audit", "payload": "{{ .KafkaTopic }}:{{ gJsonPath \"id\" .KafkaPayload }}"}},
                ],
            }
        ),
        behavior(
            {
                "key": "condition-false",
                "expect": {"condition": "{{ eq .KafkaPayload \"nope\" }}", "kafka": {"topic": "orders"}},
                "actions": [{"redis": ["RPUSH seen nope"]}],
            }
        ),
        behavior(
            {
                "key": "condition-error",
                "expect": {"condition": "{{ .Missing }}", "kafka": {"topic": "orders"}},
                "actions": [{"redis": ["RPUSH seen error"]}],
            }
        ),
        behavior(
            {
                "key": "second",
                "expect": {"kafka": {"topic": "orders"}},
                "actions": [
                    {"redis": ["RPUSH seen second"]},
                    {"publish_amqp": {"exchange": "out", "routing_key": "rk", "payload": "{{ .KafkaPayload }}"}},
                ],
            }
        ),
        behavior(
            {
                "key": "other-topic",
                "expect": {"kafka": {"topic": "payments"}},
                "actions": [{"redis": ["RPUSH seen payments"]}],
            }
        ),
    ]
    state = hmock.HMockRuntimeState(
        hmock.Config(templates_dir_hot_reload=False, kafka_enabled=True, amqp_enabled=True),
        logger,
        store,
        behaviors,
        [],
        kafka_adapter=kafka,
        amqp_adapter=amqp,
    )
    runtime = hmock.BrokerRuntime(state, kafka, amqp)
    state.broker_runtime = runtime
    runtime.start()
    runtime.handle_kafka_message(hmock.KafkaMessage("orders", '{"status":"go","id":"42"}'))

    assert kafka.subscriptions[-1] == ("orders", "payments")
    assert kafka.consume_calls == 1
    assert store.do("LRANGE seen 0 -1") == "first;;second"
    assert kafka.published == [("audit", "orders:42")]
    assert amqp.published == [("out", "rk", '{"status":"go","id":"42"}')]

    state.replace_snapshot(
        hmock.DefinitionSnapshot(
            [],
            behaviors
            + [
                behavior(
                    {
                        "key": "new-topic",
                        "expect": {"kafka": {"topic": "shipments"}},
                        "actions": [{"redis": ["RPUSH seen shipments"]}],
                    }
                )
            ],
        )
    )
    assert kafka.subscriptions[-1] == ("orders", "payments", "shipments")
    runtime.stop()
    assert kafka.closed is True
    assert amqp.closed is True

    disabled_store = hmock.MemoryRedisStore()
    disabled_state = hmock.HMockRuntimeState(
        hmock.Config(templates_dir_hot_reload=False, kafka_enabled=False),
        logger,
        disabled_store,
        behaviors,
        [],
        kafka_adapter=FakeKafkaAdapter(),
    )
    disabled_runtime = hmock.BrokerRuntime(disabled_state, disabled_state.kafka_adapter)
    disabled_runtime.handle_kafka_message(hmock.KafkaMessage("orders", '{"status":"go"}'))
    assert disabled_store.do("LRANGE seen 0 -1") == ""


def test_amqp_runtime_setup_matching_reconnect_and_disabled(logger):
    amqp = FakeAMQPAdapter()
    kafka = FakeKafkaAdapter()
    store = hmock.MemoryRedisStore()
    behaviors = [
        behavior(
            {
                "key": "first",
                "values": {"expected": "payload"},
                "expect": {
                    "condition": "{{ eq .AMQPPayload .Values.expected }}",
                    "amqp": {"exchange": "events", "routing_key": "order.created"},
                },
                "actions": [
                    {"redis": ["RPUSH amqp first"]},
                    {"publish_amqp": {"exchange": "out", "routing_key": "{{ .AMQPQueue }}", "payload": "{{ .AMQPExchange }}:{{ .AMQPRoutingKey }}:{{ .AMQPPayload }}"}},
                ],
            }
        ),
        behavior(
            {
                "key": "false",
                "expect": {"condition": "{{ eq .AMQPPayload \"nope\" }}", "amqp": {"exchange": "events", "routing_key": "order.created"}},
                "actions": [{"redis": ["RPUSH amqp nope"]}],
            }
        ),
        behavior(
            {
                "key": "error",
                "expect": {"condition": "{{ .Missing }}", "amqp": {"exchange": "events", "routing_key": "order.created"}},
                "actions": [{"redis": ["RPUSH amqp error"]}],
            }
        ),
        behavior(
            {
                "key": "second",
                "expect": {"amqp": {"exchange": "events", "routing_key": "order.created", "queue": "explicit"}},
                "actions": [
                    {"redis": ["RPUSH amqp second"]},
                    {"publish_kafka": {"topic": "amqp-audit", "payload": "{{ .AMQPQueue }}:{{ .AMQPPayload }}"}},
                ],
            }
        ),
    ]
    state = hmock.HMockRuntimeState(
        hmock.Config(templates_dir_hot_reload=False, kafka_enabled=True, amqp_enabled=True),
        logger,
        store,
        behaviors,
        [],
        kafka_adapter=kafka,
        amqp_adapter=amqp,
    )
    runtime = hmock.BrokerRuntime(state, kafka, amqp)
    state.broker_runtime = runtime
    runtime.start()

    assert amqp.binding_setups[-1] == (
        hmock.AMQPBinding("events", "order.created", "explicit"),
        hmock.AMQPBinding("events", "order.created", "order.created"),
    )
    assert amqp.consume_calls == 1

    runtime.handle_amqp_message(hmock.AMQPMessage("events", "order.created", "order.created", "payload"))
    runtime.handle_amqp_message(hmock.AMQPMessage("events", "order.created", "explicit", "payload"))
    runtime.handle_amqp_message(hmock.AMQPMessage("events", "other", "order.created", "payload"))

    assert store.do("LRANGE amqp 0 -1") == "first;;second"
    assert amqp.published == [("out", "order.created", "events:order.created:payload")]
    assert kafka.published == [("amqp-audit", "explicit:payload")]

    runtime.reconnect_amqp()
    assert amqp.binding_setups[-1] == runtime.amqp_bindings
    runtime.stop()

    disabled_store = hmock.MemoryRedisStore()
    disabled_state = hmock.HMockRuntimeState(
        hmock.Config(templates_dir_hot_reload=False, amqp_enabled=False),
        logger,
        disabled_store,
        behaviors,
        [],
        amqp_adapter=FakeAMQPAdapter(),
    )
    disabled_runtime = hmock.BrokerRuntime(disabled_state, amqp_adapter=disabled_state.amqp_adapter)
    disabled_runtime.handle_amqp_message(hmock.AMQPMessage("events", "order.created", "order.created", "payload"))
    assert disabled_store.do("LRANGE amqp 0 -1") == ""


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
    ctx = hmock.build_template_context({}, "", "/", "", {}, store.do)

    assert hmock.render_template('{{ redisDo "SET color blue" }}', ctx) == "OK"
    assert hmock.render_template('{{ redisDo "GET color" }}', ctx) == "blue"
    assert hmock.render_template('{{ redisDo "RPUSH letters a b c" }}', ctx) == "3"
    assert hmock.render_template('{{ range $i, $v := redisDo "LRANGE letters 0 -1" | splitList ";;" }}{{ $v }}{{ end }}', ctx) == "abc"


def test_reserved_internal_redis_keyspace_detection():
    assert hmock.redis_command_targets_internal("GET __hmock_internal:templates") is True
    assert hmock.redis_command_targets_internal("SET __hmock_internal:template_sets:a value") is True
    assert hmock.redis_command_targets_internal("DEL public __hmock_internal:templates") is True
    assert hmock.redis_command_targets_internal("KEYS __hmock_internal:*") is True
    assert hmock.redis_command_targets_internal("KEYS *") is True
    assert hmock.redis_command_targets_internal("GET public") is False


def test_reserved_internal_redis_keyspace_is_blocked_for_templates_and_actions():
    store = hmock.MemoryRedisStore()
    store.do("SET __hmock_internal:templates original")
    behaviors = [
        behavior(
            {
                "key": "template-blocked",
                "expect": {"http": {"method": "GET", "path": "/template-blocked"}},
                "actions": [
                    {
                        "reply_http": {
                            "status_code": 200,
                            "body": '{{ redisDo "GET __hmock_internal:templates" }}',
                        }
                    }
                ],
            }
        ),
        behavior(
            {
                "key": "action-blocked",
                "expect": {"http": {"method": "GET", "path": "/action-blocked"}},
                "actions": [
                    {"redis": ["SET __hmock_internal:templates changed"]},
                    {"reply_http": {"status_code": 200, "body": "changed"}},
                ],
            }
        ),
    ]
    logger = hmock.JsonLogger("debug", stream=io.StringIO())
    server = hmock.HMockHTTPServer(("127.0.0.1", 0), behaviors, logger, store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        actual_base = f"http://127.0.0.1:{server.server_address[1]}"
        assert request(actual_base + "/template-blocked")[0::2] == (500, "template render error")
        assert request(actual_base + "/action-blocked")[0::2] == (500, "template render error")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert store.do("GET __hmock_internal:templates") == "original"


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


def test_mock_http_cors_headers_and_preflight(tmp_path, logger, runtime_server_factory):
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
        headers:
          Access-Control-Allow-Origin: https://example.test
        body: ok
- key: explicit-options
  expect:
    http:
      method: OPTIONS
      path: /cors
  actions:
    - reply_http:
        status_code: 204
        body: explicit
""",
    )
    disabled_config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_enabled=False,
        cors_enabled=False,
    )
    _, disabled_base, _ = runtime_server_factory(disabled_config)
    assert "Access-Control-Allow-Methods" not in request(disabled_base + "/cors")[1]

    enabled_config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_enabled=False,
        cors_enabled=True,
    )
    _, enabled_base, _ = runtime_server_factory(enabled_config)

    status, headers, body = request(enabled_base + "/cors")
    assert (status, body) == (200, "ok")
    assert headers["Access-Control-Allow-Origin"] == "https://example.test"
    assert headers["Access-Control-Allow-Methods"] == "*"
    assert headers["Access-Control-Allow-Headers"] == "*"
    assert headers["Access-Control-Allow-Credentials"] == "true"

    assert request(enabled_base + "/cors", method="OPTIONS")[0] == 204
    status, headers, body = request(enabled_base + "/missing", method="OPTIONS")
    assert (status, body) == (200, "")
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Access-Control-Allow-Methods"] == "*"


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


def test_binary_reply_http_loading_response_and_precedence(tmp_path, logger, server_factory):
    binary_file = tmp_path / "files" / "payload.bin"
    binary_file.parent.mkdir()
    binary_file.write_bytes(b"\x00\xffA")
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
        body_from_binary_file: files/payload.bin
        binary_file_name: payload.bin
        headers:
          Content-Type: application/octet-stream
- key: inline
  expect:
    http:
      method: GET
      path: /inline-binary
  actions:
    - reply_http:
        status_code: 200
        body: inline
        body_from_binary_file: files/payload.bin
- key: empty-inline
  expect:
    http:
      method: GET
      path: /empty-binary
  actions:
    - reply_http:
        status_code: 200
        body: ""
        body_from_binary_file: files/payload.bin
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    binary_file.write_bytes(b"changed")
    payload = behaviors[0].actions[0]["reply_http"]
    assert payload["body_from_binary_file_content"] == b"\x00\xffA"

    _, base = server_factory(behaviors)
    status, headers, body = raw_request(base + "/binary")
    assert (status, body) == (200, b"\x00\xffA")
    assert headers["Content-Length"] == "3"
    assert headers["Content-Disposition"] == 'inline; filename="payload.bin"'

    assert request(base + "/inline-binary")[0::2] == (200, "inline")
    assert raw_request(base + "/empty-binary")[0::2] == (200, b"\x00\xffA")

    with pytest.raises(hmock.ValidationError):
        hmock.validate_behavior(
            {
                "key": "bad-name",
                "expect": {"http": {"method": "GET", "path": "/bad"}},
                "actions": [{"reply_http": {"status_code": 200, "binary_file_name": 123}}],
            }
        )


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

    assert len(records) == 1
    assert records[0]["method"] == "POST"
    assert records[0]["path"] == "/callback/42"
    assert records[0]["headers"]["X-Echo"] == "ABC"
    assert records[0]["body"] == "sent abc 42"


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


def test_send_http_binary_body_multipart_raw_and_precedence(tmp_path, logger, server_factory):
    binary_file = tmp_path / "uploads" / "payload.bin"
    binary_file.parent.mkdir()
    binary_file.write_bytes(b"\x00\xffDATA")
    target, target_thread, records, target_base = start_capture_server()
    try:
        write_yaml(
            tmp_path / "binary-callbacks.yaml",
            f"""
- key: multipart
  expect:
    http:
      method: GET
      path: /multipart
  actions:
    - send_http:
        url: {target_base}/upload
        method: POST
        body_from_binary_file: uploads/payload.bin
        binary_file_name: upload.bin
        headers:
          Content-Type: image/custom
    - reply_http:
        status_code: 200
        body: ok
- key: raw
  expect:
    http:
      method: GET
      path: /raw
  actions:
    - send_http:
        url: {target_base}/raw
        method: PUT
        body_from_binary_file: uploads/payload.bin
    - reply_http:
        status_code: 200
        body: ok
- key: inline
  expect:
    http:
      method: GET
      path: /inline-send
  actions:
    - send_http:
        url: {target_base}/inline
        method: POST
        body: inline
        body_from_binary_file: uploads/payload.bin
    - reply_http:
        status_code: 200
        body: ok
""",
        )
        behaviors = hmock.load_behaviors(tmp_path, logger)
        binary_file.write_bytes(b"changed")
        assert behaviors[0].actions[0]["send_http"]["send_http_body_from_binary_file_content"] == b"\x00\xffDATA"
        _, base = server_factory(behaviors)

        assert request(base + "/multipart")[0::2] == (200, "ok")
        assert request(base + "/raw")[0::2] == (200, "ok")
        assert request(base + "/inline-send")[0::2] == (200, "ok")
    finally:
        stop_server(target, target_thread)

    assert records[0]["path"] == "/upload"
    assert records[0]["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="upload.bin"' in records[0]["body_bytes"]
    assert b"Content-Type: image/custom" in records[0]["body_bytes"]
    assert b"\x00\xffDATA" in records[0]["body_bytes"]

    assert records[1]["method"] == "PUT"
    assert records[1]["path"] == "/raw"
    assert records[1]["body_bytes"] == b"\x00\xffDATA"

    assert records[2]["path"] == "/inline"
    assert records[2]["body"] == "inline"


def test_admin_api_templates_crud_reload_and_filesystem_isolation(tmp_path, logger, runtime_server_factory):
    write_yaml(
        tmp_path / "fs.yaml",
        """
- key: fs
  expect:
    http:
      method: GET
      path: /same
  actions:
    - reply_http:
        status_code: 200
        body: fs
""",
    )
    config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_host="127.0.0.1",
        admin_http_port=0,
    )
    _, mock_base, admin_base = runtime_server_factory(config)

    assert json_request(admin_base + "/api/v1/health")[0::2] == (200, {"status": "OK"})
    status, _, definitions = json_request(admin_base + "/api/v1/templates")
    assert status == 200
    assert [raw["key"] for raw in definitions] == ["fs"]

    api_definition = {
        "key": "api",
        "expect": {"http": {"method": "GET", "path": "/api"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", method="POST", value=[api_definition])[0::2] == (200, [api_definition])
    assert request(mock_base + "/api")[0::2] == (200, "api")

    updated_api_definition = {
        "key": "api",
        "expect": {"http": {"method": "GET", "path": "/api"}},
        "actions": [{"reply_http": {"status_code": 201, "body": "api-new"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", method="POST", value=[updated_api_definition])[0::2] == (200, [updated_api_definition])
    assert request(mock_base + "/api")[0::2] == (201, "api-new")

    assert json_request(admin_base + "/api/v1/templates", method="POST", value=[{"key": "bad"}])[0] == 400
    assert request(mock_base + "/api")[0::2] == (201, "api-new")

    fs_override = {
        "key": "fs",
        "expect": {"http": {"method": "GET", "path": "/same"}},
        "actions": [{"reply_http": {"status_code": 202, "body": "api-fs"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", method="POST", value=[fs_override])[0] == 200
    assert request(mock_base + "/same")[0::2] == (202, "api-fs")
    assert request(admin_base + "/api/v1/templates/fs", method="DELETE")[0] == 204
    assert request(mock_base + "/same")[0::2] == (200, "fs")

    assert request(admin_base + "/api/v1/templates/missing", method="DELETE")[0] == 404
    assert request(admin_base + "/api/v1/templates/api", method="DELETE")[0] == 204
    assert request(mock_base + "/api")[0::2] == (404, "not found")


def test_admin_api_template_sets_and_delete_isolation(tmp_path, logger, runtime_server_factory):
    config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_host="127.0.0.1",
        admin_http_port=0,
    )
    _, mock_base, admin_base = runtime_server_factory(config)
    set_a = [
        {
            "key": "set-a",
            "expect": {"http": {"method": "GET", "path": "/set-a"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "a"}}],
        }
    ]
    set_b = [
        {
            "key": "set-b",
            "expect": {"http": {"method": "GET", "path": "/set-b"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "b"}}],
        }
    ]

    assert json_request(admin_base + "/api/v1/template_sets/a", method="POST", value=set_a)[0::2] == (200, set_a)
    assert json_request(admin_base + "/api/v1/template_sets/b", method="POST", value=set_b)[0::2] == (200, set_b)
    assert request(mock_base + "/set-a")[0::2] == (200, "a")
    assert request(mock_base + "/set-b")[0::2] == (200, "b")

    replacement_a = [
        {
            "key": "set-a-new",
            "expect": {"http": {"method": "GET", "path": "/set-a-new"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "a-new"}}],
        }
    ]
    assert json_request(admin_base + "/api/v1/template_sets/a", method="POST", value=replacement_a)[0] == 200
    assert request(mock_base + "/set-a")[0::2] == (404, "not found")
    assert request(mock_base + "/set-a-new")[0::2] == (200, "a-new")

    assert request(admin_base + "/api/v1/template_sets/a", method="DELETE")[0] == 204
    assert request(mock_base + "/set-a-new")[0::2] == (404, "not found")
    assert request(mock_base + "/set-b")[0::2] == (200, "b")


def test_admin_api_accepts_yaml_template_payloads(tmp_path, logger, runtime_server_factory):
    config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_host="127.0.0.1",
        admin_http_port=0,
    )
    _, mock_base, admin_base = runtime_server_factory(config)

    base_yaml = """
- key: yaml-base
  expect:
    http:
      method: GET
      path: /yaml-base
  actions:
    - reply_http:
        status_code: 200
        body: yaml-base
"""
    status, _, submitted = yaml_request(admin_base + "/api/v1/templates", text=base_yaml)
    assert status == 200
    assert submitted[0]["key"] == "yaml-base"
    assert request(mock_base + "/yaml-base")[0::2] == (200, "yaml-base")

    set_yaml = """
- key: yaml-set
  expect:
    http:
      method: GET
      path: /yaml-set
  actions:
    - reply_http:
        status_code: 201
        body: yaml-set
"""
    status, _, submitted = yaml_request(admin_base + "/api/v1/template_sets/s", text=set_yaml)
    assert status == 200
    assert submitted[0]["key"] == "yaml-set"
    assert request(mock_base + "/yaml-set")[0::2] == (201, "yaml-set")

    assert yaml_request(admin_base + "/api/v1/templates", text="- key: bad\n")[0] == 400
    assert yaml_request(admin_base + "/api/v1/template_sets/bad", text="- key: bad\n")[0] == 400


def test_persisted_admin_mocks_load_on_startup(tmp_path, logger, runtime_server_factory):
    store = hmock.MemoryRedisStore()
    first_config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_host="127.0.0.1",
        admin_http_port=0,
    )
    _, _, admin_base = runtime_server_factory(first_config, store)
    base_definition = {
        "key": "persisted-base",
        "expect": {"http": {"method": "GET", "path": "/persisted-base"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "base"}}],
    }
    set_definition = {
        "key": "persisted-set",
        "expect": {"http": {"method": "GET", "path": "/persisted-set"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "set"}}],
    }
    assert json_request(admin_base + "/api/v1/templates", method="POST", value=[base_definition])[0] == 200
    assert json_request(admin_base + "/api/v1/template_sets/s", method="POST", value=[set_definition])[0] == 200

    second_config = hmock.Config(
        templates_dir=str(tmp_path),
        http_host="127.0.0.1",
        http_port=0,
        log_level="debug",
        admin_http_enabled=False,
    )
    _, mock_base, _ = runtime_server_factory(second_config, store)

    assert request(mock_base + "/persisted-base")[0::2] == (200, "base")
    assert request(mock_base + "/persisted-set")[0::2] == (200, "set")


def test_omctl_push_and_delete_commands(tmp_path, monkeypatch, capsys):
    demo_dir = tmp_path / "demo_templates"
    write_yaml(
        demo_dir / "nested" / "a.yaml",
        """
- key: cli-a
  expect:
    http:
      method: GET
      path: /a
  actions:
    - reply_http:
        status_code: 200
""",
    )
    custom_dir = tmp_path / "custom"
    write_yaml(
        custom_dir / "b.yml",
        """
- key: cli-b
  expect:
    http:
      method: GET
      path: /b
  actions:
    - reply_http:
        status_code: 200
""",
    )
    calls = []

    def fake_send(url, method, body=None):
        calls.append((url, method, body))
        return 204 if method == "DELETE" else 200, b"[]"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(omctl, "send_request", fake_send)

    assert omctl.main(["push"]) == 0
    assert calls[-1][0] == "http://localhost:9998/api/v1/templates"
    assert calls[-1][1] == "POST"
    assert "cli-a" in calls[-1][2]

    assert omctl.main(["push", "--directory", str(custom_dir), "--url", "http://admin.test/", "--set-key", "blue"]) == 0
    assert calls[-1][0] == "http://admin.test/api/v1/template_sets/blue"
    assert calls[-1][1] == "POST"
    assert "cli-b" in calls[-1][2]

    assert omctl.main(["delete", "--url", "http://admin.test", "--set-key", "blue"]) == 0
    assert calls[-1] == ("http://admin.test/api/v1/template_sets/blue", "DELETE", None)

    before = len(calls)
    with pytest.raises(SystemExit):
        omctl.main(["delete"])
    assert len(calls) == before
    capsys.readouterr()


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
