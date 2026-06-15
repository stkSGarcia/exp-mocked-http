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


def request(url, method="GET", body=None, headers=None):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()


def request_raw(url, method="GET", body=None, headers=None):
    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


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


class FakeKafkaAdapter:
    def __init__(self, fail_publish=False):
        self.fail_publish = fail_publish
        self.subscribed = ()
        self.callback = None
        self.published = []
        self.closed = False

    def subscribe(self, topics, callback):
        self.subscribed = tuple(topics)
        self.callback = callback

    def publish(self, topic, payload):
        if self.fail_publish:
            raise RuntimeError("kafka down")
        self.published.append((topic, payload))

    def close(self):
        self.closed = True


class FakeAMQPAdapter:
    def __init__(self, fail_publish=False):
        self.fail_publish = fail_publish
        self.bindings = ()
        self.callback = None
        self.published = []
        self.reconnected = False
        self.closed = False

    def declare_and_consume(self, bindings, callback):
        self.bindings = tuple(bindings)
        self.callback = callback

    def publish(self, exchange, routing_key, payload):
        if self.fail_publish:
            raise RuntimeError("amqp down")
        self.published.append((exchange, routing_key, payload))

    def reconnect(self, bindings, callback):
        self.reconnected = True
        self.declare_and_consume(bindings, callback)

    def close(self):
        self.closed = True


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def start_runtime_servers(config, logger, redis_store=None):
    runtime = hmock.HMockRuntime(config, logger, redis_store)
    mock_server = hmock.HMockHTTPServer(("127.0.0.1", 0), None, logger, runtime=runtime)
    admin_server = hmock.HMockAdminHTTPServer(("127.0.0.1", 0), runtime, logger)
    mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
    mock_thread.start()
    admin_thread.start()
    return (
        mock_server,
        mock_thread,
        f"http://127.0.0.1:{mock_server.server_address[1]}",
        admin_server,
        admin_thread,
        f"http://127.0.0.1:{admin_server.server_address[1]}",
    )


def behavior(raw):
    return hmock.validate_behavior(raw)


def test_config_defaults_and_environment_overrides(monkeypatch):
    assert hmock.load_config({}) == hmock.Config()
    defaults = hmock.load_config({})
    assert defaults.kafka_enabled is False
    assert defaults.amqp_enabled is False
    assert hmock.resolve_kafka_producer_config(defaults) == hmock.KafkaClientConfig(
        "hmock",
        ("kafka:9092",),
        "",
        "",
        False,
        False,
    )
    assert hmock.resolve_kafka_consumer_config(defaults) == hmock.KafkaClientConfig(
        "hmock",
        ("kafka:9092",),
        "",
        "",
        False,
        False,
    )

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
            "HM_KAFKA_SEED_BROKERS": "k1:9092, k2:9092",
            "HM_KAFKA_SASL_USERNAME": "shared-user",
            "HM_KAFKA_SASL_PASSWORD": "shared-pass",
            "HM_KAFKA_TLS_ENABLED": "true",
            "HM_KAFKA_PRODUCER_SEED_BROKERS": "kp:9092",
            "HM_KAFKA_CONSUMER_SEED_BROKERS": "kc:9092",
            "HM_KAFKA_SASL_PRODUCER_USERNAME": "producer-user",
            "HM_KAFKA_SASL_PRODUCER_PASSWORD": "producer-pass",
            "HM_KAFKA_SASL_CONSUMER_USERNAME": "consumer-user",
            "HM_KAFKA_TLS_PRODUCER_ENABLED": "false",
            "HM_AMQP_ENABLED": "true",
            "HM_AMQP_URL": "amqp://user:pass@localhost:5673/vhost",
        }
    )

    assert config == hmock.Config(
        "/tmp/mocks",
        7777,
        "127.0.0.1",
        "warn",
        "redis",
        "redis://localhost:6380/2",
        False,
        7778,
        "127.0.0.2",
        False,
        True,
        True,
        "client-a",
        "k1:9092, k2:9092",
        "shared-user",
        "shared-pass",
        True,
        "kp:9092",
        "kc:9092",
        "producer-user",
        "producer-pass",
        "consumer-user",
        "",
        False,
        None,
        True,
        "amqp://user:pass@localhost:5673/vhost",
    )
    assert hmock.resolve_kafka_producer_config(config) == hmock.KafkaClientConfig(
        "client-a",
        ("kp:9092",),
        "producer-user",
        "producer-pass",
        True,
        False,
    )
    assert hmock.resolve_kafka_consumer_config(config) == hmock.KafkaClientConfig(
        "client-a",
        ("kc:9092",),
        "consumer-user",
        "shared-pass",
        True,
        True,
    )

    partial = hmock.load_config({"HM_KAFKA_SASL_USERNAME": "user-only"})
    assert hmock.resolve_kafka_producer_config(partial).sasl_enabled is False


