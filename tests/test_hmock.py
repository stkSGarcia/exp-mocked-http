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


def request(url, method="GET", body=None, headers=None):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()


def request_bytes(url, method="GET", body=None, headers=None):
    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def json_request(url, method="GET", value=None):
    body = None if value is None else json.dumps(value)
    return request(url, method=method, body=body, headers={"Content-Type": "application/json"})


def start_mock_and_admin(templates_dir, logger, redis_store=None, hot_reload=True, cors_enabled=False):
    redis_store = redis_store or hmock.MemoryRedisStore()
    collection = hmock.load_persisted_mock_collection(templates_dir, redis_store, logger)
    state = hmock.MockState(collection.behaviors, collection.raw_definitions, collection.filesystem_definitions)
    mock_server = hmock.HMockHTTPServer(
        ("127.0.0.1", 0),
        state,
        logger,
        redis_store,
        templates_dir,
        hot_reload,
        cors_enabled,
    )
    admin_server = hmock.AdminHTTPServer(("127.0.0.1", 0), state, templates_dir, logger, redis_store, hot_reload)
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


def stop_mock_and_admin(mock_server, mock_thread, admin_server, admin_thread):
    for server in (mock_server, admin_server):
        server.shutdown()
        server.server_close()
    for thread in (mock_thread, admin_thread):
        thread.join(timeout=2)


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


def test_admin_config_defaults_enabled():
    config = hmock.load_config({})

    assert config.admin_http_enabled is True
    assert config.admin_http_port == 9998
    assert config.admin_http_host == "0.0.0.0"
    assert config.templates_dir_hot_reload is True
    assert config.cors_enabled is False


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


