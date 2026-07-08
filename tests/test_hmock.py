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

    def start(behaviors, level="debug", cors_enabled=False):
        active_logger = logger if level == "debug" else hmock.JsonLogger(level, stream=io.StringIO())
        server = hmock.HMockHTTPServer(("127.0.0.1", 0), behaviors, active_logger, cors_enabled=cors_enabled)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server, f"http://127.0.0.1:{server.server_address[1]}"

    yield start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def raw_request(url, method="GET", body=None, headers=None):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def request(url, method="GET", body=None, headers=None):
    status, headers, body_bytes = raw_request(url, method, body, headers)
    return status, headers, body_bytes.decode()


def json_request(url, method="GET", payload=None):
    body = json.dumps(payload) if payload is not None else None
    return request(url, method=method, body=body, headers={"Content-Type": "application/json"})


def start_admin_server(registry, logger):
    server = hmock.HMockAdminServer(("127.0.0.1", 0), registry, logger)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def start_capture_server(response_status=202, delete_status=None):
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
            status = delete_status if self.command == "DELETE" and delete_status is not None else response_status
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_PUT(self):
            self._handle()

        def do_DELETE(self):
            self._handle()

    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, records, f"http://127.0.0.1:{server.server_address[1]}"


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def behavior(raw):
    return hmock.validate_behavior(raw)


def test_config_defaults_and_environment_overrides(monkeypatch):
    assert hmock.load_config({}) == hmock.Config()
    assert hmock.load_config({}).templates_dir_hot_reload is True
    assert hmock.load_config({}).cors_enabled is False

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
    )


def test_admin_config_defaults_overrides_and_disabled_server(tmp_path, logger):
    config = hmock.load_config({})
    assert config.admin_http_enabled is True
    assert config.admin_http_port == 9998
    assert config.admin_http_host == "0.0.0.0"

    redis_store = hmock.MemoryRedisStore()
    registry = hmock.ActiveMockRegistry(tmp_path, redis_store, logger)

    enabled = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", "memory", "redis://redis:6379", True, 0, "127.0.0.1")
    admin_server = hmock.build_admin_server(enabled, registry, logger)
    assert admin_server is not None
    admin_server.server_close()

    disabled = hmock.Config(str(tmp_path), 0, "127.0.0.1", "debug", "memory", "redis://redis:6379", False, 0, "127.0.0.1")
    assert hmock.build_admin_server(disabled, registry, logger) is None


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


