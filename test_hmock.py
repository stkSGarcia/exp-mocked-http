import io
import json
import hashlib
import hmac
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import hmock


@pytest.fixture(autouse=True)
def reset_redis_backend():
    old_backend = hmock._REDIS_BACKEND
    old_templates = hmock._NAMED_TEMPLATES
    hmock._REDIS_BACKEND = hmock.MemoryRedisBackend()
    hmock._NAMED_TEMPLATES = {}
    try:
        yield
    finally:
        hmock._REDIS_BACKEND = old_backend
        hmock._NAMED_TEMPLATES = old_templates


def test_config_defaults_and_overrides():
    assert hmock.load_config({}) == hmock.Config()
    config = hmock.load_config({
        "HM_TEMPLATES_DIR": "/tmp/mocks",
        "HM_HTTP_PORT": "1234",
        "HM_HTTP_HOST": "127.0.0.1",
        "HM_LOG_LEVEL": "debug",
        "HM_REDIS_TYPE": "redis",
        "HM_REDIS_URL": "redis://example.test:6380/2",
    })
    assert config.templates_dir == "/tmp/mocks"
    assert config.http_port == 1234
    assert config.http_host == "127.0.0.1"
    assert config.log_level == "debug"
    assert config.redis_type == "redis"
    assert config.redis_url == "redis://example.test:6380/2"

    with pytest.raises(ValueError, match="HM_REDIS_TYPE"):
        hmock.load_config({"HM_REDIS_TYPE": "bad"})


def test_redis_backend_factory_uses_configured_type():
    memory = hmock.create_redis_backend(hmock.Config(redis_type="memory"))
    external = hmock.create_redis_backend(hmock.Config(
        redis_type="redis",
        redis_url="redis://example.test:6380",
    ))

    assert isinstance(memory, hmock.MemoryRedisBackend)
    assert isinstance(external, hmock.ExternalRedisBackend)
    assert external.url == "redis://example.test:6380"


def test_yaml_loading_validation_and_duplicate_override(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "a.yaml").write_text("""
- key: first
  expect:
    http:
      method: GET
      path: /first
  actions: []
- key: duplicate
  expect:
    http:
      method: GET
      path: /old
  actions: []
""")
    (nested / "b.yml").write_text("""
- key: duplicate
  expect:
    http:
      method: GET
      path: /new
  actions: []
""")
    (tmp_path / "ignored.txt").write_text("not yaml")
    stream = io.StringIO()
    old_logger = hmock.LOGGER
    hmock.LOGGER = hmock.setup_logger("warn", stream)
    try:
        behaviors = hmock.load_behaviors(str(tmp_path))
    finally:
        hmock.LOGGER = old_logger
    assert [behavior["key"] for behavior in behaviors] == ["first", "duplicate"]
    assert behaviors[1]["expect"]["http"]["path"] == "/new"
    assert "duplicate behavior key override" in stream.getvalue()


def test_validation_rejects_bad_keys_and_multiple_replies():
    with pytest.raises(ValueError, match="key"):
        hmock._validate_behavior({"actions": []})
    with pytest.raises(ValueError, match="key"):
        hmock._validate_behavior({"key": ""})
    with pytest.raises(ValueError, match="kind"):
        hmock.assemble_behaviors([{"key": "x", "kind": "Unknown"}])
    with pytest.raises(ValueError, match="Template does not allow"):
        hmock.assemble_behaviors([{"key": "t", "kind": "Template", "template": "x", "values": {}}])
    with pytest.raises(ValueError, match="Behavior does not allow"):
        hmock.assemble_behaviors([{"key": "b", "kind": "Behavior", "template": "x"}])
    with pytest.raises(ValueError, match="more than one"):
        hmock._validate_behavior({
            "key": "x",
            "actions": [
                {"reply_http": {"status_code": 200}},
                {"reply_http": {"status_code": 201}},
            ],
        })
    with pytest.raises(ValueError, match="redis action"):
        hmock._validate_behavior({"key": "x", "actions": [{"redis": "SET a b"}]})
    with pytest.raises(ValueError, match="send_http.url"):
        hmock._validate_behavior({"key": "x", "actions": [{"send_http": {"method": "POST"}}]})
    with pytest.raises(ValueError, match="send_http.headers"):
        hmock._validate_behavior({
            "key": "x",
            "actions": [{"send_http": {"url": "http://example.test", "method": "POST", "headers": []}}],
        })