def test_persisted_api_mocks_sets_merge_precedence_and_isolation(tmp_path, logger):
    write_yaml(
        tmp_path / "fs.yaml",
        """
- key: shared
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
    store = hmock.MemoryRedisStore()
    hmock.save_base_api_definitions(
        store,
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/base"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "base"}}],
            }
        ],
    )
    hmock.save_template_set(
        store,
        "b",
        [
            {
                "key": "set-b",
                "expect": {"http": {"method": "GET", "path": "/set-b"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "b"}}],
            }
        ],
    )
    hmock.save_template_set(
        store,
        "a",
        [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/set-a"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "a"}}],
            }
        ],
    )

    collection = hmock.load_persisted_mock_collection(tmp_path, store, logger)

    assert [raw["key"] for raw in collection.raw_definitions] == ["shared", "set-b"]
    assert [behavior.path for behavior in collection.behaviors] == ["/set-a", "/set-b"]

    hmock.delete_template_set(store, "a")
    assert sorted(hmock.load_template_sets(store)) == ["b"]
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


def test_reserved_internal_redis_keyspace_is_blocked_for_templates_and_actions():
    store = hmock.MemoryRedisStore()
    store.do("SET __hmock_internal:templates secret")
    ctx = hmock.build_template_context({}, "", "/", "", {}, hmock.guarded_redis_do(store))

    with pytest.raises(hmock.TemplateError):
        hmock.render_template('{{ redisDo "GET __hmock_internal:templates" }}', ctx)
    with pytest.raises(hmock.TemplateError):
        hmock.render_template('{{ redisDo "KEYS __hmock_internal:*" }}', ctx)
    with pytest.raises(hmock.TemplateError):
        hmock.render_template('{{ redisDo "DEL __hmock_internal:templates" }}', ctx)

    assert store.do("GET __hmock_internal:templates") == "secret"
    assert hmock.render_template('{{ redisDo "SET public ok" }} {{ redisDo "GET public" }}', ctx) == "OK ok"

    protected = behavior(
        {
            "key": "protected",
            "expect": {"http": {"method": "GET", "path": "/protected"}},
            "actions": [
                {"redis": ["DEL __hmock_internal:templates"]},
                {"reply_http": {"status_code": 200, "body": "not reached"}},
            ],
        }
    )
    request_info = hmock.RequestInfo("GET", "/protected", "/protected", "", "", {}, "")
    with pytest.raises(hmock.TemplateError):
        hmock.execute_behavior(protected, request_info, {}, store)
    assert store.do("GET __hmock_internal:templates") == "secret"


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


def test_binary_file_payload_loading_validation_and_response_execution(tmp_path, logger, server_factory):
    binary_file = tmp_path / "responses" / "body.bin"
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
        body_from_binary_file: responses/body.bin
        binary_file_name: fixture.bin
- key: inline-wins
  expect:
    http:
      method: GET
      path: /inline-wins
  actions:
    - reply_http:
        status_code: 200
        body: inline
        body_from_binary_file: responses/body.bin
""",
    )

    behaviors = hmock.load_behaviors(tmp_path, logger)
    binary_file.write_bytes(b"changed")

    payload = behaviors[0].actions[0]["reply_http"]
    assert payload["body_from_binary_file_content"] == b"\x00{{ .HTTPBody }}\xff"
    request_info = hmock.RequestInfo("POST", "/binary", "/binary", "", "", {}, "payload")
    response = hmock.execute_behavior(behaviors[0], request_info, {})
    assert response.body == b"\x00{{ .HTTPBody }}\xff"
    assert response.headers["Content-Length"] == str(len(b"\x00{{ .HTTPBody }}\xff"))
    assert response.headers["Content-Disposition"] == 'inline; filename="fixture.bin"'

    _, base = server_factory(behaviors)
    status, headers, body = request_bytes(base + "/binary", method="POST", body="payload")
    assert status == 200
    assert body == b"\x00{{ .HTTPBody }}\xff"
    assert headers["Content-Length"] == str(len(body))
    assert headers["Content-Disposition"] == 'inline; filename="fixture.bin"'
    assert request(base + "/inline-wins")[0::2] == (200, "inline")

    invalid = [
        {"reply_http": {"status_code": 200, "body_from_binary_file": "responses/missing.bin"}},
        {"reply_http": {"status_code": 200, "body_from_binary_file": "responses/body.bin", "binary_file_name": 3}},
        {"send_http": {"url": "http://example.test", "method": "POST", "body_from_binary_file": "responses/missing.bin"}},
        {"send_http": {"url": "http://example.test", "method": "POST", "body_from_binary_file": "responses/body.bin", "binary_file_name": 3}},
    ]
    for action in invalid:
        with pytest.raises(hmock.ValidationError):
            hmock.validate_behavior(
                {
                    "key": "bad",
                    "expect": {"http": {"method": "GET", "path": "/bad"}},
                    "actions": [action],
                },
                tmp_path,
            )

    outside = tmp_path.parent / f"{tmp_path.name}-outside.bin"
    outside.write_bytes(b"outside")
    with pytest.raises(hmock.ValidationError):
        hmock.validate_behavior(
            {
                "key": "outside",
                "expect": {"http": {"method": "GET", "path": "/outside"}},
                "actions": [
                    {"reply_http": {"status_code": 200, "body_from_binary_file": f"../{outside.name}"}},
                ],
            },
            tmp_path,
        )


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


