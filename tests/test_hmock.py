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


def request(url, method="GET", body=None, headers=None):
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            return res.status, dict(res.headers), res.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()


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
        }
    )

    assert config == hmock.Config("/tmp/mocks", 7777, "127.0.0.1", "warn")


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