def test_template_and_abstract_definitions_do_not_match_directly():
    behaviors = hmock.assemble_behaviors([
        {"key": "payload", "kind": "Template", "template": "not active"},
        {
            "key": "abstract",
            "kind": "AbstractBehavior",
            "expect": {"http": {"method": "GET", "path": "/abstract"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "abstract"}}],
        },
        {
            "key": "concrete",
            "kind": "Behavior",
            "expect": {"http": {"method": "GET", "path": "/concrete"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "concrete"}}],
        },
    ])

    assert [behavior["key"] for behavior in behaviors] == ["concrete"]
    ctx = hmock.build_context("GET", "/abstract", "", {}, "")
    behavior, _ = hmock.find_behavior(behaviors, "GET", "/abstract", ctx)
    assert behavior is None
    behavior, _ = hmock.find_behavior(behaviors, "GET", "/concrete", ctx)
    assert behavior["key"] == "concrete"


def test_template_and_inheritance_checkpoint_example():
    behaviors = hmock.assemble_behaviors([
        {
            "key": "http-request-template",
            "kind": "Template",
            "template": '{ "http_path": "{{.HTTPPath}}", "http_header": "{{.HTTPHeader.Get "X-Name"}}" }',
        },
        {
            "key": "color-template",
            "kind": "Template",
            "template": '{ "color": "{{.color}}" }',
        },
        {
            "key": "purple-teapot",
            "kind": "Behavior",
            "extend": "teapot",
            "values": {"color": "purple"},
        },
        {
            "key": "teapot",
            "kind": "AbstractBehavior",
            "expect": {"http": {"method": "GET", "path": "/teapot"}},
            "values": {"fruit": "potato", "color": "brown"},
            "actions": [{
                "reply_http": {
                    "status_code": 418,
                    "body": (
                        '{ "request-info": {{ template "http-request-template" . }}, '
                        '"teapot-info": {{ template "color-template" .Values }}, '
                        '"fruit": "{{.Values.fruit}}" }'
                    ),
                },
            }],
        },
    ])
    ctx = hmock.build_context("GET", "/teapot", "", {"X-Name": "Ada"}, "")
    behavior, params = hmock.find_behavior(behaviors, "GET", "/teapot", ctx)
    assert behavior["key"] == "purple-teapot"
    assert behavior["values"] == {"fruit": "potato", "color": "purple"}

    ctx["HTTPParams"] = params
    ctx["HTTPPathParams"] = params
    ctx["Values"] = behavior["values"]
    response = hmock.execute_actions(behavior["actions"], ctx)

    assert response.status_code == 418
    assert json.loads(response.body) == {
        "request-info": {"http_path": "/teapot", "http_header": "Ada"},
        "teapot-info": {"color": "purple"},
        "fruit": "potato",
    }


def test_values_are_available_in_conditions_and_named_templates():
    behaviors = hmock.assemble_behaviors([
        {"key": "body-template", "kind": "Template", "template": "{{.color}}:{{.size}}"},
        {
            "key": "check",
            "kind": "AbstractBehavior",
            "values": {"expected_token": "default", "color": "blue", "size": "large"},
            "expect": {
                "condition": '{{.HTTPHeader.Get "X-Token" | eq .Values.expected_token}}',
                "http": {"method": "GET", "path": "/secured"},
            },
            "actions": [{
                "reply_http": {
                    "status_code": 200,
                    "body": '{{ template "body-template" .Values }}',
                },
            }],
        },
        {
            "key": "prod-check",
            "kind": "Behavior",
            "extend": "check",
            "values": {"expected_token": "prod-secret", "color": "green"},
        },
    ])
    ctx = hmock.build_context("GET", "/secured", "", {"X-Token": "prod-secret"}, "")
    behavior, params = hmock.find_behavior(behaviors, "GET", "/secured", ctx)
    assert behavior["key"] == "prod-check"
    ctx["HTTPParams"] = params
    ctx["HTTPPathParams"] = params
    ctx["Values"] = behavior["values"]

    assert hmock.execute_actions(behavior["actions"], ctx).body == b"green:large"
    with pytest.raises(hmock.TemplateRenderError, match="unknown template"):
        hmock.render('{{ template "missing" . }}', ctx)