def test_send_http_binary_post_multipart_raw_non_post_and_inline_precedence(tmp_path, logger, server_factory):
    binary_file = tmp_path / "payloads" / "upload.bin"
    binary_file.parent.mkdir()
    binary_file.write_bytes(b"\x00{{ .HTTPBody }}\xff")
    target, target_thread, records, target_base = start_capture_server()
    try:
        write_yaml(
            tmp_path / "binary-callbacks.yaml",
            f"""
- key: binary-post
  expect:
    http:
      method: POST
      path: /binary-post
  actions:
    - send_http:
        url: {target_base}/upload
        method: POST
        body_from_binary_file: payloads/upload.bin
        binary_file_name: sent.bin
        headers:
          Content-Type: image/png
    - reply_http:
        status_code: 200
        body: post-ok
- key: binary-put
  expect:
    http:
      method: GET
      path: /binary-put
  actions:
    - send_http:
        url: {target_base}/raw
        method: PUT
        body_from_binary_file: payloads/upload.bin
    - reply_http:
        status_code: 200
        body: put-ok
- key: inline-send-wins
  expect:
    http:
      method: GET
      path: /inline-send-wins
  actions:
    - send_http:
        url: {target_base}/inline
        method: POST
        body: inline body
        body_from_binary_file: payloads/upload.bin
    - reply_http:
        status_code: 200
        body: inline-ok
""",
        )
        _, base = server_factory(hmock.load_behaviors(tmp_path, logger))

        assert request(base + "/binary-post", method="POST", body="payload")[0::2] == (200, "post-ok")
        assert request(base + "/binary-put")[0::2] == (200, "put-ok")
        assert request(base + "/inline-send-wins")[0::2] == (200, "inline-ok")
    finally:
        stop_server(target, target_thread)

    assert records[0]["method"] == "POST"
    assert records[0]["path"] == "/upload"
    assert records[0]["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="sent.bin"' in records[0]["body_bytes"]
    assert b"Content-Type: image/png" in records[0]["body_bytes"]
    assert b"\x00{{ .HTTPBody }}\xff" in records[0]["body_bytes"]

    assert records[1]["method"] == "PUT"
    assert records[1]["path"] == "/raw"
    assert records[1]["body_bytes"] == b"\x00{{ .HTTPBody }}\xff"

    assert records[2]["method"] == "POST"
    assert records[2]["path"] == "/inline"
    assert records[2]["body"] == "inline body"


def test_cors_headers_preflight_and_mock_header_precedence(server_factory):
    behaviors = [
        behavior(
            {
                "key": "cors",
                "expect": {"http": {"method": "GET", "path": "/cors"}},
                "actions": [
                    {
                        "reply_http": {
                            "status_code": 200,
                            "headers": {"access-control-allow-origin": "https://example.test"},
                            "body": "ok",
                        }
                    }
                ],
            }
        ),
        behavior(
                {
                    "key": "options",
                    "expect": {"http": {"method": "OPTIONS", "path": "/cors"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "explicit"}}],
                }
            ),
    ]

    _, base = server_factory(behaviors, cors_enabled=True)

    status, headers, body = request(base + "/cors")
    assert (status, body) == (200, "ok")
    assert headers["access-control-allow-origin"] == "https://example.test"
    assert headers["Access-Control-Allow-Methods"] == "*"
    assert headers["Access-Control-Allow-Headers"] == "*"
    assert headers["Access-Control-Allow-Credentials"] == "true"

    status, headers, body = request(base + "/cors", method="OPTIONS")
    assert (status, body) == (200, "explicit")
    assert headers["Access-Control-Allow-Origin"] == "*"

    status, headers, body = request(base + "/missing", method="OPTIONS")
    assert (status, body) == (200, "")
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Content-Length"] == "0"

    _, off_base = server_factory(behaviors, cors_enabled=False)
    status, headers, body = request(off_base + "/missing", method="OPTIONS")
    assert (status, body) == (404, "not found")
    assert "Access-Control-Allow-Origin" not in headers