def test_binary_reply_http_bytes_metadata_snapshot_and_precedence(tmp_path, logger, server_factory):
    binary_file = tmp_path / "responses" / "payload.bin"
    binary_file.parent.mkdir()
    binary_file.write_bytes(b"\x00{{ .HTTPBody }}\xff")
    write_yaml(
        tmp_path / "binary.yaml",
        """
- key: binary
  expect:
    http:
      method: POST
      path: /binary
  actions:
    - reply_http:
        status_code: 200
        body_from_binary_file: responses/payload.bin
        binary_file_name: report.bin
- key: text-wins
  expect:
    http:
      method: GET
      path: /text-wins
  actions:
    - reply_http:
        status_code: 200
        body: text body
        body_from_binary_file: responses/payload.bin
- key: empty-allows-binary
  expect:
    http:
      method: GET
      path: /empty-allows-binary
  actions:
    - reply_http:
        status_code: 200
        body: ""
        body_from_binary_file: responses/payload.bin
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    binary_file.write_bytes(b"changed")
    _, base = server_factory(behaviors)

    status, headers, body = raw_request(base + "/binary", method="POST", body="payload")
    assert status == 200
    assert body == b"\x00{{ .HTTPBody }}\xff"
    assert headers["Content-Length"] == str(len(body))
    assert headers["Content-Disposition"] == 'inline; filename="report.bin"'

    assert request(base + "/text-wins")[0::2] == (200, "text body")
    assert raw_request(base + "/empty-allows-binary")[2] == b"\x00{{ .HTTPBody }}\xff"


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


def test_cors_headers_precedence_and_preflight(server_factory):
    behaviors = [
        behavior(
            {
                "key": "cors",
                "expect": {"http": {"method": "GET", "path": "/cors"}},
                "actions": [
                    {
                        "reply_http": {
                            "status_code": 200,
                            "headers": {"Access-Control-Allow-Origin": "https://example.test"},
                            "body": "ok",
                        }
                    }
                ],
            }
        ),
        behavior(
            {
                "key": "options",
                "expect": {"http": {"method": "OPTIONS", "path": "/explicit"}},
                "actions": [{"reply_http": {"status_code": 204, "headers": {"X-Explicit": "yes"}}}],
            }
        ),
    ]
    _, enabled_base = server_factory(behaviors, cors_enabled=True)

    status, headers, body = request(enabled_base + "/cors")
    assert (status, body) == (200, "ok")
    assert headers["Access-Control-Allow-Origin"] == "https://example.test"
    assert headers["Access-Control-Allow-Methods"] == "*"
    assert headers["Access-Control-Allow-Headers"] == "*"
    assert headers["Access-Control-Allow-Credentials"] == "true"

    status, headers, body = request(enabled_base + "/unmatched", method="OPTIONS")
    assert (status, body) == (200, "")
    assert headers["Access-Control-Allow-Origin"] == "*"

    status, headers, body = request(enabled_base + "/explicit", method="OPTIONS")
    assert (status, body) == (204, "")
    assert headers["X-Explicit"] == "yes"
    assert headers["Access-Control-Allow-Origin"] == "*"

    _, disabled_base = server_factory(behaviors, cors_enabled=False)
    status, headers, body = request(disabled_base + "/missing", method="OPTIONS")
    assert (status, body) == (404, "not found")
    assert "Access-Control-Allow-Origin" not in headers


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


def test_send_http_binary_file_post_multipart_and_raw_non_post(tmp_path, logger, server_factory):
    upload_file = tmp_path / "upload.bin"
    upload_file.write_bytes(b"\x00upload\xff")
    raw_file = tmp_path / "raw.bin"
    raw_file.write_bytes(b"\x01raw\xfe")
    target, target_thread, records, target_base = start_capture_server()
    try:
        write_yaml(
            tmp_path / "binary-send.yaml",
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
          X-Meta: yes
    - reply_http:
        status_code: 200
        body: ok
- key: raw-binary
  expect:
    http:
      method: GET
      path: /raw-binary
  actions:
    - send_http:
        url: {target_base}/raw-binary
        method: PUT
        body_from_binary_file: raw.bin
        headers:
          Content-Type: application/custom
    - reply_http:
        status_code: 200
        body: ok
""",
        )
        _, base = server_factory(hmock.load_behaviors(tmp_path, logger))
        assert request(base + "/upload-default")[0::2] == (200, "ok")
        assert request(base + "/upload-named")[0::2] == (200, "ok")
        assert request(base + "/raw-binary")[0::2] == (200, "ok")
    finally:
        stop_server(target, target_thread)

    assert [record["method"] for record in records] == ["POST", "POST", "PUT"]

    default_upload = records[0]
    assert default_upload["path"] == "/upload-default"
    assert default_upload["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"' in default_upload["body_bytes"]
    assert b'filename="upload.bin"' in default_upload["body_bytes"]
    assert b"Content-Type: application/octet-stream" in default_upload["body_bytes"]
    assert b"\x00upload\xff" in default_upload["body_bytes"]

    named_upload = records[1]
    assert named_upload["headers"]["X-Meta"] == "yes"
    assert named_upload["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'filename="named.dat"' in named_upload["body_bytes"]
    assert b"Content-Type: image/png" in named_upload["body_bytes"]

    raw_upload = records[2]
    assert raw_upload["headers"]["Content-Type"] == "application/custom"
    assert raw_upload["body_bytes"] == b"\x01raw\xfe"


def test_active_registry_persistence_merge_delete_and_template_sets(tmp_path, logger):
    write_yaml(
        tmp_path / "base.yaml",
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
    redis_store = hmock.MemoryRedisStore()
    registry = hmock.ActiveMockRegistry(tmp_path, redis_store, logger)
    server = hmock.HMockHTTPServer(("127.0.0.1", 0), registry, logger, redis_store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert request(base + "/shared")[0::2] == (200, "fs")

        registry.upsert_base_definitions(
            [
                {
                    "key": "shared",
                    "expect": {"http": {"method": "GET", "path": "/shared"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
                },
                {
                    "key": "api-only",
                    "expect": {"http": {"method": "GET", "path": "/api-only"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "api-only"}}],
                },
            ]
        )

        assert request(base + "/shared")[0::2] == (200, "api")
        assert request(base + "/api-only")[0::2] == (200, "api-only")

        restarted = hmock.ActiveMockRegistry(tmp_path, redis_store, logger)
        assert [definition["key"] for definition in restarted.active_definitions()] == ["shared", "api-only"]

        registry.replace_template_set(
            "alpha",
            [
                {
                    "key": "alpha",
                    "expect": {"http": {"method": "GET", "path": "/alpha"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "alpha"}}],
                }
            ],
        )
        registry.replace_template_set(
            "beta",
            [
                {
                    "key": "beta",
                    "expect": {"http": {"method": "GET", "path": "/beta"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "beta"}}],
                }
            ],
        )
        assert request(base + "/alpha")[0::2] == (200, "alpha")
        assert request(base + "/beta")[0::2] == (200, "beta")

        registry.delete_template_set("alpha")
        assert request(base + "/alpha")[0] == 404
        assert request(base + "/beta")[0::2] == (200, "beta")

        registry.delete_base_definition("shared")
        assert request(base + "/shared")[0::2] == (200, "fs")
        registry.delete_all_base_definitions()
        assert request(base + "/api-only")[0] == 404
        assert request(base + "/beta")[0::2] == (200, "beta")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_active_registry_hot_reload_enabled_for_create_edit_and_delete(tmp_path, logger):
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
        body: one
""",
    )
    redis_store = hmock.MemoryRedisStore()
    registry = hmock.ActiveMockRegistry(tmp_path, redis_store, logger, templates_dir_hot_reload=True)
    server = hmock.HMockHTTPServer(("127.0.0.1", 0), registry, logger, redis_store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert request(base + "/hot")[0::2] == (200, "one")
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
        body: two!!
""",
        )
        assert request(base + "/hot")[0::2] == (200, "two!!")

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
        assert request(base + "/new")[0::2] == (200, "new")
        (tmp_path / "new.yaml").unlink()
        assert request(base + "/new")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_active_registry_hot_reload_disabled_keeps_filesystem_snapshot_but_allows_admin_mutations(tmp_path, logger):
    write_yaml(
        tmp_path / "frozen.yaml",
        """
- key: frozen
  expect:
    http:
      method: GET
      path: /frozen
  actions:
    - reply_http:
        status_code: 200
        body: one
""",
    )
    redis_store = hmock.MemoryRedisStore()
    registry = hmock.ActiveMockRegistry(tmp_path, redis_store, logger, templates_dir_hot_reload=False)
    server = hmock.HMockHTTPServer(("127.0.0.1", 0), registry, logger, redis_store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert request(base + "/frozen")[0::2] == (200, "one")
        write_yaml(
            tmp_path / "frozen.yaml",
            """
- key: frozen
  expect:
    http:
      method: GET
      path: /frozen
  actions:
    - reply_http:
        status_code: 200
        body: two
""",
        )
        assert request(base + "/frozen")[0::2] == (200, "one")

        registry.upsert_base_definitions(
            [
                {
                    "key": "admin-visible",
                    "expect": {"http": {"method": "GET", "path": "/admin-visible"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "admin"}}],
                }
            ]
        )
        assert request(base + "/admin-visible")[0::2] == (200, "admin")

        registry.reload()
        assert request(base + "/frozen")[0::2] == (200, "two")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_admin_api_endpoints_validation_and_reload_visibility(tmp_path, logger):
    redis_store = hmock.MemoryRedisStore()
    registry = hmock.ActiveMockRegistry(tmp_path, redis_store, logger)
    mock_server = hmock.HMockHTTPServer(("127.0.0.1", 0), registry, logger, redis_store)
    mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    mock_thread.start()
    admin_server, admin_thread, admin_base = start_admin_server(registry, logger)
    mock_base = f"http://127.0.0.1:{mock_server.server_address[1]}"
    try:
        assert request(admin_base + "/api/v1/health")[0::2] == (200, '{"status":"OK"}')

        submitted = [
            {
                "key": "admin",
                "expect": {"http": {"method": "GET", "path": "/admin"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "admin"}}],
            }
        ]
        assert json_request(admin_base + "/api/v1/templates", method="POST", payload=submitted)[0::2] == (
            200,
            json.dumps(submitted, separators=(",", ":")),
        )
        assert request(mock_base + "/admin")[0::2] == (200, "admin")

        status, _, body = request(admin_base + "/api/v1/templates")
        assert status == 200
        assert json.loads(body)[0]["key"] == "admin"

        status, _, body = json_request(admin_base + "/api/v1/templates", method="POST", payload=[{"key": ""}])
        assert status == 400
        assert "error" in json.loads(body)
        assert request(mock_base + "/admin")[0::2] == (200, "admin")

        assert request(admin_base + "/api/v1/templates/missing", method="DELETE")[0] == 404
        assert request(admin_base + "/api/v1/templates/admin", method="DELETE")[0] == 204
        assert request(mock_base + "/admin")[0] == 404

        set_payload = [
            {
                "key": "set-admin",
                "expect": {"http": {"method": "GET", "path": "/set-admin"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "set"}}],
            }
        ]
        assert json_request(admin_base + "/api/v1/template_sets/alpha", method="POST", payload=set_payload)[0] == 200
        assert request(mock_base + "/set-admin")[0::2] == (200, "set")
        assert request(admin_base + "/api/v1/template_sets/alpha", method="DELETE")[0] == 204
        assert request(mock_base + "/set-admin")[0] == 404
        assert request(admin_base + "/api/v1/templates", method="DELETE")[0] == 204
    finally:
        admin_server.shutdown()
        admin_server.server_close()
        admin_thread.join(timeout=2)
        mock_server.shutdown()
        mock_server.server_close()
        mock_thread.join(timeout=2)