def test_runtime_hot_reload_tracks_filesystem_create_edit_and_delete(tmp_path, logger):
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    mock_server, mock_thread, mock_base, admin_server, admin_thread, _ = start_runtime_servers(config, logger)
    try:
        assert request(mock_base + "/hot")[0::2] == (404, "not found")

        hot_file = tmp_path / "hot.yaml"
        write_yaml(
            hot_file,
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
            hot_file,
            """
- key: hot
  expect:
    http:
      method: GET
      path: /hot
  actions:
    - reply_http:
        status_code: 200
        body: second
""",
        )
        assert request(mock_base + "/hot")[0::2] == (200, "second")

        hot_file.unlink()
        assert request(mock_base + "/hot")[0::2] == (404, "not found")
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)


def test_runtime_hot_reload_can_be_disabled_while_admin_mutations_still_reload(tmp_path, logger):
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
        body: first
""",
    )
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", templates_dir_hot_reload=False)
    mock_server, mock_thread, mock_base, admin_server, admin_thread, admin_base = start_runtime_servers(config, logger)
    try:
        assert request(mock_base + "/hot")[0::2] == (200, "first")
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
        body: second
""",
        )
        assert request(mock_base + "/hot")[0::2] == (200, "first")

        admin_mock = {
            "key": "admin-hot",
            "expect": {"http": {"method": "GET", "path": "/admin-hot"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "admin"}}],
        }
        assert request(admin_base + "/api/v1/templates", method="POST", body=json.dumps([admin_mock]))[0] == 200
        assert request(mock_base + "/admin-hot")[0::2] == (200, "admin")
        assert request(mock_base + "/hot")[0::2] == (200, "second")
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)


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


