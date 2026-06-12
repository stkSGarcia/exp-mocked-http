import io
import json
import hashlib
import hmac
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import hmock
import omctl


@pytest.fixture(autouse=True)
def reset_redis_backend():
    old_backend = hmock._REDIS_BACKEND
    old_templates = hmock._NAMED_TEMPLATES
    old_behaviors = hmock._BEHAVIORS
    old_definitions = hmock._ACTIVE_DEFINITIONS
    old_kafka_producer = hmock._KAFKA_PRODUCER
    old_amqp_connection = hmock._AMQP_PUBLISH_CONNECTION
    old_amqp_channel = hmock._AMQP_PUBLISH_CHANNEL
    hmock._REDIS_BACKEND = hmock.MemoryRedisBackend()
    hmock._NAMED_TEMPLATES = {}
    hmock._BEHAVIORS = []
    hmock._ACTIVE_DEFINITIONS = []
    hmock._KAFKA_PRODUCER = None
    hmock._AMQP_PUBLISH_CONNECTION = None
    hmock._AMQP_PUBLISH_CHANNEL = None
    try:
        yield
    finally:
        hmock._REDIS_BACKEND = old_backend
        hmock._NAMED_TEMPLATES = old_templates
        hmock._BEHAVIORS = old_behaviors
        hmock._ACTIVE_DEFINITIONS = old_definitions
        hmock._KAFKA_PRODUCER = old_kafka_producer
        hmock._AMQP_PUBLISH_CONNECTION = old_amqp_connection
        hmock._AMQP_PUBLISH_CHANNEL = old_amqp_channel


def test_config_defaults_and_overrides():
    assert hmock.load_config({}) == hmock.Config()
    config = hmock.load_config({
        "HM_TEMPLATES_DIR": "/tmp/mocks",
        "HM_TEMPLATES_DIR_HOT_RELOAD": "false",
        "HM_HTTP_PORT": "1234",
        "HM_HTTP_HOST": "127.0.0.1",
        "HM_CORS_ENABLED": "true",
        "HM_ADMIN_HTTP_ENABLED": "false",
        "HM_ADMIN_HTTP_PORT": "4321",
        "HM_ADMIN_HTTP_HOST": "127.0.0.2",
        "HM_LOG_LEVEL": "debug",
        "HM_REDIS_TYPE": "redis",
        "HM_REDIS_URL": "redis://example.test:6380/2",
    })
    assert config.templates_dir == "/tmp/mocks"
    assert config.templates_dir_hot_reload is False
    assert config.http_port == 1234
    assert config.http_host == "127.0.0.1"
    assert config.cors_enabled is True
    assert config.admin_http_enabled is False
    assert config.admin_http_port == 4321
    assert config.admin_http_host == "127.0.0.2"
    assert config.log_level == "debug"
    assert config.redis_type == "redis"
    assert config.redis_url == "redis://example.test:6380/2"

    with pytest.raises(ValueError, match="HM_REDIS_TYPE"):
        hmock.load_config({"HM_REDIS_TYPE": "bad"})
    with pytest.raises(ValueError, match="HM_ADMIN_HTTP_ENABLED"):
        hmock.load_config({"HM_ADMIN_HTTP_ENABLED": "sometimes"})
    with pytest.raises(ValueError, match="HM_TEMPLATES_DIR_HOT_RELOAD"):
        hmock.load_config({"HM_TEMPLATES_DIR_HOT_RELOAD": "sometimes"})
    with pytest.raises(ValueError, match="HM_CORS_ENABLED"):
        hmock.load_config({"HM_CORS_ENABLED": "sometimes"})
    with pytest.raises(ValueError):
        hmock.load_config({"HM_ADMIN_HTTP_PORT": "not-a-port"})


def test_broker_config_defaults_overrides_and_role_resolution():
    defaults = hmock.load_config({})
    assert defaults.kafka_enabled is False
    assert defaults.kafka_client_id == "hmock"
    assert defaults.kafka_seed_brokers == "kafka:9092"
    assert defaults.amqp_enabled is False
    assert defaults.amqp_url == "amqp://guest:guest@rabbitmq:5672"

    config = hmock.load_config({
        "HM_KAFKA_ENABLED": "true",
        "HM_KAFKA_CLIENT_ID": "test-client",
        "HM_KAFKA_SEED_BROKERS": "shared-a:9092, shared-b:9092",
        "HM_KAFKA_SASL_USERNAME": "shared-user",
        "HM_KAFKA_SASL_PASSWORD": "shared-pass",
        "HM_KAFKA_TLS_ENABLED": "true",
        "HM_KAFKA_PRODUCER_SEED_BROKERS": "producer:9092",
        "HM_KAFKA_SASL_PRODUCER_USERNAME": "producer-user",
        "HM_KAFKA_SASL_PRODUCER_PASSWORD": "producer-pass",
        "HM_KAFKA_TLS_PRODUCER_ENABLED": "false",
        "HM_KAFKA_TLS_CONSUMER_ENABLED": "true",
        "HM_AMQP_ENABLED": "true",
        "HM_AMQP_URL": "amqp://example.test/vhost",
    })
    producer = hmock.resolve_kafka_role(config, "producer")
    consumer = hmock.resolve_kafka_role(config, "consumer")
    assert producer.seed_brokers == ("producer:9092",)
    assert producer.sasl_username == "producer-user"
    assert producer.sasl_enabled is True
    assert producer.tls_enabled is False
    assert consumer.seed_brokers == ("shared-a:9092", "shared-b:9092")
    assert consumer.sasl_username == "shared-user"
    assert consumer.sasl_enabled is True
    assert consumer.tls_enabled is True
    assert config.amqp_enabled is True
    assert config.amqp_url == "amqp://example.test/vhost"

    partial = hmock.load_config({
        "HM_KAFKA_SASL_USERNAME": "user-only",
        "HM_KAFKA_SASL_PRODUCER_PASSWORD": "producer-pass-only",
    })
    assert hmock.resolve_kafka_role(partial, "consumer").sasl_enabled is False
    assert hmock.resolve_kafka_role(partial, "producer").sasl_enabled is True
    with pytest.raises(ValueError, match="HM_KAFKA_ENABLED"):
        hmock.load_config({"HM_KAFKA_ENABLED": "sometimes"})
    with pytest.raises(ValueError, match="HM_KAFKA_TLS_CONSUMER_ENABLED"):
        hmock.load_config({"HM_KAFKA_TLS_CONSUMER_ENABLED": "sometimes"})
    with pytest.raises(ValueError, match="HM_AMQP_ENABLED"):
        hmock.load_config({"HM_AMQP_ENABLED": "sometimes"})