def test_inheritance_action_order_and_stable_equal_order():
    behaviors = hmock.assemble_behaviors([
        {
            "key": "ordered",
            "kind": "Behavior",
            "extend": "base",
            "actions": [
                {"order": -5, "redis": ["RPUSH trace child-early"]},
                {"redis": ["RPUSH trace child-default"]},
                {"order": 5, "reply_http": {"status_code": 200, "body": '{{ redisDo "LRANGE trace 0 -1" }}'}},
            ],
        },
        {
            "key": "base",
            "kind": "AbstractBehavior",
            "expect": {"http": {"method": "GET", "path": "/ordered"}},
            "actions": [
                {"redis": ["RPUSH trace parent-a"]},
                {"order": 0, "redis": ["RPUSH trace parent-b"]},
            ],
        },
    ])
    ctx = hmock.build_context("GET", "/ordered", "", {}, "")
    behavior, params = hmock.find_behavior(behaviors, "GET", "/ordered", ctx)
    ctx["HTTPParams"] = params
    ctx["HTTPPathParams"] = params
    response = hmock.execute_actions(behavior["actions"], ctx)

    assert response.body == b"child-early;;parent-a;;parent-b;;child-default"


def test_missing_parent_skip_and_inheritance_cycle_validation():
    behaviors = hmock.assemble_behaviors([
        {
            "key": "valid-child",
            "kind": "Behavior",
            "extend": "missing-parent",
            "expect": {"http": {"method": "GET", "path": "/valid"}},
            "actions": [{"reply_http": {"status_code": 200, "body": "ok"}}],
        },
    ])
    assert behaviors[0]["key"] == "valid-child"

    with pytest.raises(ValueError, match="actions"):
        hmock.assemble_behaviors([
            {"key": "invalid-child", "kind": "Behavior", "extend": "missing-parent", "actions": "bad"},
        ])

    with pytest.raises(ValueError, match="cyclic behavior inheritance"):
        hmock.assemble_behaviors([
            {"key": "a", "kind": "Behavior", "extend": "b"},
            {"key": "b", "kind": "Behavior", "extend": "a"},
        ])


def test_matching_conditions_and_params():
    behaviors = hmock.assemble_behaviors([
        {
            "key": "bad-token",
            "expect": {
                "condition": '{{.HTTPHeader.Get "X-Token" | eq "nope"}}',
                "http": {"method": "GET", "path": "/users/:id"},
            },
            "actions": [],
        },
        {
            "key": "good-token",
            "expect": {
                "condition": '{{.HTTPHeader.Get "X-Token" | eq "ok"}}',
                "http": {"method": "GET", "path": "/users/:id"},
            },
            "actions": [],
        },
    ])
    ctx = hmock.build_context("GET", "/users/42?debug=1", "debug=1", {"X-Token": "ok"}, "")
    behavior, params = hmock.find_behavior(behaviors, "GET", "/users/42", ctx)
    assert behavior["key"] == "good-token"
    assert params == {"id": "42"}


def test_template_context_syntax_and_functions(monkeypatch):
    monkeypatch.setenv("HM_TEST_VALUE", "env-ok")
    ctx = hmock.build_context("POST", "/p?q=1", "q=1", {"X-Name": "Ada"}, "hello")
    assert hmock.render('{{.HTTPHeader.Get "X-Name"}}', ctx) == "Ada"
    assert hmock.render("{{.HTTPBody | upper}}", ctx) == "HELLO"
    assert hmock.render("{{ if eq .HTTPBody \"hello\" }}yes{{ else }}no{{ end }}", ctx) == "yes"
    assert hmock.render("{{ $x := .HTTPQueryString }}{{ $x }}", ctx) == "q=1"
    assert hmock.render("{{ `raw text` }}", ctx) == "raw text"
    assert hmock.render("{{ b64dec (b64enc .HTTPBody) }}", ctx) == "hello"
    assert hmock.render("{{ env \"HM_TEST_VALUE\" }}", ctx) == "env-ok"
    assert hmock.render("{{ add 2 3 }}", ctx) == "5"
    with pytest.raises(hmock.TemplateRenderError):
        hmock.render("{{.MissingValue}}", ctx)