def test_broker_expectations_actions_and_file_payload_validation(tmp_path, logger):
    payload_file = tmp_path / "payloads" / "message.txt"
    payload_file.parent.mkdir()
    payload_file.write_text("file {{ .KafkaPayload }} {{ .AMQPPayload }}")
    write_yaml(
        tmp_path / "broker.yaml",
        """
- key: kafka-file
  expect:
    kafka:
      topic: in
  actions:
    - publish_kafka:
        topic: out
        payload_from_file: payloads/message.txt
- key: amqp-file
  expect:
    amqp:
      exchange: events
      routing_key: created
  actions:
    - publish_amqp:
        exchange: outbound
        routing_key: done
        payload_from_file: payloads/message.txt
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    payload_file.write_text("changed")

    assert behaviors[0].method == ""
    assert behaviors[0].pattern is None
    assert behaviors[0].kafka_topic == "in"
    assert behaviors[0].actions[0]["publish_kafka"]["publish_kafka_payload_from_file_content"] == "file {{ .KafkaPayload }} {{ .AMQPPayload }}"
    assert behaviors[1].amqp_exchange == "events"
    assert behaviors[1].amqp_routing_key == "created"
    assert behaviors[1].amqp_queue == "created"
    assert behaviors[1].actions[0]["publish_amqp"]["publish_amqp_payload_from_file_content"] == "file {{ .KafkaPayload }} {{ .AMQPPayload }}"

    invalid_behaviors = [
        {"key": "missing-kafka-topic", "expect": {"kafka": {}}, "actions": []},
        {"key": "bad-kafka-topic", "expect": {"kafka": {"topic": ""}}, "actions": []},
        {"key": "missing-amqp-exchange", "expect": {"amqp": {"routing_key": "rk"}}, "actions": []},
        {"key": "missing-amqp-routing", "expect": {"amqp": {"exchange": "ex"}}, "actions": []},
        {"key": "bad-amqp-queue", "expect": {"amqp": {"exchange": "ex", "routing_key": "rk", "queue": 1}}, "actions": []},
        {
            "key": "bad-kafka-action-topic",
            "expect": {"kafka": {"topic": "in"}},
            "actions": [{"publish_kafka": {"payload": "x"}}],
        },
        {
            "key": "bad-kafka-action-payload",
            "expect": {"kafka": {"topic": "in"}},
            "actions": [{"publish_kafka": {"topic": "out"}}],
        },
        {
            "key": "bad-amqp-action-exchange",
            "expect": {"amqp": {"exchange": "ex", "routing_key": "rk"}},
            "actions": [{"publish_amqp": {"routing_key": "rk", "payload": "x"}}],
        },
        {
            "key": "bad-amqp-action-routing",
            "expect": {"amqp": {"exchange": "ex", "routing_key": "rk"}},
            "actions": [{"publish_amqp": {"exchange": "ex", "payload": "x"}}],
        },
        {
            "key": "bad-amqp-action-payload",
            "expect": {"amqp": {"exchange": "ex", "routing_key": "rk"}},
            "actions": [{"publish_amqp": {"exchange": "ex", "routing_key": "rk"}}],
        },
    ]
    for raw in invalid_behaviors:
        with pytest.raises(hmock.ValidationError):
            hmock.validate_behavior(raw)

    write_yaml(
        tmp_path / "missing-broker-payload.yaml",
        """
- key: missing-broker-payload
  expect:
    kafka:
      topic: in
  actions:
    - publish_kafka:
        topic: out
        payload_from_file: payloads/missing.txt
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_broker_payload_file_rejects_paths_outside_templates_dir(tmp_path, logger):
    outside = tmp_path.parent / f"{tmp_path.name}-broker.txt"
    outside.write_text("outside")
    write_yaml(
        tmp_path / "outside-broker.yaml",
        f"""
- key: outside-broker
  expect:
    kafka:
      topic: in
  actions:
    - publish_kafka:
        topic: out
        payload_from_file: ../{outside.name}
""",
    )

    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_binary_file_payload_loading_validation_and_snapshot(tmp_path, logger):
    response_file = tmp_path / "files" / "response.bin"
    callback_file = tmp_path / "files" / "callback.bin"
    response_file.parent.mkdir()
    response_file.write_bytes(b"\x00response{{ .HTTPBody }}")
    callback_file.write_bytes(b"\xffcallback")
    write_yaml(
        tmp_path / "binary.yaml",
        """
- key: binary
  expect:
    http:
      method: GET
      path: /binary
  actions:
    - send_http:
        url: http://127.0.0.1:9999/callback
        method: POST
        body_from_binary_file: files/callback.bin
        binary_file_name: callback.dat
    - reply_http:
        status_code: 200
        body_from_binary_file: files/response.bin
        binary_file_name: response.dat
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    response_file.write_bytes(b"changed")
    callback_file.write_bytes(b"changed")

    send_payload = behaviors[0].actions[0]["send_http"]
    reply_payload = behaviors[0].actions[1]["reply_http"]
    assert send_payload["send_http_body_from_binary_file_content"] == b"\xffcallback"
    assert send_payload["binary_file_name"] == "callback.dat"
    assert reply_payload["body_from_binary_file_content"] == b"\x00response{{ .HTTPBody }}"
    assert reply_payload["binary_file_name"] == "response.dat"

    invalid_actions = [
        {"reply_http": {"status_code": 200, "body_from_binary_file": ""}},
        {"reply_http": {"status_code": 200, "body_from_binary_file": "files/response.bin", "binary_file_name": 1}},
        {"send_http": {"url": "http://example.test", "method": "POST", "body_from_binary_file": ""}},
        {"send_http": {"url": "http://example.test", "method": "POST", "body_from_binary_file": "files/callback.bin", "binary_file_name": 1}},
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
        tmp_path / "missing-binary.yaml",
        """
- key: missing-binary
  expect:
    http:
      method: GET
      path: /missing-binary
  actions:
    - reply_http:
        status_code: 200
        body_from_binary_file: files/missing.bin
""",
    )
    with pytest.raises(hmock.ValidationError):
        hmock.load_behaviors(tmp_path, logger)


def test_binary_file_payloads_reject_paths_outside_templates_dir(tmp_path, logger):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.bin"
    outside.write_bytes(b"outside")
    write_yaml(
        tmp_path / "outside-binary.yaml",
        f"""
- key: outside-binary
  expect:
    http:
      method: GET
      path: /outside-binary
  actions:
    - send_http:
        url: http://127.0.0.1:9999/callback
        method: PUT
        body_from_binary_file: ../{outside.name}
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


def test_kafka_runtime_subscribes_matches_in_order_and_publishes(tmp_path, logger):
    write_yaml(
        tmp_path / "kafka.yaml",
        """
- key: remember
  expect:
    condition: '{{ .KafkaPayload | eq "go" }}'
    kafka:
      topic: in
  actions:
    - redis:
        - SET seen {{ .KafkaTopic }}
- key: publish
  expect:
    condition: '{{ .KafkaPayload | eq "go" }}'
    kafka:
      topic: in
  actions:
    - publish_kafka:
        topic: out-{{ .KafkaTopic }}
        payload: '{{ .KafkaPayload }}:{{ redisDo "GET seen" }}'
- key: bad-condition
  expect:
    condition: '{{ .Missing }}'
    kafka:
      topic: in
  actions:
    - redis:
        - SET bad yes
- key: other-topic
  expect:
    kafka:
      topic: other
  actions:
    - redis:
        - SET other yes
""",
    )
    store = hmock.MemoryRedisStore()
    kafka = FakeKafkaAdapter()
    runtime = hmock.HMockRuntime(
        hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", kafka_enabled=True),
        logger,
        store,
        kafka_adapter=kafka,
    )

    assert kafka.subscribed == ("in", "other")
    assert kafka.callback is not None

    kafka.callback("in", "go")

    assert store.do("GET seen") == "in"
    assert store.do("GET bad") == ""
    assert store.do("GET other") == ""
    assert kafka.published == [("out-in", "go:in")]

    write_yaml(
        tmp_path / "kafka.yaml",
        """
- key: replacement
  expect:
    kafka:
      topic: replacement
  actions:
    - redis:
        - SET replacement yes
""",
    )
    runtime.reload()
    assert kafka.subscribed == ("replacement",)
    runtime.close()
    assert kafka.closed is True


def test_amqp_runtime_declares_matches_reconnects_and_publishes(tmp_path, logger):
    write_yaml(
        tmp_path / "amqp.yaml",
        """
- key: remember-amqp
  expect:
    condition: '{{ .AMQPQueue | eq "created" }}'
    amqp:
      exchange: events
      routing_key: created
  actions:
    - redis:
        - SET amqp {{ .AMQPPayload }}
- key: publish-amqp
  expect:
    condition: '{{ .AMQPExchange | eq "events" }}'
    amqp:
      exchange: events
      routing_key: created
  actions:
    - publish_amqp:
        exchange: outbound-{{ .AMQPExchange }}
        routing_key: done-{{ .AMQPRoutingKey }}
        payload: '{{ redisDo "GET amqp" }}:{{ .AMQPQueue }}'
- key: custom-queue
  expect:
    amqp:
      exchange: events
      routing_key: updated
      queue: updates
  actions:
    - redis:
        - SET updated yes
""",
    )
    store = hmock.MemoryRedisStore()
    amqp = FakeAMQPAdapter()
    runtime = hmock.HMockRuntime(
        hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", amqp_enabled=True),
        logger,
        store,
        amqp_adapter=amqp,
    )

    assert amqp.bindings == (
        hmock.AMQPBinding("events", "created", "created"),
        hmock.AMQPBinding("events", "updated", "updates"),
    )
    assert amqp.callback is not None

    amqp.callback("events", "created", "created", "payload")

    assert store.do("GET amqp") == "payload"
    assert store.do("GET updated") == ""
    assert amqp.published == [("outbound-events", "done-created", "payload:created")]

    runtime.recover_amqp_consumption()
    assert amqp.reconnected is True
    assert amqp.bindings == (
        hmock.AMQPBinding("events", "created", "created"),
        hmock.AMQPBinding("events", "updated", "updates"),
    )
    runtime.close()
    assert amqp.closed is True


def test_broker_publish_failures_log_and_continue(logger, log_stream):
    kafka_behavior = hmock.validate_behavior(
        {
            "key": "kafka-failure",
            "expect": {"kafka": {"topic": "in"}},
            "actions": [
                {"publish_kafka": {"topic": "out", "payload": "payload"}},
                {"redis": ["SET kafka-after yes"]},
            ],
        }
    )
    amqp_behavior = hmock.validate_behavior(
        {
            "key": "amqp-failure",
            "expect": {"amqp": {"exchange": "ex", "routing_key": "rk"}},
            "actions": [
                {"publish_amqp": {"exchange": "out", "routing_key": "done", "payload": "payload"}},
                {"redis": ["SET amqp-after yes"]},
            ],
        }
    )
    store = hmock.MemoryRedisStore()

    hmock.execute_behavior(
        kafka_behavior,
        hmock.BrokerMessageInfo("kafka", "payload", kafka_topic="in"),
        {},
        store,
        logger,
        kafka_adapter=FakeKafkaAdapter(fail_publish=True),
    )
    hmock.execute_behavior(
        amqp_behavior,
        hmock.BrokerMessageInfo("amqp", "payload", amqp_exchange="ex", amqp_routing_key="rk", amqp_queue="rk"),
        {},
        store,
        logger,
        amqp_adapter=FakeAMQPAdapter(fail_publish=True),
    )

    assert store.do("GET kafka-after") == "yes"
    assert store.do("GET amqp-after") == "yes"
    logs = log_stream.getvalue()
    assert "publish_kafka failed" in logs
    assert "publish_amqp failed" in logs


def test_broker_only_behaviors_do_not_affect_http_first_match(server_factory):
    behaviors = [
        behavior(
            {
                "key": "broker-only",
                "expect": {"kafka": {"topic": "in"}},
                "actions": [{"redis": ["SET broker yes"]}],
            }
        ),
        behavior(
            {
                "key": "first",
                "expect": {"http": {"method": "GET", "path": "/same"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "first"}}],
            }
        ),
        behavior(
            {
                "key": "second",
                "expect": {"http": {"method": "GET", "path": "/same"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "second"}}],
            }
        ),
    ]
    _, base = server_factory(behaviors)

    assert request(base + "/same")[0::2] == (200, "first")