def test_omctl_push_delete_defaults_ordering_and_failures(tmp_path):
    write_yaml(
        tmp_path / "a.yaml",
        """
- key: a
  expect:
    http:
      method: GET
      path: /a
  actions:
    - reply_http:
        status_code: 200
""",
    )
    write_yaml(
        tmp_path / "nested" / "b.yml",
        """
- key: b
  expect:
    http:
      method: GET
      path: /b
  actions:
    - reply_http:
        status_code: 200
""",
    )
    target, target_thread, records, target_base = start_capture_server(response_status=200, delete_status=204)
    try:
        assert omctl.push(str(tmp_path), target_base) == 200
        assert omctl.push(str(tmp_path), target_base, "alpha/beta") == 200
        assert omctl.delete(target_base, "alpha") == 204
    finally:
        stop_server(target, target_thread)

    assert records[0]["method"] == "POST"
    assert records[0]["path"] == "/api/v1/templates"
    assert records[0]["headers"]["Content-Type"] == "application/yaml"
    assert records[0]["body"].index("key: a") < records[0]["body"].index("key: b")

    assert records[1]["method"] == "POST"
    assert records[1]["path"] == "/api/v1/template_sets/alpha%2Fbeta"
    assert records[2]["method"] == "DELETE"
    assert records[2]["path"] == "/api/v1/template_sets/alpha"

    push_defaults = omctl.build_parser().parse_args(["push"])
    assert push_defaults.directory == "./demo_templates"
    assert push_defaults.url == "http://localhost:9998"
    assert push_defaults.set_key is None
    delete_defaults = omctl.build_parser().parse_args(["delete", "--set-key", "alpha"])
    assert delete_defaults.url == "http://localhost:9998"
    with pytest.raises(SystemExit):
        omctl.build_parser().parse_args(["delete"])

    failing, failing_thread, _, failing_base = start_capture_server(response_status=500)
    try:
        with pytest.raises(urllib.error.HTTPError):
            omctl.push(str(tmp_path), failing_base)
        assert omctl.main(["push", "-d", str(tmp_path), "-u", failing_base]) == 1
    finally:
        stop_server(failing, failing_thread)


def test_internal_redis_keyspace_blocked_for_redis_do_and_actions():
    store = hmock.MemoryRedisStore()
    with pytest.raises(hmock.RedisError):
        store.do("SET __hmock_internal:templates bad")
    assert store.do("GET __hmock_internal:templates", allow_internal=True) == ""

    with pytest.raises(hmock.RedisError):
        store.do("KEYS *")
    assert store.do("SET user:key ok") == "OK"

    ctx = hmock.build_template_context({}, "", "/", "", {}, store.do)
    with pytest.raises(hmock.TemplateError):
        hmock.render_template('{{ redisDo "GET __hmock_internal:templates" }}', ctx)

    protected = behavior(
        {
            "key": "protected",
            "expect": {"http": {"method": "GET", "path": "/protected"}},
            "actions": [
                {"redis": ["SET __hmock_internal:template_sets:alpha no"]},
                {"reply_http": {"status_code": 200, "body": "never"}},
            ],
        }
    )
    request_info = hmock.RequestInfo("GET", "/protected", "/protected", "", "", {}, "")
    with pytest.raises(hmock.TemplateError):
        hmock.execute_behavior(protected, request_info, {}, store)
    assert store.do("GET __hmock_internal:template_sets:alpha", allow_internal=True) == ""


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