def test_disabled_admin_server_does_not_start(monkeypatch):
    called = False

    def unexpected_create(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(hmock, "create_admin_server", unexpected_create)
    server, thread = hmock.start_admin_server(hmock.Config(admin_http_enabled=False))

    assert server is None
    assert thread is None
    assert called is False


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


def test_redis_do_blocks_reserved_keyspace_before_backend_execution():
    class RecordingBackend(hmock.RedisBackend):
        def __init__(self):
            self.calls = []

        def execute(self, args):
            self.calls.append(args)
            return "OK"

    backend = RecordingBackend()
    hmock._REDIS_BACKEND = backend

    for command in [
        "GET __hmock_internal:templates",
        "HGET __hmock_internal:template_sets demo",
        "KEYS __hmock_internal:*",
        "DEL public __hmock_internal:templates",
    ]:
        with pytest.raises(hmock.TemplateRenderError, match="reserved"):
            hmock.render(f'{{{{ redisDo "{command}" }}}}', {})

    assert backend.calls == []
    assert hmock.render('{{ redisDo "GET public" }}', {}) == "OK"
    assert backend.calls == [["GET", "public"]]


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


def test_binary_reply_loading_precedence_snapshot_and_validation(tmp_path):
    binary = tmp_path / "payload.bin"
    original = b"\x00\xff{{not rendered}}\x10"
    binary.write_bytes(original)
    definitions = [{
        "key": "binary",
        "actions": [{
            "reply_http": {
                "status_code": 200,
                "body": "",
                "body_from_binary_file": "payload.bin",
                "binary_file_name": "report.bin",
            },
        }],
    }, {
        "key": "inline",
        "actions": [{
            "reply_http": {
                "status_code": 200,
                "body": "inline",
                "body_from_binary_file": "payload.bin",
                "binary_file_name": "ignored.bin",
            },
        }],
    }]
    behaviors = hmock.assemble_behaviors(definitions, str(tmp_path))
    binary.write_bytes(b"changed")

    response = hmock.execute_actions(behaviors[0]["actions"], {})
    inline = hmock.execute_actions(behaviors[1]["actions"], {})

    assert response.body == original
    assert response.headers["Content-Length"] == str(len(original))
    assert response.headers["Content-Disposition"] == 'inline; filename="report.bin"'
    assert inline.body == b"inline"
    assert "Content-Disposition" not in inline.headers

    with pytest.raises(ValueError, match="body_from_binary_file must resolve inside"):
        hmock.assemble_behaviors([{
            "key": "outside",
            "actions": [{"reply_http": {
                "status_code": 200,
                "body_from_binary_file": "../outside.bin",
            }}],
        }], str(tmp_path))
    with pytest.raises(ValueError, match="cannot read body_from_binary_file"):
        hmock.assemble_behaviors([{
            "key": "missing",
            "actions": [{"reply_http": {
                "status_code": 200,
                "body_from_binary_file": "missing.bin",
            }}],
        }], str(tmp_path))


class RecordingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _record(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length) if length else b""
        self.server.records.append({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body": raw_body.decode("utf-8", errors="replace"),
            "raw_body": raw_body,
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


def test_send_http_binary_multipart_raw_and_inline_precedence(tmp_path, recording_server):
    payload = b"\x00\xffbinary\r\nbytes"
    (tmp_path / "asset.bin").write_bytes(payload)
    port = recording_server.server_address[1]
    behaviors = hmock.assemble_behaviors([{
        "key": "binary-send",
        "actions": [
            {"send_http": {
                "url": f"http://127.0.0.1:{port}/multipart",
                "method": "POST",
                "headers": {"Content-Type": "image/png", "X-Test": "yes"},
                "body_from_binary_file": "asset.bin",
                "binary_file_name": "upload.png",
            }},
            {"send_http": {
                "url": f"http://127.0.0.1:{port}/raw",
                "method": "PUT",
                "body_from_binary_file": "asset.bin",
            }},
            {"send_http": {
                "url": f"http://127.0.0.1:{port}/multipart-defaults",
                "method": "POST",
                "body_from_binary_file": "asset.bin",
            }},
            {"send_http": {
                "url": f"http://127.0.0.1:{port}/inline",
                "method": "PUT",
                "body": "text wins",
                "body_from_binary_file": "asset.bin",
            }},
        ],
    }], str(tmp_path))

    hmock.execute_actions(behaviors[0]["actions"], {})

    multipart, raw, multipart_defaults, inline = recording_server.records
    assert multipart["method"] == "POST"
    assert multipart["headers"]["X-Test"] == "yes"
    assert multipart["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="upload.png"' in multipart["raw_body"]
    assert b"Content-Type: image/png" in multipart["raw_body"]
    assert payload in multipart["raw_body"]
    assert raw["method"] == "PUT"
    assert raw["raw_body"] == payload
    assert b'name="file"; filename="asset.bin"' in multipart_defaults["raw_body"]
    assert b"Content-Type: application/octet-stream" in multipart_defaults["raw_body"]
    assert inline["raw_body"] == b"text wins"


def test_persisted_definition_loading_precedence_and_restart(tmp_path):
    (tmp_path / "mocks.yaml").write_text("""
- key: filesystem-only
  actions: []
- key: duplicate
  actions:
    - reply_http:
        status_code: 200
        body: filesystem
""", encoding="utf-8")
    backend = hmock.MemoryRedisBackend()
    config = hmock.Config(templates_dir=str(tmp_path))
    hmock.save_persisted_base([
        {"key": "base-only", "actions": []},
        {
            "key": "duplicate",
            "actions": [{"reply_http": {"status_code": 200, "body": "base"}}],
        },
    ], backend)
    hmock.save_persisted_set("z-set", [
        {
            "key": "duplicate",
            "actions": [{"reply_http": {"status_code": 200, "body": "z-set"}}],
        },
    ], backend)
    hmock.save_persisted_set("a-set", [
        {"key": "set-only", "actions": []},
        {
            "key": "duplicate",
            "actions": [{"reply_http": {"status_code": 200, "body": "a-set"}}],
        },
    ], backend)

    state = hmock.reload_runtime(config, backend)
    keys = [definition["key"] for definition in state.definitions]
    duplicate = next(behavior for behavior in state.behaviors if behavior["key"] == "duplicate")
    response = hmock.execute_actions(duplicate["actions"], {})

    assert keys == ["filesystem-only", "base-only", "set-only", "duplicate"]
    assert response.body == b"z-set"

    hmock.install_runtime(hmock.RuntimeState([], [], {}))
    restarted = hmock.reload_runtime(config, backend)
    assert [definition["key"] for definition in restarted.definitions] == keys


def test_persisted_definitions_share_composition_and_file_validation(tmp_path):
    (tmp_path / "mocks.yaml").write_text("""
- key: greeting
  kind: Template
  template: "hello {{.name}}"
- key: base
  kind: AbstractBehavior
  expect:
    http:
      method: GET
      path: /hello
  actions:
    - reply_http:
        status_code: 200
        body: '{{ template "greeting" .Values }}'
""", encoding="utf-8")
    backend = hmock.MemoryRedisBackend()
    config = hmock.Config(templates_dir=str(tmp_path))
    hmock.save_persisted_base([
        {"key": "child", "extend": "base", "values": {"name": "Ada"}},
    ], backend)

    state = hmock.reload_runtime(config, backend)
    context = hmock.build_context("GET", "/hello", "", {}, "")
    behavior, params = hmock.find_behavior(state.behaviors, "GET", "/hello", context)
    context["HTTPParams"] = params
    context["HTTPPathParams"] = params
    context["Values"] = behavior["values"]
    assert hmock.execute_actions(behavior["actions"], context).body == b"hello Ada"

    with pytest.raises(ValueError, match="inside HM_TEMPLATES_DIR"):
        hmock.build_runtime(
            config,
            [{
                "key": "bad-file",
                "actions": [{
                    "reply_http": {
                        "status_code": 200,
                        "body_from_file": "../outside.txt",
                    },
                }],
            }],
            {},
            backend,
        )


def _http_request(url, method="GET", data=None, raw_data=None, content_type=None):
    headers = {}
    body = raw_data
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if content_type is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw and exc.headers.get_content_type() == "application/json" else raw


@pytest.fixture()
def admin_server(tmp_path):
    backend = hmock.MemoryRedisBackend()
    config = hmock.Config(
        templates_dir=str(tmp_path),
        admin_http_host="127.0.0.1",
        admin_http_port=0,
    )
    hmock._REDIS_BACKEND = backend
    hmock.reload_runtime(config, backend)
    httpd = hmock.create_admin_server(config, backend)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, config, backend, tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_admin_health_base_templates_and_atomic_validation(admin_server):
    httpd, config, backend, _ = admin_server
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    first = {
        "key": "first",
        "expect": {"http": {"method": "GET", "path": "/first"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "one"}}],
    }
    second = {"key": "second", "actions": []}

    assert _http_request(f"{root}/api/v1/health") == (200, {"status": "OK"})
    assert _http_request(f"{root}/api/v1/templates") == (200, [])
    assert _http_request(f"{root}/api/v1/templates", "POST", [first, second]) == (
        200,
        [first, second],
    )
    assert [item["key"] for item in hmock.load_persisted_base(backend)] == ["first", "second"]
    assert [item["key"] for item in _http_request(f"{root}/api/v1/templates")[1]] == [
        "first",
        "second",
    ]

    replacement = dict(first)
    replacement["actions"] = [{"reply_http": {"status_code": 201, "body": "updated"}}]
    assert _http_request(f"{root}/api/v1/templates", "POST", replacement) == (200, [replacement])
    assert [item["key"] for item in hmock.load_persisted_base(backend)] == ["second", "first"]

    status, error = _http_request(
        f"{root}/api/v1/templates",
        "POST",
        [{"key": "invalid", "actions": "not-a-list"}],
    )
    assert status == 400
    assert "actions" in error["error"]
    assert [item["key"] for item in hmock.load_persisted_base(backend)] == ["second", "first"]
    status, error = _http_request(
        f"{root}/api/v1/templates",
        "POST",
        raw_data=b"{broken",
    )
    assert status == 400
    assert "invalid JSON" in error["error"]
    assert _http_request(f"{root}/api/v1/templates/missing", "DELETE")[0] == 404
    assert _http_request(f"{root}/api/v1/templates/second", "DELETE") == (204, None)
    assert [item["key"] for item in hmock.load_persisted_base(backend)] == ["first"]
    assert _http_request(f"{root}/api/v1/templates", "DELETE") == (204, None)
    assert hmock.load_persisted_base(backend) == []


def test_admin_template_set_isolation_and_validation(admin_server):
    httpd, config, backend, _ = admin_server
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    base = {"key": "base", "actions": []}
    set_a = {"key": "set-a", "actions": []}
    set_b = {"key": "set-b", "actions": []}

    assert _http_request(f"{root}/api/v1/templates", "POST", base) == (200, [base])
    assert _http_request(f"{root}/api/v1/template_sets/a", "POST", [set_a]) == (200, [set_a])
    assert _http_request(f"{root}/api/v1/template_sets/b", "POST", [set_b]) == (200, [set_b])
    assert set(hmock.load_persisted_sets(backend)) == {"a", "b"}

    status, error = _http_request(
        f"{root}/api/v1/template_sets/a",
        "POST",
        [{"key": "invalid", "actions": {}}],
    )
    assert status == 400
    assert "actions" in error["error"]
    assert hmock.load_persisted_sets(backend)["a"] == [set_a]

    assert _http_request(f"{root}/api/v1/template_sets/a", "DELETE") == (204, None)
    assert hmock.load_persisted_sets(backend) == {"b": [set_b]}
    assert hmock.load_persisted_base(backend) == [base]
    assert _http_request(f"{root}/api/v1/template_sets/absent", "DELETE") == (204, None)


def test_admin_accepts_yaml_and_rejects_invalid_yaml_atomically(admin_server):
    httpd, _, backend, _ = admin_server
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    definition = {"key": "yaml-base", "actions": []}
    payload = yaml.safe_dump([definition]).encode("utf-8")

    assert _http_request(
        f"{root}/api/v1/templates",
        "POST",
        raw_data=payload,
        content_type="application/yaml",
    ) == (200, [definition])
    assert hmock.load_persisted_base(backend) == [definition]

    status, error = _http_request(
        f"{root}/api/v1/template_sets/bad",
        "POST",
        raw_data=b"- key: broken\n  actions: [",
        content_type="application/x-yaml",
    )
    assert status == 400
    assert "invalid YAML" in error["error"]
    assert hmock.load_persisted_sets(backend) == {}
    assert hmock.load_persisted_base(backend) == [definition]


def test_admin_mutations_are_immediately_visible_and_preserve_filesystem_mock(admin_server):
    httpd, config, backend, tmp_path = admin_server
    (tmp_path / "filesystem.yaml").write_text("""
key: shared
expect:
  http:
    method: GET
    path: /filesystem
actions:
  - reply_http:
      status_code: 200
      body: filesystem
""", encoding="utf-8")
    hmock.reload_runtime(config, backend)
    mock_server = ThreadingHTTPServer(("127.0.0.1", 0), hmock.MockRequestHandler)
    mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    mock_thread.start()
    admin_root = f"http://127.0.0.1:{httpd.server_address[1]}"
    mock_root = f"http://127.0.0.1:{mock_server.server_address[1]}"
    api_definition = {
        "key": "shared",
        "expect": {"http": {"method": "GET", "path": "/api"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "api"}}],
    }
    try:
        assert _http_request(f"{admin_root}/api/v1/templates", "POST", api_definition)[0] == 200
        with urllib.request.urlopen(f"{mock_root}/api") as response:
            assert response.read() == b"api"

        assert _http_request(f"{admin_root}/api/v1/templates/shared", "DELETE") == (204, None)
        with urllib.request.urlopen(f"{mock_root}/filesystem") as response:
            assert response.read() == b"filesystem"
        active = _http_request(f"{admin_root}/api/v1/templates")[1]
        assert [(item["key"], item["expect"]["http"]["path"]) for item in active] == [
            ("shared", "/filesystem"),
        ]
    finally:
        mock_server.shutdown()
        mock_server.server_close()
        mock_thread.join(timeout=2)


def test_mock_request_uses_one_runtime_generation():
    old_state = hmock.compile_runtime([
        {"key": "message", "kind": "Template", "template": "old"},
        {
            "key": "slow",
            "expect": {"http": {"method": "GET", "path": "/slow"}},
            "actions": [
                {"sleep": {"duration": "100ms"}},
                {"reply_http": {"status_code": 200, "body": '{{ template "message" . }}'}},
            ],
        },
    ])
    new_state = hmock.compile_runtime([
        {"key": "message", "kind": "Template", "template": "new"},
        {
            "key": "slow",
            "expect": {"http": {"method": "GET", "path": "/slow"}},
            "actions": [{"reply_http": {"status_code": 200, "body": '{{ template "message" . }}'}}],
        },
    ])
    hmock.install_runtime(old_state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), hmock.MockRequestHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    result = {}

    def request_slow():
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/slow") as response:
            result["body"] = response.read()

    request_thread = threading.Thread(target=request_slow)
    request_thread.start()
    time.sleep(0.03)
    hmock.install_runtime(new_state)
    request_thread.join(timeout=2)
    try:
        assert result["body"] == b"old"
    finally:
        httpd.shutdown()
        httpd.server_close()
        server_thread.join(timeout=2)


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def _response_body(path):
    state = hmock.runtime_snapshot()
    context = hmock.build_context("GET", path, "", {}, "")
    behavior, params = hmock.find_behavior(state.behaviors, "GET", path, context)
    if behavior is None:
        return None
    context["HTTPParams"] = params
    context["HTTPPathParams"] = params
    context["Values"] = behavior.get("values") or {}
    return hmock.execute_actions(behavior["actions"], context).body


def test_hot_reload_create_edit_delete_invalid_and_fixture_changes(tmp_path):
    template = tmp_path / "mock.yaml"
    fixture = tmp_path / "body.txt"
    fixture.write_text("fixture one", encoding="utf-8")
    template.write_text("""
key: reload
expect:
  http:
    method: GET
    path: /reload
actions:
  - reply_http:
      status_code: 200
      body_from_file: body.txt
""", encoding="utf-8")
    backend = hmock.MemoryRedisBackend()
    config = hmock.Config(templates_dir=str(tmp_path))
    hmock.reload_runtime(config, backend)
    stop, thread = hmock.start_hot_reload_worker(config, backend, interval=0.01)
    try:
        assert _response_body("/reload") == b"fixture one"
        fixture.write_text("fixture two", encoding="utf-8")
        _wait_until(lambda: _response_body("/reload") == b"fixture two")

        template.write_text("broken: [", encoding="utf-8")
        time.sleep(0.05)
        assert _response_body("/reload") == b"fixture two"

        template.write_text("""
key: edited
expect:
  http:
    method: GET
    path: /edited
actions:
  - reply_http:
      status_code: 200
      body: edited
""", encoding="utf-8")
        _wait_until(lambda: _response_body("/edited") == b"edited")
        assert _response_body("/reload") is None

        created = tmp_path / "created.yml"
        created.write_text("""
key: created
expect:
  http:
    method: GET
    path: /created
actions:
  - reply_http:
      status_code: 200
      body: created
""", encoding="utf-8")
        _wait_until(lambda: _response_body("/created") == b"created")
        created.unlink()
        _wait_until(lambda: _response_body("/created") is None)
    finally:
        stop.set()
        thread.join(timeout=2)


def test_disabled_hot_reload_defers_filesystem_until_admin_boundary(tmp_path):
    template = tmp_path / "mock.yaml"
    template.write_text("""
key: value
expect:
  http:
    method: GET
    path: /value
actions:
  - reply_http:
      status_code: 200
      body: old
""", encoding="utf-8")
    backend = hmock.MemoryRedisBackend()
    config = hmock.Config(
        templates_dir=str(tmp_path),
        templates_dir_hot_reload=False,
    )
    hmock.reload_runtime(config, backend)
    stop, thread = hmock.start_hot_reload_worker(config, backend, interval=0.01)
    assert stop is None
    assert thread is None

    template.write_text(template.read_text(encoding="utf-8").replace("body: old", "body: new"))
    time.sleep(0.05)
    assert _response_body("/value") == b"old"
    hmock.mutate_base_templates(
        config,
        submitted=[{"key": "admin-boundary", "actions": []}],
        backend=backend,
    )
    assert _response_body("/value") == b"new"


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


def test_cors_headers_preflight_and_mock_precedence():
    state = hmock.compile_runtime([
        {
            "key": "get",
            "expect": {"http": {"method": "GET", "path": "/cors"}},
            "actions": [{"reply_http": {
                "status_code": 200,
                "headers": {"access-control-allow-origin": "https://client.example"},
                "body": "ok",
            }}],
        },
        {
            "key": "options",
            "expect": {"http": {"method": "OPTIONS", "path": "/explicit"}},
            "actions": [{"reply_http": {"status_code": 202, "body": "explicit"}}],
        },
    ])
    hmock.install_runtime(state)
    config = hmock.Config(http_host="127.0.0.1", http_port=0, cors_enabled=True)
    httpd = hmock.create_server(config, backend=hmock.MemoryRedisBackend())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{root}/cors") as response:
            assert response.headers["access-control-allow-origin"] == "https://client.example"
            assert response.headers.get_all("Access-Control-Allow-Origin") == [
                "https://client.example",
            ]
            assert response.headers["Access-Control-Allow-Methods"] == "*"
            assert response.headers["Access-Control-Allow-Headers"] == "*"
            assert response.headers["Access-Control-Allow-Credentials"] == "true"

        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"{root}/missing")
        assert exc.value.code == 404
        assert exc.value.headers["Access-Control-Allow-Origin"] == "*"

        request = urllib.request.Request(f"{root}/preflight", method="OPTIONS")
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
            assert response.read() == b""
            assert response.headers["Access-Control-Allow-Origin"] == "*"

        request = urllib.request.Request(f"{root}/explicit", method="OPTIONS")
        with urllib.request.urlopen(request) as response:
            assert response.status == 202
            assert response.read() == b"explicit"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_unmatched_options_is_404_when_cors_disabled():
    hmock.install_runtime(hmock.RuntimeState([], [], {}))
    config = hmock.Config(http_host="127.0.0.1", http_port=0, cors_enabled=False)
    httpd = hmock.create_server(config, backend=hmock.MemoryRedisBackend())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/preflight",
            method="OPTIONS",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        assert exc.value.code == 404
        assert "Access-Control-Allow-Origin" not in exc.value.headers
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_omctl_push_delete_and_failures(tmp_path, admin_server, monkeypatch, capsys):
    httpd, _, backend, _ = admin_server
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "a.yaml").write_text("key: first\nactions: []\n", encoding="utf-8")
    (nested / "b.yml").write_text("- key: second\n  actions: []\n", encoding="utf-8")

    assert omctl.main(["push", "-d", str(tmp_path), "-u", root]) == 0
    assert [item["key"] for item in hmock.load_persisted_base(backend)] == ["first", "second"]
    assert omctl.main([
        "push",
        "-d",
        str(tmp_path),
        "-u",
        root,
        "-k",
        "set/key",
    ]) == 0
    assert "set/key" in hmock.load_persisted_sets(backend)
    assert omctl.main(["delete", "-u", root, "-k", "set/key"]) == 0
    assert hmock.load_persisted_sets(backend) == {}

    (tmp_path / "broken.yaml").write_text("broken: [", encoding="utf-8")
    called = False

    def unexpected_request(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(omctl, "_request", unexpected_request)
    assert omctl.main(["push", "-d", str(tmp_path), "-u", root]) == 1
    assert called is False
    assert "omctl:" in capsys.readouterr().err


def test_omctl_defaults_help_and_unexpected_status(tmp_path, monkeypatch, capsys):
    parser = omctl.build_parser()
    push = parser.parse_args(["push"])
    assert push.directory == "./demo_templates"
    assert push.url == "http://localhost:9998"
    delete = parser.parse_args(["delete", "-k", "demo"])
    assert delete.url == "http://localhost:9998"

    with pytest.raises(SystemExit):
        parser.parse_args(["delete"])
    with pytest.raises(SystemExit) as exc:
        omctl.main(["--help"])
    assert exc.value.code == 0
    help_output = capsys.readouterr().out
    assert "push" in help_output
    assert "delete" in help_output

    (tmp_path / "mock.yaml").write_text("key: demo\nactions: []\n", encoding="utf-8")

    def fail_request(*args, **kwargs):
        raise RuntimeError("unexpected status")

    monkeypatch.setattr(omctl, "_request", fail_request)
    assert omctl.main(["push", "-d", str(tmp_path)]) == 1
    assert "unexpected status" in capsys.readouterr().err


def test_installed_omctl_entry_point_against_admin_server(tmp_path, admin_server):
    httpd, _, backend, _ = admin_server
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    (tmp_path / "mock.yaml").write_text("key: installed\nactions: []\n", encoding="utf-8")
    executable = str(Path(__file__).with_name(".venv") / "bin" / "omctl")

    help_result = subprocess.run(
        [executable, "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "push" in help_result.stdout
    assert "delete" in help_result.stdout

    push_result = subprocess.run(
        [
            executable,
            "push",
            "-d",
            str(tmp_path),
            "-u",
            root,
            "-k",
            "installed-set",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert push_result.returncode == 0, push_result.stderr
    assert "installed-set" in hmock.load_persisted_sets(backend)

    delete_result = subprocess.run(
        [executable, "delete", "-u", root, "-k", "installed-set"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert delete_result.returncode == 0, delete_result.stderr
    assert hmock.load_persisted_sets(backend) == {}


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


def test_broker_definition_validation_queue_defaults_and_payload_files(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_text("file {{.KafkaPayload}}", encoding="utf-8")
    behaviors = hmock.assemble_behaviors([
        {
            "key": "broker-actions",
            "expect": {
                "kafka": {"topic": "input"},
                "amqp": {"exchange": "events", "routing_key": "created"},
            },
            "actions": [
                {"publish_kafka": {
                    "topic": "output",
                    "payload_from_file": "payload.txt",
                }},
                {"publish_amqp": {
                    "exchange": "out",
                    "routing_key": "done",
                    "payload": "inline",
                    "payload_from_file": "payload.txt",
                }},
            ],
        },
    ], str(tmp_path))
    payload.write_text("changed", encoding="utf-8")

    behavior = behaviors[0]
    assert behavior["expect"]["amqp"]["queue"] == "created"
    assert behavior["actions"][0]["publish_kafka"]["_payload_from_file_content"] == (
        "file {{.KafkaPayload}}"
    )
    assert hmock._select_payload_template(
        behavior["actions"][1]["publish_amqp"]
    ) == "inline"

    invalid_definitions = [
        {"key": "kafka", "expect": {"kafka": {}}, "actions": []},
        {"key": "amqp-exchange", "expect": {"amqp": {"routing_key": "x"}}, "actions": []},
        {"key": "amqp-routing", "expect": {"amqp": {"exchange": "x"}}, "actions": []},
        {"key": "publish-kafka", "actions": [{"publish_kafka": {"payload": "x"}}]},
        {"key": "publish-amqp", "actions": [{"publish_amqp": {
            "exchange": "x",
            "routing_key": "y",
        }}]},
    ]
    for definition in invalid_definitions:
        with pytest.raises(ValueError):
            hmock.assemble_behaviors([definition], str(tmp_path))

    with pytest.raises(ValueError, match="payload_from_file must resolve inside"):
        hmock.assemble_behaviors([{
            "key": "outside",
            "actions": [{"publish_kafka": {
                "topic": "x",
                "payload_from_file": "../outside.txt",
            }}],
        }], str(tmp_path))
    with pytest.raises(ValueError, match="cannot read payload_from_file"):
        hmock.assemble_behaviors([{
            "key": "missing",
            "actions": [{"publish_amqp": {
                "exchange": "x",
                "routing_key": "y",
                "payload_from_file": "missing.txt",
            }}],
        }], str(tmp_path))


def test_broker_matching_dispatch_order_conditions_and_context(monkeypatch):
    state = hmock.compile_runtime([
        {
            "key": "kafka-skip",
            "values": {"expected": "other"},
            "expect": {
                "kafka": {"topic": "events"},
                "condition": "{{.KafkaPayload | eq .Values.expected}}",
            },
            "actions": [],
        },
        {
            "key": "kafka-first",
            "expect": {"kafka": {"topic": "events"}},
            "actions": [],
        },
        {
            "key": "kafka-second",
            "expect": {"kafka": {"topic": "events"}},
            "actions": [],
        },
        {
            "key": "amqp-first",
            "expect": {
                "amqp": {
                    "exchange": "domain",
                    "routing_key": "created",
                    "queue": "workers",
                },
            },
            "actions": [],
        },
        {
            "key": "amqp-second",
            "expect": {
                "amqp": {
                    "exchange": "domain",
                    "routing_key": "created",
                    "queue": "workers",
                },
            },
            "actions": [],
        },
    ])
    for behavior in state.behaviors:
        behavior["actions"] = [{"record": behavior["key"]}]
    hmock.install_runtime(state)
    records = []

    def record_actions(actions, context):
        records.append((actions[0]["record"], dict(context)))
        return hmock.Response(204, {"Content-Length": "0"}, b"")

    monkeypatch.setattr(hmock, "execute_actions", record_actions)
    assert hmock.dispatch_kafka_message("events", "payload") == 2
    assert [item[0] for item in records] == ["kafka-first", "kafka-second"]
    assert records[0][1]["KafkaTopic"] == "events"
    assert records[0][1]["KafkaPayload"] == "payload"

    records.clear()
    assert hmock.dispatch_amqp_message("domain", "created", "workers", "body") == 2
    assert [item[0] for item in records] == ["amqp-first", "amqp-second"]
    assert records[0][1]["AMQPExchange"] == "domain"
    assert records[0][1]["AMQPRoutingKey"] == "created"
    assert records[0][1]["AMQPQueue"] == "workers"
    assert records[0][1]["AMQPPayload"] == "body"
    assert hmock.dispatch_kafka_message("unknown", "payload") == 0


def test_broker_publish_actions_render_and_log_unavailable(tmp_path):
    (tmp_path / "payload.txt").write_text("file {{.KafkaPayload}}", encoding="utf-8")
    behavior = hmock.assemble_behaviors([{
        "key": "publish",
        "actions": [
            {"publish_kafka": {
                "topic": "out-{{.KafkaTopic}}",
                "payload_from_file": "payload.txt",
            }},
            {"publish_amqp": {
                "exchange": "exchange-{{.KafkaTopic}}",
                "routing_key": "route",
                "payload": "inline {{.KafkaPayload}}",
            }},
        ],
    }], str(tmp_path))[0]

    class Producer:
        def __init__(self):
            self.sent = []

        def send(self, topic, payload):
            self.sent.append((topic, payload))

    class Channel:
        def __init__(self):
            self.published = []

        def basic_publish(self, **kwargs):
            self.published.append(kwargs)

    producer = Producer()
    channel = Channel()
    hmock._KAFKA_PRODUCER = producer
    hmock._AMQP_PUBLISH_CHANNEL = channel
    hmock.execute_actions(
        behavior["actions"],
        {"KafkaTopic": "source", "KafkaPayload": "message"},
    )
    assert producer.sent == [("out-source", b"file message")]
    assert channel.published == [{
        "exchange": "exchange-source",
        "routing_key": "route",
        "body": b"inline message",
    }]

    hmock._KAFKA_PRODUCER = None
    stream = io.StringIO()
    old_logger = hmock.LOGGER
    hmock.LOGGER = hmock.setup_logger("warn", stream)
    try:
        hmock.publish_kafka_message(
            {"topic": "out", "payload": "data"},
            {},
        )
    finally:
        hmock.LOGGER = old_logger
    log = json.loads(stream.getvalue())
    assert log["transport"] == "kafka"
    assert log["operation"] == "publish"


def test_kafka_factories_settings_topics_worker_and_shutdown(monkeypatch):
    producer_kwargs = {}
    consumer_kwargs = {}

    class LibraryProducer:
        def __init__(self, **kwargs):
            producer_kwargs.update(kwargs)

    class LibraryConsumer:
        def __init__(self, **kwargs):
            consumer_kwargs.update(kwargs)

    import kafka
    monkeypatch.setattr(kafka, "KafkaProducer", LibraryProducer)
    monkeypatch.setattr(kafka, "KafkaConsumer", LibraryConsumer)
    config = hmock.Config(
        kafka_enabled=True,
        kafka_client_id="client",
        kafka_seed_brokers="a:1,b:2",
        kafka_sasl_username="user",
        kafka_sasl_password="pass",
        kafka_tls_enabled=True,
    )
    hmock.create_kafka_producer(config)
    hmock.create_kafka_consumer(config)
    assert producer_kwargs["bootstrap_servers"] == ["a:1", "b:2"]
    assert producer_kwargs["security_protocol"] == "SASL_SSL"
    assert producer_kwargs["sasl_plain_username"] == "user"
    assert consumer_kwargs["auto_offset_reset"] == "earliest"

    first = hmock.compile_runtime([
        {"key": "one", "expect": {"kafka": {"topic": "one"}}, "actions": []},
        {"key": "duplicate", "expect": {"kafka": {"topic": "one"}}, "actions": []},
    ])
    second = hmock.compile_runtime([
        {"key": "two", "expect": {"kafka": {"topic": "two"}}, "actions": []},
    ])
    hmock.install_runtime(first)
    stop = threading.Event()

    class FakeConsumer:
        def __init__(self):
            self.subscriptions = []
            self.closed = False
            self.poll_count = 0

        def subscribe(self, topics):
            self.subscriptions.append(tuple(topics))

        def poll(self, timeout_ms):
            self.poll_count += 1
            if self.poll_count == 1:
                hmock.install_runtime(second)
                return {"partition": [SimpleNamespace(topic="one", value=b"payload")]}
            stop.set()
            return {}

        def close(self):
            self.closed = True

    dispatched = []
    monkeypatch.setattr(
        hmock,
        "dispatch_kafka_message",
        lambda topic, payload: dispatched.append((topic, payload)),
    )
    consumer = FakeConsumer()
    hmock.run_kafka_worker(consumer, stop, interval=0.001)
    assert consumer.subscriptions == [("one",), ("two",)]
    assert dispatched == [("one", "payload")]

    assert hmock.start_kafka_worker(hmock.Config(kafka_enabled=False)) is None
    producer = SimpleNamespace(closed=False)
    producer.close = lambda: setattr(producer, "closed", True)
    idle_consumer = FakeConsumer()
    idle_consumer.poll = lambda timeout_ms: {}
    worker = hmock.start_kafka_worker(
        hmock.Config(kafka_enabled=True),
        producer_factory=lambda _: producer,
        consumer_factory=lambda _: idle_consumer,
        interval=0.001,
    )
    assert worker is not None
    worker.stop()
    assert producer.closed is True
    assert idle_consumer.closed is True

    stream = io.StringIO()
    old_logger = hmock.LOGGER
    hmock.LOGGER = hmock.setup_logger("error", stream)
    try:
        with pytest.raises(RuntimeError, match="secret-user"):
            hmock.start_kafka_worker(
                hmock.Config(
                    kafka_enabled=True,
                    kafka_sasl_username="secret-user",
                    kafka_sasl_password="secret-pass",
                ),
                producer_factory=lambda _: (_ for _ in ()).throw(
                    RuntimeError("failed for secret-user:secret-pass")
                ),
            )
    finally:
        hmock.LOGGER = old_logger
    assert "secret-user" not in stream.getvalue()
    assert "secret-pass" not in stream.getvalue()
    assert "[redacted]" in stream.getvalue()


def test_amqp_topology_dispatch_reconnect_and_shutdown(monkeypatch):
    state = hmock.compile_runtime([
        {
            "key": "one",
            "expect": {"amqp": {
                "exchange": "events",
                "routing_key": "created",
                "queue": "",
            }},
            "actions": [],
        },
        {
            "key": "duplicate",
            "expect": {"amqp": {
                "exchange": "events",
                "routing_key": "created",
            }},
            "actions": [],
        },
    ])
    hmock.install_runtime(state)
    topology = hmock.amqp_topology(state.behaviors)
    assert topology == (("events", "created", "created"),)

    class FakeChannel:
        def __init__(self):
            self.exchanges = []
            self.queues = []
            self.bindings = []
            self.consumers = []
            self.published = []

        def exchange_declare(self, **kwargs):
            self.exchanges.append(kwargs)

        def queue_declare(self, **kwargs):
            self.queues.append(kwargs)

        def queue_bind(self, **kwargs):
            self.bindings.append(kwargs)

        def basic_consume(self, **kwargs):
            self.consumers.append(kwargs)

        def basic_publish(self, **kwargs):
            self.published.append(kwargs)

    channel = FakeChannel()
    hmock.setup_amqp_topology(channel, topology)
    assert channel.exchanges == [{"exchange": "events"}]
    assert channel.queues == [{"queue": "created"}]
    assert len(channel.bindings) == 1
    assert len(channel.consumers) == 1

    delivered = []
    monkeypatch.setattr(
        hmock,
        "dispatch_amqp_message",
        lambda exchange, routing_key, queue, payload: delivered.append(
            (exchange, routing_key, queue, payload)
        ),
    )
    channel.consumers[0]["on_message_callback"](
        None,
        SimpleNamespace(exchange="events", routing_key="created"),
        None,
        b"payload",
    )
    assert delivered == [("events", "created", "created", "payload")]

    stop = threading.Event()

    class FakeConnection:
        def __init__(self, fail=False, stop_after=False):
            self.channel_value = FakeChannel()
            self.fail = fail
            self.stop_after = stop_after
            self.closed = False

        def channel(self):
            return self.channel_value

        def process_data_events(self, time_limit):
            if self.fail:
                self.fail = False
                raise RuntimeError("transient disconnect")
            if self.stop_after:
                stop.set()

        def close(self):
            self.closed = True

    connections = [FakeConnection(fail=True), FakeConnection(stop_after=True)]
    hmock.run_amqp_worker(
        hmock.Config(amqp_enabled=True),
        stop,
        connection_factory=lambda _: connections.pop(0),
        interval=0.001,
        reconnect_delay=0,
    )
    assert connections == []

    assert hmock.start_amqp_worker(hmock.Config(amqp_enabled=False)) is None
    created = []

    def connection_factory(_):
        connection = FakeConnection(stop_after=True)
        created.append(connection)
        return connection

    worker = hmock.start_amqp_worker(
        hmock.Config(amqp_enabled=True),
        connection_factory=connection_factory,
        interval=0.001,
        reconnect_delay=0,
    )
    assert worker is not None
    worker.stop()
    assert created[0].closed is True