def test_mock_server_cors_headers_preflight_and_header_precedence(tmp_path, logger):
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
        status_code: 204
        headers:
          X-Explicit: yes
""",
    )
    disabled = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    mock_server, mock_thread, mock_base, admin_server, admin_thread, _ = start_runtime_servers(disabled, logger)
    try:
        status, headers, body = request(mock_base + "/cors")
        assert (status, body) == (200, "cors")
        assert "Access-Control-Allow-Methods" not in headers
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)

    enabled = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", cors_enabled=True)
    mock_server, mock_thread, mock_base, admin_server, admin_thread, _ = start_runtime_servers(enabled, logger)
    try:
        status, headers, body = request(mock_base + "/cors")
        assert (status, body) == (200, "cors")
        assert headers["Access-Control-Allow-Origin"] == "https://example.test"
        assert headers["Access-Control-Allow-Methods"] == "*"
        assert headers["Access-Control-Allow-Headers"] == "*"
        assert headers["Access-Control-Allow-Credentials"] == "true"

        status, headers, body = request(mock_base + "/explicit", method="OPTIONS")
        assert (status, body) == (204, "")
        assert headers["X-Explicit"] == "yes"
        assert headers["Access-Control-Allow-Origin"] == "*"

        status, headers, body = request(mock_base + "/unmatched", method="OPTIONS")
        assert (status, body) == (200, "")
        assert headers["Content-Length"] == "0"
        assert headers["Access-Control-Allow-Origin"] == "*"

        status, headers, body = request(mock_base + "/unmatched")
        assert (status, body) == (404, "not found")
        assert headers["Access-Control-Allow-Origin"] == "*"
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)


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


def test_binary_response_body_sends_exact_bytes_and_precedence(tmp_path, logger, server_factory):
    binary_file = tmp_path / "files" / "response.bin"
    binary_file.parent.mkdir()
    binary_file.write_bytes(b"\x00\xff{{ .HTTPBody }}")
    write_yaml(
        tmp_path / "binary-response.yaml",
        """