def test_admin_api_templates_sets_persistence_and_reload(tmp_path, logger):
    write_yaml(
        tmp_path / "shared.yaml",
        """
- key: shared
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
    (
        mock_server,
        mock_thread,
        mock_base,
        admin_server,
        admin_thread,
        admin_base,
    ) = start_mock_and_admin(tmp_path, logger)
    try:
        status, _, body = request(admin_base + "/api/v1/health")
        assert (status, body) == (200, '{"status":"OK"}')

        status, _, body = request(admin_base + "/api/v1/templates")
        assert status == 200
        assert [raw["key"] for raw in json.loads(body)] == ["shared"]

        api_shared = [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/api"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
            }
        ]
        assert json_request(admin_base + "/api/v1/templates", method="POST", value=api_shared)[0] == 200
        assert request(mock_base + "/api")[0::2] == (200, "api")
        assert request(mock_base + "/fs")[0::2] == (404, "not found")

        invalid = [{"key": "bad", "actions": [{"reply_http": {"status_code": 200}}]}]
        status, _, body = json_request(admin_base + "/api/v1/templates", method="POST", value=invalid)
        assert status == 400
        assert "expect.http.method" in body
        assert request(mock_base + "/api")[0::2] == (200, "api")

        updated = [
            {
                "key": "shared",
                "expect": {"http": {"method": "GET", "path": "/api"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "api-v2"}}],
            }
        ]
        assert json_request(admin_base + "/api/v1/templates", method="POST", value=updated)[0::2] == (
            200,
            json.dumps(updated, separators=(",", ":")),
        )
        assert request(mock_base + "/api")[0::2] == (200, "api-v2")

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
        assert json_request(admin_base + "/api/v1/template_sets/a", method="POST", value=set_a)[0] == 200
        assert json_request(admin_base + "/api/v1/template_sets/b", method="POST", value=set_b)[0] == 200
        assert request(mock_base + "/set-a")[0::2] == (200, "a")
        assert request(mock_base + "/set-b")[0::2] == (200, "b")

        assert request(admin_base + "/api/v1/template_sets/a", method="DELETE")[0] == 204
        assert request(mock_base + "/set-a")[0::2] == (404, "not found")
        assert request(mock_base + "/set-b")[0::2] == (200, "b")
        assert request(admin_base + "/api/v1/template_sets/missing", method="DELETE")[0] == 204

        assert request(admin_base + "/api/v1/templates", method="DELETE")[0] == 204
        assert request(mock_base + "/api")[0::2] == (404, "not found")
        assert request(mock_base + "/fs")[0::2] == (200, "fs")
        assert request(mock_base + "/set-b")[0::2] == (200, "b")

        assert json_request(admin_base + "/api/v1/templates", method="POST", value=api_shared)[0] == 200
        assert request(admin_base + "/api/v1/templates/shared", method="DELETE")[0] == 204
        assert request(mock_base + "/fs")[0::2] == (200, "fs")
        assert request(admin_base + "/api/v1/templates/shared", method="DELETE")[0] == 404
    finally:
        stop_mock_and_admin(mock_server, mock_thread, admin_server, admin_thread)


def test_admin_api_accepts_yaml_upserts_and_rejects_invalid_yaml(tmp_path, logger):
    (
        mock_server,
        mock_thread,
        mock_base,
        admin_server,
        admin_thread,
        admin_base,
    ) = start_mock_and_admin(tmp_path, logger)
    try:
        yaml_body = """
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
        assert request(admin_base + "/api/v1/templates", method="POST", body=yaml_body, headers={"Content-Type": "application/yaml"})[0] == 200
        assert request(mock_base + "/yaml-base")[0::2] == (200, "yaml-base")

        set_body = """
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
        assert request(admin_base + "/api/v1/template_sets/yaml", method="POST", body=set_body, headers={"Content-Type": "text/yaml"})[0] == 200
        assert request(mock_base + "/yaml-set")[0::2] == (200, "yaml-set")

        status, _, body = request(
            admin_base + "/api/v1/templates",
            method="POST",
            body="not: an-array",
            headers={"Content-Type": "application/yaml"},
        )
        assert status == 400
        assert "request body must be a JSON array" in body
        assert request(mock_base + "/yaml-base")[0::2] == (200, "yaml-base")

        status, _, body = request(
            admin_base + "/api/v1/template_sets/yaml",
            method="POST",
            body="- key: broken\n  expect:\n    http:\n      path: /broken\n",
            headers={"Content-Type": "application/x-yaml"},
        )
        assert status == 400
        assert "expect.http.method" in body
        assert request(mock_base + "/yaml-set")[0::2] == (200, "yaml-set")

        assert json_request(
            admin_base + "/api/v1/templates",
            method="POST",
            value=[
                {
                    "key": "json-still-works",
                    "expect": {"http": {"method": "GET", "path": "/json"}},
                    "actions": [{"reply_http": {"status_code": 200, "body": "json"}}],
                }
            ],
        )[0] == 200
        assert request(mock_base + "/json")[0::2] == (200, "json")
    finally:
        stop_mock_and_admin(mock_server, mock_thread, admin_server, admin_thread)


def test_templates_directory_hot_reload_creation_edit_delete_and_failed_reload(tmp_path, logger):
    (
        mock_server,
        mock_thread,
        mock_base,
        admin_server,
        admin_thread,
        _,
    ) = start_mock_and_admin(tmp_path, logger, hot_reload=True)
    try:
        assert request(mock_base + "/hot")[0::2] == (404, "not found")

        hot_file = write_yaml(
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
        body: v1
""",
        )
        assert request(mock_base + "/hot")[0::2] == (200, "v1")

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
        body: version-two
""",
        )
        assert request(mock_base + "/hot")[0::2] == (200, "version-two")

        write_yaml(
            tmp_path / "bad.yaml",
            """