def test_richer_template_helpers():
    body = json.dumps({
        "foo": "alpha",
        "context": {"type": "event"},
        "items": [{"id": 10}, {"id": 11}],
        "nested": {"bar": "omega"},
    })
    ctx = hmock.build_context("POST", "/p", "", {}, body)
    ctx["Values"] = {"items": ["a", "b"]}
    ctx["ItemList"] = ["a", "b"]

    assert hmock.render('{{ jsonPath "foo" .HTTPBody }}', ctx) == "alpha"
    assert hmock.render('{{ jsonPath "//bar" .HTTPBody }}', ctx) == "omega"
    assert hmock.render('{{ jsonPath "missing" "" }}', ctx) == ""
    assert hmock.render('{{ gJsonPath "context.type" .HTTPBody }}', ctx) == "event"
    assert hmock.render('{{ gJsonPath "items.0.id" .HTTPBody }}', ctx) == "10"
    assert hmock.render('{{ gJsonPath "items.#" .HTTPBody }}', ctx) == "2"
    assert hmock.render('{{ gJsonPath "items.#.id" .HTTPBody }}', ctx) == "[10,11]"
    assert hmock.render('{{ gJsonPath "missing" .HTTPBody }}', ctx) == ""
    with pytest.raises(hmock.TemplateRenderError):
        hmock.render('{{ gJsonPath "x" "not-json" }}', ctx)

    xml = "<root><item>Ada</item><nested><value>42</value></nested></root>"
    assert hmock.render('{{ xmlPath "item" .Values.xml }}', {"Values": {"xml": xml}}) == "Ada"
    assert hmock.render('{{ xmlPath "//value" .Values.xml }}', {"Values": {"xml": xml}}) == "42"
    assert hmock.render('{{ xmlPath "missing" "" }}', ctx) == ""

    assert hmock.render('{{ uuidv5 "same-input" }}', ctx) == str(uuid.uuid5(uuid.NAMESPACE_OID, "same-input"))
    assert hmock.render('{{ regexFindFirstSubmatch "user-([0-9]+)" "user-42" }}', ctx) == "42"
    assert hmock.render('{{ regexFindAllSubmatch("user-([0-9]+)", "user-42") }}', ctx) == "['user-42', '42']"
    assert hmock.render('{{ regexFindFirstSubmatch "user-[0-9]+" "user-42" }}', ctx) == ""
    assert hmock.render('{{ hmacSHA256 "secret" "payload" }}', ctx) == hmac.new(
        b"secret",
        b"payload",
        hashlib.sha256,
    ).hexdigest()
    assert hmock.render("{{ isLastIndex 1 .ItemList }}", ctx) == "true"
    assert hmock.render("{{ htmlEscapeString .Values.html }}", {"Values": {"html": "<a>&\"'"}}) == "&lt;a&gt;&amp;&quot;&#x27;"


def test_memory_redis_backend_commands_and_result_formatting():
    backend = hmock.MemoryRedisBackend()

    assert hmock.format_redis_result(backend.execute(["SET", "greeting", "hello world"])) == "OK"
    assert hmock.format_redis_result(backend.execute(["GET", "greeting"])) == "hello world"
    assert hmock.format_redis_result(backend.execute(["RPUSH", "queue", "a"])) == "1"
    assert hmock.format_redis_result(backend.execute(["RPUSH", "queue", "b"])) == "2"
    assert hmock.format_redis_result(backend.execute(["LPUSH", "queue", "z"])) == "3"
    assert hmock.format_redis_result(backend.execute(["LRANGE", "queue", "0", "-1"])) == "z;;a;;b"
    assert hmock.format_redis_result(backend.execute(["LPOP", "queue"])) == "z"
    assert hmock.format_redis_result(backend.execute(["RPOP", "queue"])) == "b"
    assert hmock.format_redis_result(backend.execute(["HSET", "user", "name", "Ada"])) == "1"
    assert hmock.format_redis_result(backend.execute(["HGET", "user", "name"])) == "Ada"
    assert hmock.format_redis_result(backend.execute(["HGETALL", "user"])) == "name;;Ada"
    assert hmock.format_redis_result(backend.execute(["HDEL", "user", "name"])) == "1"
    assert hmock.format_redis_result(backend.execute(["EXISTS", "greeting"])) == "1"
    assert hmock.format_redis_result(backend.execute(["KEYS", "g*"])) == "greeting"
    assert hmock.format_redis_result(backend.execute(["DEL", "greeting"])) == "1"
    assert hmock.format_redis_result(backend.execute(["GET", "greeting"])) == ""