- key: binary-response
  expect:
    http:
      method: GET
      path: /binary
  actions:
    - reply_http:
        status_code: 200
        body_from_binary_file: files/response.bin
        binary_file_name: response.bin
- key: inline-wins
  expect:
    http:
      method: GET
      path: /inline-wins
  actions:
    - reply_http:
        status_code: 200
        body: inline
        body_from_binary_file: files/response.bin
- key: empty-uses-binary
  expect:
    http:
      method: GET
      path: /empty-uses-binary
  actions:
    - reply_http:
        status_code: 200
        body: ""
        body_from_binary_file: files/response.bin
""",
    )
    _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

    status, headers, body = request_raw(base + "/binary")
    assert (status, body) == (200, b"\x00\xff{{ .HTTPBody }}")
    assert headers["Content-Length"] == str(len(body))
    assert headers["Content-Disposition"] == 'inline; filename="response.bin"'

    assert request_raw(base + "/inline-wins")[0::2] == (200, b"inline")
    assert request_raw(base + "/empty-uses-binary")[0::2] == (200, b"\x00\xff{{ .HTTPBody }}")


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
            "body_bytes": b"sent abc 42",
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


def test_send_http_binary_file_multipart_raw_and_inline_precedence(tmp_path, logger, server_factory):
    upload_file = tmp_path / "upload.bin"
    raw_file = tmp_path / "raw.bin"
    upload_file.write_bytes(b"\x00upload")
    raw_file.write_bytes(b"\xffraw")
    target, target_thread, records, target_base = start_capture_server()
    try:
        write_yaml(
            tmp_path / "binary-callbacks.yaml",
            f"""
- key: upload-default
  expect:
    http:
      method: GET
      path: /upload-default
  actions:
    - send_http:
        url: {target_base}/upload-default
        method: POST
        body_from_binary_file: upload.bin
    - reply_http:
        status_code: 200
        body: ok
- key: upload-named
  expect:
    http:
      method: GET
      path: /upload-named
  actions:
    - send_http:
        url: {target_base}/upload-named
        method: POST
        body_from_binary_file: upload.bin
        binary_file_name: named.dat
        headers:
          Content-Type: image/png
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
        body_from_binary_file: raw.bin
    - reply_http:
        status_code: 200
        body: ok
- key: inline-wins
  expect:
    http:
      method: GET
      path: /inline-wins
  actions:
    - send_http:
        url: {target_base}/inline-wins
        method: POST
        body: inline
        body_from_binary_file: upload.bin
    - reply_http:
        status_code: 200
        body: ok