- key: bad
  expect:
    http:
      path: /bad
  actions:
    - reply_http:
        status_code: 200
""",
        )
        assert request(mock_base + "/hot")[0::2] == (200, "version-two")
        assert "templates hot reload failed" in log_stream_value(logger)

        (tmp_path / "bad.yaml").unlink()
        assert request(mock_base + "/hot")[0::2] == (200, "version-two")

        hot_file.unlink()
        assert request(mock_base + "/hot")[0::2] == (404, "not found")
    finally:
        stop_mock_and_admin(mock_server, mock_thread, admin_server, admin_thread)


def log_stream_value(logger):
    return logger.stream.getvalue()


def test_hot_reload_disabled_preserves_filesystem_snapshot_but_admin_mutates(tmp_path, logger):
    fs_file = write_yaml(
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
        body: fs
""",
    )
    (
        mock_server,
        mock_thread,
        mock_base,
        admin_server,
        admin_thread,
        admin_base,
    ) = start_mock_and_admin(tmp_path, logger, hot_reload=False)
    try:
        assert request(mock_base + "/fs")[0::2] == (200, "fs")
        write_yaml(
            fs_file,
            """
- key: changed
  expect:
    http:
      method: GET
      path: /changed
  actions:
    - reply_http:
        status_code: 200
        body: changed
""",
        )
        assert request(mock_base + "/changed")[0::2] == (404, "not found")
        assert request(mock_base + "/fs")[0::2] == (200, "fs")

        api_definitions = [
            {
                "key": "api",
                "expect": {"http": {"method": "GET", "path": "/api"}},
                "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
            }
        ]
        assert json_request(admin_base + "/api/v1/templates", method="POST", value=api_definitions)[0] == 200
        assert request(mock_base + "/api")[0::2] == (200, "api")
        assert request(mock_base + "/changed")[0::2] == (404, "not found")
        assert request(mock_base + "/fs")[0::2] == (200, "fs")
    finally:
        stop_mock_and_admin(mock_server, mock_thread, admin_server, admin_thread)


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


def test_omctl_help_unknown_command_and_required_delete_key(capsys):
    with pytest.raises(SystemExit) as help_exit:
        omctl.main(["--help"])
    assert help_exit.value.code == 0
    assert "push" in capsys.readouterr().out

    with pytest.raises(SystemExit) as unknown_exit:
        omctl.main(["unknown"])
    assert unknown_exit.value.code != 0

    with pytest.raises(SystemExit) as delete_exit:
        omctl.main(["delete"])
    assert delete_exit.value.code != 0


def test_omctl_push_and_delete_request_construction(tmp_path, monkeypatch, capsys):
    demo = tmp_path / "demo_templates"
    write_yaml(
        demo / "a.yaml",
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
        demo / "nested" / "b.yml",
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
    (demo / "ignored.txt").write_text("- key: ignored")
    calls = []

    def fake_request(url, method, body=None, headers=None):
        calls.append((url, method, body, headers or {}))
        return (204, "") if method == "DELETE" else (200, "{}")

    monkeypatch.setattr(omctl, "_request", fake_request)
    monkeypatch.chdir(tmp_path)

    assert omctl.main(["push"]) == 0
    assert calls[-1][0] == "http://localhost:9998/api/v1/templates"
    assert calls[-1][1] == "POST"
    assert calls[-1][3]["Content-Type"] == "application/yaml"
    assert b"key: a" in calls[-1][2]
    assert b"key: b" in calls[-1][2]
    assert b"ignored" not in calls[-1][2]

    assert omctl.main(["push", "-d", str(demo), "-u", "http://127.0.0.1:18080/", "-k", "smoke"]) == 0
    assert calls[-1][0] == "http://127.0.0.1:18080/api/v1/template_sets/smoke"

    assert omctl.main(["delete", "-u", "http://127.0.0.1:18080", "-k", "smoke"]) == 0
    assert calls[-1] == ("http://127.0.0.1:18080/api/v1/template_sets/smoke", "DELETE", None, {})

    def failing_request(url, method, body=None, headers=None):
        return 500, "boom"

    monkeypatch.setattr(omctl, "_request", failing_request)
    assert omctl.main(["push", "-d", str(demo)]) == 1
    assert "boom" in capsys.readouterr().err