def test_redis_do_template_contexts_and_redis_action_order():
    behaviors = hmock.assemble_behaviors([
        {
            "key": "stateful",
            "expect": {
                "condition": '{{ redisDo "SET gate open" | eq "OK" }}',
                "http": {"method": "GET", "path": "/state/:id"},
            },
            "actions": [
                {"redis": [
                    'SET token "{{.HTTPPathParams.id}}"',
                    'SET copy "{{ redisDo "GET token" }}"',
                    'RPUSH queue "{{ redisDo "GET copy" }}"',
                ]},
                {"reply_http": {
                    "status_code": 200,
                    "headers": {
                        "X-Token": '{{ redisDo "GET token" }}',
                        "X-Queue": '{{ redisDo "LRANGE queue 0 -1" }}',
                    },
                    "body": '{{ redisDo "GET copy" }}:{{ redisDo "LRANGE queue 0 -1" | splitList ";;" | index 0 }}',
                }},
            ],
        },
    ])
    ctx = hmock.build_context("GET", "/state/42", "", {}, "")
    behavior, params = hmock.find_behavior(behaviors, "GET", "/state/42", ctx)

    assert behavior["key"] == "stateful"
    ctx["HTTPParams"] = params
    ctx["HTTPPathParams"] = params
    response = hmock.execute_actions(behavior["actions"], ctx)

    assert hmock.redis_do("GET gate") == "open"
    assert response.status_code == 200
    assert response.headers["X-Token"] == "42"
    assert response.headers["X-Queue"] == "42"
    assert response.body == b"42:42"


def test_reply_http_and_sleep_actions():
    ctx = hmock.build_context("GET", "/hello", "", {"X-Name": "Ada"}, "")
    start = time.monotonic()
    response = hmock.execute_actions([
        {"sleep": {"duration": "1ms"}},
        {"reply_http": {
            "status_code": 201,
            "headers": {
                "X-Echo": '{{.HTTPHeader.Get "X-Name"}}',
                "X-Signature": '{{ hmacSHA256 "secret" .HTTPBody }}',
            },
            "body": "hi {{.HTTPHeader.Get \"X-Name\"}}",
        }},
    ], ctx)
    assert time.monotonic() >= start
    assert response.status_code == 201
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Content-Length"] == "6"
    assert response.headers["X-Echo"] == "Ada"
    assert response.headers["X-Signature"] == hmac.new(b"secret", b"", hashlib.sha256).hexdigest()
    assert response.body == b"hi Ada"


def test_file_backed_body_loading_precedence_and_snapshot(tmp_path):
    response_dir = tmp_path / "responses"
    response_dir.mkdir()
    body_file = response_dir / "hello.txt"
    body_file.write_text('hello {{.HTTPHeader.Get "X-Name"}}', encoding="utf-8")
    (tmp_path / "mocks.yaml").write_text("""
- key: file-body
  expect:
    http:
      method: GET
      path: /file
  actions:
    - reply_http:
        status_code: 200
        body: ""
        body_from_file: responses/hello.txt
- key: inline-body
  expect:
    http:
      method: GET
      path: /inline
  actions:
    - reply_http:
        status_code: 200
        body: inline {{.HTTPHeader.Get "X-Name"}}
        body_from_file: responses/hello.txt
""", encoding="utf-8")

    behaviors = hmock.load_behaviors(str(tmp_path))
    body_file.write_text("changed", encoding="utf-8")
    ctx = hmock.build_context("GET", "/file", "", {"X-Name": "Ada"}, "")
    file_response = hmock.execute_actions(behaviors[0]["actions"], ctx)
    inline_response = hmock.execute_actions(behaviors[1]["actions"], ctx)

    assert file_response.body == b"hello Ada"
    assert file_response.headers["Content-Type"] == "application/json"
    assert file_response.headers["Content-Length"] == "9"
    assert inline_response.body == b"inline Ada"
    assert inline_response.headers["Content-Length"] == "10"