""",
        )
        _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

        assert request(base + "/upload-default")[0::2] == (200, "ok")
        assert request(base + "/upload-named")[0::2] == (200, "ok")
        assert request(base + "/raw")[0::2] == (200, "ok")
        assert request(base + "/inline-wins")[0::2] == (200, "ok")
    finally:
        stop_server(target, target_thread)

    default_upload = records[0]
    assert default_upload["path"] == "/upload-default"
    assert default_upload["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="upload.bin"' in default_upload["body_bytes"]
    assert b"Content-Type: application/octet-stream" in default_upload["body_bytes"]
    assert b"\x00upload" in default_upload["body_bytes"]

    named_upload = records[1]
    assert named_upload["path"] == "/upload-named"
    assert b'name="file"; filename="named.dat"' in named_upload["body_bytes"]
    assert b"Content-Type: image/png" in named_upload["body_bytes"]

    raw = records[2]
    assert raw["method"] == "PUT"
    assert raw["body_bytes"] == b"\xffraw"

    inline = records[3]
    assert inline["body_bytes"] == b"inline"


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


def test_build_servers_honors_admin_enabled_configuration(tmp_path, logger):
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", admin_http_enabled=False)
    mock_server, admin_server = hmock.build_servers(config, logger)
    try:
        assert isinstance(mock_server, hmock.HMockHTTPServer)
        assert admin_server is None
    finally:
        mock_server.server_close()

    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", admin_http_port=0, admin_http_host="127.0.0.1")
    mock_server, admin_server = hmock.build_servers(config, logger)
    try:
        assert isinstance(admin_server, hmock.HMockAdminHTTPServer)
        assert admin_server.server_address[0] == "127.0.0.1"
    finally:
        mock_server.server_close()
        admin_server.server_close()


def test_admin_mock_store_persists_base_templates_and_isolated_sets():
    store = hmock.MemoryRedisStore()
    admin_store = hmock.AdminMockStore(store)
    base = [
        {
            "key": "base",
            "expect": {"http": {"method": "GET", "path": "/base"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "hello base"}}],
        }
    ]
    set_one = [
        {
            "key": "set-one",
            "expect": {"http": {"method": "GET", "path": "/one"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "one"}}],
        }
    ]
    set_two = [
        {
            "key": "set-two",
            "expect": {"http": {"method": "GET", "path": "/two"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "two"}}],
        }
    ]

    admin_store.save_base_templates(base)
    admin_store.save_template_set("set one", set_one)
    admin_store.save_template_set("set-two", set_two)

    assert admin_store.load_base_templates() == base
    assert admin_store.load_template_sets() == {"set one": set_one, "set-two": set_two}

    replacement = [{**set_one[0], "key": "set-one-replaced"}]
    admin_store.save_template_set("set one", replacement)
    admin_store.delete_template_set("set-two")

    assert admin_store.load_template_sets() == {"set one": replacement}


def test_runtime_loads_persisted_mocks_and_applies_deterministic_merge_order(tmp_path, logger):
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
""",
    )
    store = hmock.MemoryRedisStore()
    admin_store = hmock.AdminMockStore(store)
    admin_store.save_base_templates(
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/shared"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "base"}}],
            }
        ]
    )
    admin_store.save_template_set(
        "b",
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/shared"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "set-b"}}],
            }
        ],
    )
    admin_store.save_template_set(
        "a",
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/shared"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "set-a"}}],
            }
        ],
    )

    runtime = hmock.HMockRuntime(hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug"), logger, store)
    request_info = hmock.RequestInfo("GET", "/shared", "/shared", "", "", {}, "")
    selected, params = hmock.find_behavior(runtime.get_behaviors(), request_info, store)

    assert hmock.execute_behavior(selected, request_info, params, store).body == "set-b"
    assert [raw["key"] for raw in runtime.get_definitions()] == ["shared"]


def test_admin_api_endpoints_validation_delete_and_isolation(tmp_path, logger):
    write_yaml(
        tmp_path / "fs.yaml",
        """
- key: fs-only
  expect:
    http:
      method: GET
      path: /fs
  actions:
    - reply_http:
        status_code: 200
        body: fs
""",
    )
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    mock_server, mock_thread, mock_base, admin_server, admin_thread, admin_base = start_runtime_servers(config, logger)
    try:
        assert request(admin_base + "/api/v1/health")[0::2] == (200, '{"status":"OK"}')

        base_mock = {
            "key": "api-one",
            "expect": {"http": {"method": "GET", "path": "/api-one"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
        }
        status, _, body = request(
            admin_base + "/api/v1/templates",
            method="POST",
            body=json.dumps([base_mock]),
            headers={"Content-Type": "application/json"},
        )
        assert (status, json.loads(body)) == (200, [base_mock])
        assert request(mock_base + "/api-one")[0::2] == (200, "api")

        status, _, body = request(admin_base + "/api/v1/templates", method="POST", body=json.dumps([{"key": ""}]))
        assert status == 400
        assert "error" in json.loads(body)

        set_mock = {
            "key": "set-one",
            "expect": {"http": {"method": "GET", "path": "/set-one"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "set"}}],
        }
        assert request(
            admin_base + "/api/v1/template_sets/set-one",
            method="POST",
            body=json.dumps([set_mock]),
            headers={"Content-Type": "application/json"},
        )[0] == 200

        status, _, body = request(admin_base + "/api/v1/templates")
        keys = {raw["key"] for raw in json.loads(body)}
        assert status == 200
        assert {"fs-only", "api-one", "set-one"} <= keys

        assert request(admin_base + "/api/v1/templates/missing", method="DELETE")[0] == 404
        assert request(admin_base + "/api/v1/templates/api-one", method="DELETE")[0] == 204
        assert request(mock_base + "/api-one")[0::2] == (404, "not found")
        assert request(mock_base + "/set-one")[0::2] == (200, "set")

        assert request(admin_base + "/api/v1/templates", method="DELETE")[0] == 204
        assert request(mock_base + "/fs")[0::2] == (200, "fs")
        assert request(mock_base + "/set-one")[0::2] == (200, "set")
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)


def test_admin_api_accepts_yaml_payloads_and_rejects_invalid_yaml(tmp_path, logger):
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    mock_server, mock_thread, mock_base, admin_server, admin_thread, admin_base = start_runtime_servers(config, logger)
    try:
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
        status, _, body = request(
            admin_base + "/api/v1/templates",
            method="POST",
            body=base_yaml,
            headers={"Content-Type": "application/yaml"},
        )
        assert status == 200
        assert json.loads(body)[0]["key"] == "yaml-base"
        assert request(mock_base + "/yaml-base")[0::2] == (200, "yaml-base")

        set_yaml = """
- key: yaml-set
  expect:
    http:
      method: GET
      path: /yaml-set
  actions:
    - reply_http:
        status_code: 200
        body: yaml-set
"""
        status, _, body = request(
            admin_base + "/api/v1/template_sets/yaml",
            method="POST",
            body=set_yaml,
            headers={"Content-Type": "text/yaml"},
        )
        assert status == 200
        assert json.loads(body)[0]["key"] == "yaml-set"
        assert request(mock_base + "/yaml-set")[0::2] == (200, "yaml-set")

        status, _, body = request(
            admin_base + "/api/v1/templates",
            method="POST",
            body="not: an array",
            headers={"Content-Type": "application/yaml"},
        )
        assert status == 400
        assert "error" in json.loads(body)

        status, _, body = request(
            admin_base + "/api/v1/template_sets/yaml",
            method="POST",
            body="- key: ''",
            headers={"Content-Type": "application/yaml"},
        )
        assert status == 400
        assert "error" in json.loads(body)
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)


def test_template_set_delete_leaves_other_sets_and_base_mocks_active(tmp_path, logger):
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    mock_server, mock_thread, mock_base, admin_server, admin_thread, admin_base = start_runtime_servers(config, logger)
    try:
        base_mock = {
            "key": "base",
            "expect": {"http": {"method": "GET", "path": "/base"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "base"}}],
        }
        set_a = {
            "key": "set-a",
            "expect": {"http": {"method": "GET", "path": "/set-a"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "a"}}],
        }
        set_b = {
            "key": "set-b",
            "expect": {"http": {"method": "GET", "path": "/set-b"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "b"}}],
        }
        assert request(admin_base + "/api/v1/templates", method="POST", body=json.dumps([base_mock]))[0] == 200
        assert request(admin_base + "/api/v1/template_sets/a", method="POST", body=json.dumps([set_a]))[0] == 200
        assert request(admin_base + "/api/v1/template_sets/b", method="POST", body=json.dumps([set_b]))[0] == 200

        assert request(admin_base + "/api/v1/template_sets/a", method="DELETE")[0] == 204

        assert request(mock_base + "/set-a")[0::2] == (404, "not found")
        assert request(mock_base + "/set-b")[0::2] == (200, "b")
        assert request(mock_base + "/base")[0::2] == (200, "base")
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)