def test_file_backed_body_rejects_outside_or_missing_paths(tmp_path):
    (tmp_path / "outside.yaml").write_text("""
- key: outside
  actions:
    - reply_http:
        status_code: 200
        body_from_file: ../outside.txt
""", encoding="utf-8")
    with pytest.raises(ValueError, match="inside HM_TEMPLATES_DIR"):
        hmock.load_behaviors(str(tmp_path))

    (tmp_path / "outside.yaml").unlink()
    (tmp_path / "missing.yaml").write_text("""
- key: missing
  actions:
    - reply_http:
        status_code: 200
        body_from_file: missing.txt
""", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read body_from_file"):
        hmock.load_behaviors(str(tmp_path))


class RecordingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _record(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        self.server.records.append({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body": body,
        })
        self.send_response(202)
        self.end_headers()
        self.wfile.write(b"accepted")

    def do_GET(self):
        self._record()

    def do_POST(self):
        self._record()

    def do_PUT(self):
        self._record()


@pytest.fixture()
def recording_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    httpd.records = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_send_http_renders_fields_file_bodies_precedence_and_failures(tmp_path, recording_server):
    (tmp_path / "payload.txt").write_text('file {{.HTTPBody}} {{ redisDo "GET token" }}', encoding="utf-8")
    port = recording_server.server_address[1]
    behaviors = hmock.assemble_behaviors([
        {
            "key": "send",
            "expect": {"http": {"method": "POST", "path": "/send/:id"}},
            "actions": [
                {"redis": ['SET token "{{.HTTPPathParams.id}}"']},
                {"send_http": {
                    "url": f"http://127.0.0.1:{port}/events/{{{{.HTTPPathParams.id}}}}?{{{{.HTTPQueryString}}}}",
                    "method": "post",
                    "headers": {"X-Name": '{{.HTTPHeader.Get "X-Name"}}'},
                    "body_from_file": "payload.txt",
                }},
                {"send_http": {
                    "url": f"http://127.0.0.1:{port}/inline",
                    "method": "PUT",
                    "body": 'inline {{ redisDo "GET token" }}',
                    "body_from_file": "payload.txt",
                }},
                {"send_http": {
                    "url": "http://127.0.0.1:1/fail",
                    "method": "POST",
                    "body": "ignored",
                }},
                {"reply_http": {
                    "status_code": 200,
                    "body": 'done {{ redisDo "GET token" }}',
                }},
                {"send_http": {
                    "url": f"http://127.0.0.1:{port}/after-reply",
                    "method": "POST",
                }},
            ],
        },
    ], str(tmp_path))
    stream = io.StringIO()
    old_logger = hmock.LOGGER
    hmock.LOGGER = hmock.setup_logger("warn", stream)
    try:
        ctx = hmock.build_context("POST", "/send/abc?debug=1", "debug=1", {"X-Name": "Ada"}, "payload")
        behavior, params = hmock.find_behavior(behaviors, "POST", "/send/abc", ctx)
        ctx["HTTPParams"] = params
        ctx["HTTPPathParams"] = params
        response = hmock.execute_actions(behavior["actions"], ctx)
    finally:
        hmock.LOGGER = old_logger

    assert response.status_code == 200
    assert response.body == b"done abc"
    assert len(recording_server.records) == 2
    assert recording_server.records[0]["method"] == "POST"
    assert recording_server.records[0]["path"] == "/events/abc?debug=1"
    assert recording_server.records[0]["headers"]["X-Name"] == "Ada"
    assert recording_server.records[0]["body"] == "file payload abc"
    assert recording_server.records[1]["method"] == "PUT"
    assert recording_server.records[1]["path"] == "/inline"
    assert recording_server.records[1]["body"] == "inline abc"
    assert "send_http request failed" in stream.getvalue()


@pytest.fixture()
def server():
    behaviors = hmock.assemble_behaviors([
        {
            "key": "ping",
            "expect": {"http": {"method": "GET", "path": "/ping"}},
            "actions": [{"reply_http": {
                "status_code": 200,
                "headers": {"Content-Type": "text/plain"},
                "body": "OK",
            }}],
        }
    ])
    hmock._BEHAVIORS = behaviors
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), hmock.MockRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_http_server_match_and_unmatched_404(server):
    port = server.server_address[1]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping") as response:
        assert response.status == 200
        assert response.headers["Content-Type"] == "text/plain"
        assert response.headers["Content-Length"] == "2"
        assert response.read() == b"OK"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/missing")
    assert exc.value.code == 404
    assert exc.value.read() == b"not found"


def test_structured_logging_filters_and_fields():
    stream = io.StringIO()
    old_logger = hmock.LOGGER
    hmock.LOGGER = hmock.setup_logger("info", stream)
    try:
        hmock.log_json(
            "info",
            "http request",
            http_path="/x",
            http_method="GET",
            http_host="example.test",
            http_req={"method": "GET"},
            http_res={"status_code": 200},
        )
    finally:
        hmock.LOGGER = old_logger
    data = json.loads(stream.getvalue())
    assert data["http_path"] == "/x"
    assert data["http_method"] == "GET"
    assert data["http_host"] == "example.test"
    assert data["http_req"] == {"method": "GET"}
    assert data["http_res"] == {"status_code": 200}