def test_reserved_redis_keyspace_is_blocked_for_redis_do(server_factory):
    store = hmock.MemoryRedisStore()
    ctx = hmock.build_template_context(
        {},
        "",
        "/",
        "",
        {},
        lambda command: hmock.protected_redis_do(store, command),
        templates={"touch": '{{ redisDo "GET __hmock_internal:templates" }}'},
    )

    with pytest.raises(hmock.RedisError):
        hmock.render_template('{{ redisDo "GET __hmock_internal:templates" }}', ctx)
    with pytest.raises(hmock.RedisError):
        hmock.render_template('{{ redisDo "KEYS __hmock_internal:*" }}', ctx)
    with pytest.raises(hmock.RedisError):
        hmock.render_template('{{ template "touch" . }}', ctx)

    assert hmock.render_template('{{ redisDo "SET user_key ok" }} {{ redisDo "GET user_key" }}', ctx) == "OK ok"
    assert store.do("GET __hmock_internal:templates") == ""

    behaviors = [
        behavior(
            {
                "key": "blocked-condition",
                "expect": {
                    "condition": '{{ redisDo "GET __hmock_internal:templates" | eq "x" }}',
                    "http": {"method": "GET", "path": "/condition"},
                },
                "actions": [{"reply_http": {"status_code": 200}}],
            }
        ),
        behavior(
            {
                "key": "blocked-body",
                "expect": {"http": {"method": "GET", "path": "/body"}},
                "actions": [{"reply_http": {"status_code": 200, "body": '{{ redisDo "GET __hmock_internal:templates" }}'}}],
            }
        ),
        behavior(
            {
                "key": "blocked-header",
                "expect": {"http": {"method": "GET", "path": "/header"}},
                "actions": [{"reply_http": {"status_code": 200, "headers": {"X-Blocked": '{{ redisDo "GET __hmock_internal:templates" }}'}}}],
            }
        ),
    ]
    _, base = server_factory(behaviors)

    assert request(base + "/condition")[0::2] == (404, "not found")
    assert request(base + "/body")[0::2] == (500, "template render error")
    assert request(base + "/header")[0::2] == (500, "template render error")


def test_admin_created_mocks_persist_across_runtime_restart(tmp_path, logger):
    store = hmock.MemoryRedisStore()
    config = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug")
    mock_server, mock_thread, mock_base, admin_server, admin_thread, admin_base = start_runtime_servers(config, logger, store)
    try:
        admin_mock = {
            "key": "persisted",
            "expect": {"http": {"method": "GET", "path": "/persisted"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "persisted"}}],
        }
        assert request(admin_base + "/api/v1/templates", method="POST", body=json.dumps([admin_mock]))[0] == 200
        assert request(mock_base + "/persisted")[0::2] == (200, "persisted")
    finally:
        stop_server(admin_server, admin_thread)
        stop_server(mock_server, mock_thread)

    runtime = hmock.HMockRuntime(config, logger, store)
    request_info = hmock.RequestInfo("GET", "/persisted", "/persisted", "", "", {}, "")
    selected, params = hmock.find_behavior(runtime.get_behaviors(), request_info, store)

    assert selected is not None
    assert hmock.execute_behavior(selected, request_info, params, store).body == "persisted"


def test_omctl_push_delete_flags_and_payloads(tmp_path, monkeypatch):
    demo = tmp_path / "demo_templates"
    write_yaml(
        demo / "a.yaml",
        """
- key: a
""",
    )
    write_yaml(
        demo / "nested" / "b.yml",
        """
- key: b
""",
    )
    records = []

    def fake_request(url, method, body=None, headers=None):
        records.append({"url": url, "method": method, "body": body, "headers": headers or {}})
        return 204 if method == "DELETE" else 200

    monkeypatch.setattr(omctl, "_request", fake_request)
    monkeypatch.chdir(tmp_path)

    assert omctl.main(["push"]) == 0
    assert records[-1]["url"] == "http://localhost:9998/api/v1/templates"
    assert records[-1]["method"] == "POST"
    assert records[-1]["headers"] == {"Content-Type": "application/yaml"}
    assert "- key: a" in records[-1]["body"]
    assert "- key: b" in records[-1]["body"]

    custom = tmp_path / "templates"
    write_yaml(custom / "custom.yaml", "- key: custom\n")
    assert omctl.main(["push", "-d", str(custom), "-u", "http://admin.test", "-k", "smoke set"]) == 0
    assert records[-1]["url"] == "http://admin.test/api/v1/template_sets/smoke+set"
    assert records[-1]["body"] == "- key: custom\n"

    assert omctl.main(["delete", "-u", "http://admin.test", "-k", "smoke set"]) == 0
    assert records[-1]["url"] == "http://admin.test/api/v1/template_sets/smoke+set"
    assert records[-1]["method"] == "DELETE"


def test_omctl_help_missing_set_key_and_non_success(monkeypatch, capsys):
    with pytest.raises(SystemExit) as help_exit:
        omctl.main(["--help"])
    assert help_exit.value.code == 0
    assert "push" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        omctl.main(["delete"])

    monkeypatch.setattr(omctl, "load_yaml_payload", lambda directory: "- key: a\n")
    monkeypatch.setattr(omctl, "_request", lambda *args, **kwargs: 500)
    assert omctl.main(["push"]) == 1
    assert "push failed with status 500" in capsys.readouterr().err
