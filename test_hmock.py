"""Tests for Redis state and outbound HTTP features."""
import json
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer
from unittest.mock import MagicMock

import pytest

import hmock


@pytest.fixture(autouse=True)
def clean_redis():
    hmock._REDIS.flushall()
    yield
    hmock._REDIS.flushall()


# ---------------------------------------------------------------------------
# 7.1  Redis state persists within a session
# ---------------------------------------------------------------------------

def test_redis_state_persists_within_session():
    ctx1 = hmock.build_context("POST", "/", "", {}, "stored-value")
    hmock.render('{{ redisDo("SET", "last_body", HTTPBody) }}', ctx1)

    ctx2 = hmock.build_context("GET", "/", "", {}, "")
    result, err = hmock.render('{{ redisDo("GET", "last_body") }}', ctx2)
    assert err is None
    assert result == "stored-value"


# ---------------------------------------------------------------------------
# 7.2  redis action executes side effects
# ---------------------------------------------------------------------------

def test_redis_action_stores_request_body():
    ctx = hmock.build_context("POST", "/events", "", {}, "event-payload")
    hmock.execute_redis(['{{ redisDo("RPUSH", "events", HTTPBody) }}'], ctx)
    assert hmock._redis_do("LRANGE", "events", "0", "-1") == "event-payload"


def test_redis_action_multiple_items_execute_in_order():
    ctx = hmock.build_context("POST", "/", "", {}, "hello")
    hmock.execute_redis([
        '{{ redisDo("RPUSH", "log", HTTPBody) }}',
        '{{ redisDo("SET", "last", HTTPBody) }}',
    ], ctx)
    assert hmock._redis_do("LRANGE", "log", "0", "-1") == "hello"
    assert hmock._redis_do("GET", "last") == "hello"


# ---------------------------------------------------------------------------
# 7.3  All 14 supported redisDo commands (happy path)
# ---------------------------------------------------------------------------

def test_cmd_set_get():
    hmock._redis_do("SET", "k", "v")
    assert hmock._redis_do("GET", "k") == "v"


def test_cmd_rpush_lrange():
    hmock._redis_do("RPUSH", "lst", "a")
    hmock._redis_do("RPUSH", "lst", "b")
    assert hmock._redis_do("LRANGE", "lst", "0", "-1") == "a;;b"


def test_cmd_lpush():
    hmock._redis_do("LPUSH", "lst", "first")
    hmock._redis_do("LPUSH", "lst", "second")
    # LPUSH prepends, so "second" is at head
    result = hmock._redis_do("LRANGE", "lst", "0", "-1")
    assert result == "second;;first"


def test_cmd_lpop():
    hmock._redis_do("RPUSH", "lst", "x")
    hmock._redis_do("RPUSH", "lst", "y")
    assert hmock._redis_do("LPOP", "lst") == "x"


def test_cmd_rpop():
    hmock._redis_do("RPUSH", "lst", "x")
    hmock._redis_do("RPUSH", "lst", "y")
    assert hmock._redis_do("RPOP", "lst") == "y"


def test_cmd_hset_hget():
    hmock._redis_do("HSET", "h", "field1", "v1")
    assert hmock._redis_do("HGET", "h", "field1") == "v1"


def test_cmd_hgetall():
    hmock._redis_do("HSET", "h", "f1", "v1")
    hmock._redis_do("HSET", "h", "f2", "v2")
    result = hmock._redis_do("HGETALL", "h")
    # Result is flat key;;val;;key;;val — check all four tokens present
    tokens = result.split(";;")
    assert set(tokens) >= {"f1", "v1", "f2", "v2"}


def test_cmd_hdel():
    hmock._redis_do("HSET", "h", "field", "val")
    hmock._redis_do("HDEL", "h", "field")
    assert hmock._redis_do("HGET", "h", "field") == ""


def test_cmd_del_exists():
    hmock._redis_do("SET", "delme", "yes")
    assert hmock._redis_do("EXISTS", "delme") == "1"
    hmock._redis_do("DEL", "delme")
    assert hmock._redis_do("EXISTS", "delme") == "0"


def test_cmd_keys():
    hmock._redis_do("SET", "apple", "1")
    hmock._redis_do("SET", "apricot", "2")
    hmock._redis_do("SET", "banana", "3")
    keys = set(hmock._redis_do("KEYS", "a*").split(";;"))
    assert "apple" in keys
    assert "apricot" in keys
    assert "banana" not in keys


# ---------------------------------------------------------------------------
# 7.4  Array results joined with ;;
# ---------------------------------------------------------------------------

def test_lrange_joined_with_double_semicolon():
    for item in ["first", "second", "third"]:
        hmock._redis_do("RPUSH", "arr", item)
    assert hmock._redis_do("LRANGE", "arr", "0", "-1") == "first;;second;;third"


def test_keys_result_joined_with_double_semicolon():
    hmock._redis_do("SET", "k1", "a")
    hmock._redis_do("SET", "k2", "b")
    result = hmock._redis_do("KEYS", "*")
    assert ";;" in result or result in ("k1", "k2")  # at least two keys joined


# ---------------------------------------------------------------------------
# 7.5  send_http dispatches outbound request; mock response returned
# ---------------------------------------------------------------------------

def test_send_http_dispatches_request():
    done = threading.Event()
    captured = []
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured.append((req.get_full_url(), req.get_method()))
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        cfg = {"url": "http://example.com/hook", "method": "POST", "body": "payload"}
        ctx = hmock.build_context("POST", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2), "outbound request not dispatched within 2s"
        assert captured[0] == ("http://example.com/hook", "POST")
    finally:
        urllib.request.urlopen = original


def test_send_http_renders_url_template():
    done = threading.Event()
    captured_url = []
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured_url.append(req.get_full_url())
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        cfg = {"url": 'http://hooks.example.com/{{ HTTPHeader.Get("X-Tenant") }}', "method": "GET"}
        ctx = hmock.build_context("GET", "/", "", {"X-Tenant": "acme"}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2)
        assert captured_url[0] == "http://hooks.example.com/acme"
    finally:
        urllib.request.urlopen = original


# ---------------------------------------------------------------------------
# 7.6  send_http failure does not affect the inbound response
# ---------------------------------------------------------------------------

def test_send_http_failure_does_not_propagate():
    done = threading.Event()
    original = urllib.request.urlopen

    def failing_urlopen(req, timeout=None):
        done.set()
        raise OSError("connection refused")

    urllib.request.urlopen = failing_urlopen
    try:
        cfg = {"url": "http://unreachable.example.com/", "method": "POST"}
        ctx = hmock.build_context("GET", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)   # must not raise
        done.wait(timeout=2)               # wait for thread to attempt and fail
    finally:
        urllib.request.urlopen = original


# ---------------------------------------------------------------------------
# 7.7  redisDo accessible inside a condition template
# ---------------------------------------------------------------------------

def test_redis_do_usable_in_condition_true():
    hmock._redis_do("SET", "feature", "enabled")
    behaviors = [{
        "key": "flagged",
        "kind": "Behavior",
        "expect": {
            "condition": '{{ redisDo("GET", "feature") | eq("enabled") }}',
            "http": {"method": "GET", "path": "/feature"},
        },
        "actions": [],
        "_pattern": hmock._compile_path("/feature"),
    }]
    ctx = hmock.build_context("GET", "/feature", "", {}, "")
    b, _ = hmock.find_behavior(behaviors, "GET", "/feature", ctx)
    assert b is not None and b["key"] == "flagged"


def test_redis_do_usable_in_condition_false():
    hmock._redis_do("SET", "feature", "disabled")
    behaviors = [{
        "key": "flagged",
        "kind": "Behavior",
        "expect": {
            "condition": '{{ redisDo("GET", "feature") | eq("enabled") }}',
            "http": {"method": "GET", "path": "/feature"},
        },
        "actions": [],
        "_pattern": hmock._compile_path("/feature"),
    }]
    ctx = hmock.build_context("GET", "/feature", "", {}, "")
    b, _ = hmock.find_behavior(behaviors, "GET", "/feature", ctx)
    assert b is None


# ---------------------------------------------------------------------------
# Checkpoint 4: Validation — kind and field rules
# ---------------------------------------------------------------------------

def test_validate_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown kind"):
        hmock._validate_behavior({"key": "x", "kind": "Widget"}, "test")


def test_validate_template_rejects_extra_fields():
    with pytest.raises(ValueError, match="disallowed fields"):
        hmock._validate_behavior({"key": "t", "kind": "Template", "template": "x", "actions": []}, "test")


def test_validate_abstract_behavior_rejects_template_field():
    with pytest.raises(ValueError, match="disallowed fields"):
        hmock._validate_behavior({"key": "a", "kind": "AbstractBehavior", "template": "x"}, "test")


def test_validate_behavior_rejects_template_field():
    with pytest.raises(ValueError, match="disallowed fields"):
        hmock._validate_behavior({"key": "b", "kind": "Behavior", "template": "x"}, "test")


def test_validate_template_missing_template_field():
    with pytest.raises(ValueError, match="missing or empty 'template'"):
        hmock._validate_behavior({"key": "t", "kind": "Template"}, "test")


def test_validate_template_ok():
    b = hmock._validate_behavior({"key": "t", "kind": "Template", "template": "hello"}, "test")
    assert b["kind"] == "Template"


def test_validate_abstract_behavior_ok():
    b = hmock._validate_behavior({
        "key": "ab", "kind": "AbstractBehavior",
        "expect": {"http": {"method": "GET", "path": "/x"}},
        "actions": [],
        "values": {"k": "v"},
    }, "test")
    assert b["kind"] == "AbstractBehavior"


def test_validate_default_kind_is_behavior():
    b = hmock._validate_behavior({"key": "x", "expect": {}, "actions": []}, "test")
    assert b["kind"] == "Behavior"


# ---------------------------------------------------------------------------
# Checkpoint 4: Template kind rendering
# ---------------------------------------------------------------------------

def test_template_called_with_full_context():
    hmock._TEMPLATES["path-tmpl"] = "{{.HTTPPath}}"
    ctx = hmock.build_context("GET", "/hello", "", {}, "")
    result, err = hmock.render('{{ _render_tmpl("path-tmpl", None) }}', ctx)
    assert err is None
    assert result == "/hello"


def test_template_called_with_values_sub_context():
    hmock._TEMPLATES["color-tmpl"] = "{{.color}}"
    ctx = {"Values": {"color": "purple"}}
    result, err = hmock.render('{{ _render_tmpl("color-tmpl", Values) }}', ctx)
    assert err is None
    assert result == "purple"


def test_template_undefined_key_returns_empty():
    ctx = hmock.build_context("GET", "/", "", {}, "")
    result, err = hmock.render('{{ _render_tmpl("no-such-key", None) }}', ctx)
    assert err is None
    assert result == ""


def test_template_call_preprocessed_from_go_syntax():
    hmock._TEMPLATES["greet"] = "hello"
    ctx = hmock.build_context("GET", "/", "", {}, "")
    result, err = hmock.render('{{template "greet" .}}', ctx)
    assert err is None
    assert result == "hello"


def test_template_call_with_values_from_go_syntax():
    hmock._TEMPLATES["item"] = "{{.name}}"
    ctx = {**hmock.build_context("GET", "/", "", {}, ""), "Values": {"name": "widget"}}
    result, err = hmock.render('{{template "item" .Values}}', ctx)
    assert err is None
    assert result == "widget"


# ---------------------------------------------------------------------------
# Checkpoint 4: Inheritance — _merge_behavior
# ---------------------------------------------------------------------------

def test_merge_values_child_overrides_parent():
    parent = {"key": "p", "kind": "AbstractBehavior", "values": {"color": "red", "size": "large"}}
    child  = {"key": "c", "kind": "Behavior", "values": {"color": "blue"}}
    merged = hmock._merge_behavior(parent, child)
    assert merged["values"] == {"color": "blue", "size": "large"}


def test_merge_actions_parent_first():
    parent = {"key": "p", "kind": "AbstractBehavior", "actions": [{"sleep": {"duration": "10ms"}}]}
    child  = {"key": "c", "kind": "Behavior", "actions": [{"reply_http": {"status_code": 200}}]}
    merged = hmock._merge_behavior(parent, child)
    assert "sleep" in merged["actions"][0]
    assert "reply_http" in merged["actions"][1]


def test_merge_expect_child_field_wins():
    parent = {"key": "p", "kind": "AbstractBehavior",
              "expect": {"http": {"method": "GET", "path": "/base"}}}
    child  = {"key": "c", "kind": "Behavior",
              "expect": {"http": {"path": "/override"}}}
    merged = hmock._merge_behavior(parent, child)
    assert merged["expect"]["http"]["path"] == "/override"
    assert merged["expect"]["http"]["method"] == "GET"


def test_merge_child_inherits_expect_when_no_child_expect():
    parent = {"key": "p", "kind": "AbstractBehavior",
              "expect": {"http": {"method": "GET", "path": "/api"}}}
    child  = {"key": "c", "kind": "Behavior"}
    merged = hmock._merge_behavior(parent, child)
    assert merged["expect"]["http"]["method"] == "GET"
    assert merged["expect"]["http"]["path"] == "/api"


def test_load_behaviors_extend_resolves_forward_reference(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: child
  kind: Behavior
  extend: parent
  values:
    color: blue

- key: parent
  kind: AbstractBehavior
  expect:
    http:
      method: GET
      path: /item
  actions:
    - reply_http:
        status_code: 200
        body: '{{.Values.color}}'
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert len(behaviors) == 1
    b = behaviors[0]
    assert b["key"] == "child"
    assert b["expect"]["http"]["path"] == "/item"
    assert b["values"]["color"] == "blue"


def test_load_behaviors_abstract_not_matchable(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: abstract-only
  kind: AbstractBehavior
  expect:
    http:
      method: GET
      path: /api
  actions: []
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert behaviors == []


def test_load_behaviors_missing_parent_skipped(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: orphan
  kind: Behavior
  extend: nonexistent
  expect:
    http:
      method: GET
      path: /orphan
  actions:
    - reply_http:
        status_code: 200
        body: ok
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert len(behaviors) == 1
    assert behaviors[0]["key"] == "orphan"


def test_load_behaviors_template_registered_and_not_matchable(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: my-tmpl
  kind: Template
  template: 'hello {{.name}}'
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert behaviors == []
    assert "my-tmpl" in hmock._TEMPLATES


# ---------------------------------------------------------------------------
# Checkpoint 4: Values in context
# ---------------------------------------------------------------------------

def test_values_accessible_in_body():
    behaviors = [{
        "key": "colored",
        "kind": "Behavior",
        "values": {"color": "teal"},
        "expect": {"http": {"method": "GET", "path": "/color"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "{{.Values.color}}"}}],
        "_pattern": hmock._compile_path("/color"),
    }]
    ctx = hmock.build_context("GET", "/color", "", {}, "")
    b, _ = hmock.find_behavior(behaviors, "GET", "/color", ctx)
    assert b is not None
    ctx["Values"] = b.get("values") or {}
    result, err = hmock.render("{{.Values.color}}", ctx)
    assert err is None
    assert result == "teal"


def test_values_accessible_in_condition():
    behaviors = [{
        "key": "token-check",
        "kind": "Behavior",
        "values": {"expected_token": "secret"},
        "expect": {
            "condition": '{{.HTTPHeader.Get "X-Token" | eq .Values.expected_token}}',
            "http": {"method": "GET", "path": "/secured"},
        },
        "actions": [],
        "_pattern": hmock._compile_path("/secured"),
    }]
    ctx_match = hmock.build_context("GET", "/secured", "", {"X-Token": "secret"}, "")
    b, _ = hmock.find_behavior(behaviors, "GET", "/secured", ctx_match)
    assert b is not None

    ctx_no_match = hmock.build_context("GET", "/secured", "", {"X-Token": "wrong"}, "")
    b2, _ = hmock.find_behavior(behaviors, "GET", "/secured", ctx_no_match)
    assert b2 is None


def test_merged_values_exposed_after_inheritance(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: base
  kind: AbstractBehavior
  values:
    a: "1"
    b: "2"

- key: child
  kind: Behavior
  extend: base
  values:
    b: "override"
  expect:
    http:
      method: GET
      path: /val
  actions:
    - reply_http:
        status_code: 200
        body: '{{.Values.a}}-{{.Values.b}}'
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert len(behaviors) == 1
    b = behaviors[0]
    assert b["values"] == {"a": "1", "b": "override"}


# ---------------------------------------------------------------------------
# Checkpoint 4: Action ordering
# ---------------------------------------------------------------------------

def test_action_order_lower_runs_first():
    log = []
    actions = [
        {"order": 1, "reply_http": {"status_code": 200, "body": "resp"}},
        {"order": 0, "sleep": {"duration": "1ms"}},
    ]
    sorted_actions = sorted(actions, key=lambda a: int(a.get("order", 0)))
    assert "sleep" in sorted_actions[0]
    assert "reply_http" in sorted_actions[1]


def test_action_negative_order_runs_before_default():
    actions = [
        {"reply_http": {"status_code": 200, "body": "ok"}},
        {"order": -1000, "sleep": {"duration": "1ms"}},
    ]
    sorted_actions = sorted(actions, key=lambda a: int(a.get("order", 0)))
    assert "sleep" in sorted_actions[0]
    assert "reply_http" in sorted_actions[1]


def test_action_same_order_preserves_relative_order():
    actions = [
        {"order": 0, "sleep": {"duration": "1ms"}},
        {"order": 0, "reply_http": {"status_code": 200, "body": "ok"}},
    ]
    sorted_actions = sorted(actions, key=lambda a: int(a.get("order", 0)))
    assert "sleep" in sorted_actions[0]
    assert "reply_http" in sorted_actions[1]


def test_action_no_order_defaults_to_zero():
    actions = [
        {"order": -1, "sleep": {"duration": "1ms"}},
        {"reply_http": {"status_code": 200, "body": "ok"}},
    ]
    sorted_actions = sorted(actions, key=lambda a: int(a.get("order", 0)))
    assert "sleep" in sorted_actions[0]
    assert "reply_http" in sorted_actions[1]


# ---------------------------------------------------------------------------
# Checkpoint 4: End-to-end — template + inheritance + values
# ---------------------------------------------------------------------------

def test_e2e_template_inheritance_values(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: color-template
  kind: Template
  template: '{"color": "{{.color}}"}'

- key: teapot
  kind: AbstractBehavior
  expect:
    http:
      method: GET
      path: /teapot
  actions:
    - reply_http:
        status_code: 418
        body: '{{template "color-template" .Values}}'

- key: purple-teapot
  kind: Behavior
  extend: teapot
  values:
    color: purple
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert len(behaviors) == 1
    b = behaviors[0]
    assert b["key"] == "purple-teapot"
    ctx = {**hmock.build_context("GET", "/teapot", "", {}, ""), "Values": b.get("values") or {}}
    body_tmpl = b["actions"][0]["reply_http"]["body"]
    result, err = hmock.render(body_tmpl, ctx)
    assert err is None
    assert '"color": "purple"' in result


def test_e2e_ordered_inherited_actions(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: base-api
  kind: AbstractBehavior
  expect:
    http:
      method: GET
      path: /api
  actions:
    - order: 0
      reply_http:
        status_code: 200
        body: '{"result": "ok"}'

- key: slow-api
  kind: Behavior
  extend: base-api
  actions:
    - order: -1000
      sleep:
        duration: 1ms
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert len(behaviors) == 1
    b = behaviors[0]
    actions = sorted(b["actions"], key=lambda a: int(a.get("order", 0)))
    assert "sleep" in actions[0]
    assert "reply_http" in actions[1]


def test_e2e_values_in_condition(tmp_path):
    f = tmp_path / "mocks.yaml"
    f.write_text("""
- key: base-check
  kind: AbstractBehavior
  values:
    expected_token: default-token
  expect:
    condition: '{{.HTTPHeader.Get "X-Token" | eq .Values.expected_token}}'
    http:
      method: GET
      path: /secured

- key: prod-check
  kind: Behavior
  extend: base-check
  values:
    expected_token: prod-secret-123
""")
    behaviors = hmock.load_behaviors(str(tmp_path))
    assert len(behaviors) == 1

    ctx_match = hmock.build_context("GET", "/secured", "", {"X-Token": "prod-secret-123"}, "")
    b, _ = hmock.find_behavior(behaviors, "GET", "/secured", ctx_match)
    assert b is not None and b["key"] == "prod-check"

    ctx_wrong = hmock.build_context("GET", "/secured", "", {"X-Token": "default-token"}, "")
    b2, _ = hmock.find_behavior(behaviors, "GET", "/secured", ctx_wrong)
    assert b2 is None


# ---------------------------------------------------------------------------
# Checkpoint 5: Reserved keyspace guard in redisDo (tasks 1.1, 1.2, 6.10)
# ---------------------------------------------------------------------------

def test_redis_do_blocks_internal_set():
    with pytest.raises(ValueError, match="reserved internal keyspace"):
        hmock._redis_do("SET", "__hmock_internal:templates", "x")


def test_redis_do_blocks_internal_get():
    with pytest.raises(ValueError, match="reserved internal keyspace"):
        hmock._redis_do("GET", "__hmock_internal:tset:foo")


def test_redis_do_normal_key_unblocked():
    hmock._redis_do("SET", "safe_key", "val")
    assert hmock._redis_do("GET", "safe_key") == "val"


def test_redis_do_internal_keyspace_render_error():
    ctx = hmock.build_context("GET", "/", "", {}, "")
    _, err = hmock.render('{{ redisDo("SET", "__hmock_internal:templates", "x") }}', ctx)
    assert err is not None


# ---------------------------------------------------------------------------
# Checkpoint 5: Persistent storage layer (tasks 2.1–2.6)
# ---------------------------------------------------------------------------

def test_load_api_mocks_empty_when_not_set():
    assert hmock._load_api_mocks() == []


def test_save_and_load_api_mocks():
    mocks = [{"key": "m1", "kind": "Behavior", "expect": {}, "actions": []}]
    hmock._save_api_mocks(mocks)
    loaded = hmock._load_api_mocks()
    assert len(loaded) == 1
    assert loaded[0]["key"] == "m1"


def test_load_template_set_empty_when_not_set():
    assert hmock._load_template_set("noset") == []


def test_save_and_load_template_set():
    mocks = [{"key": "ts1", "kind": "Behavior", "expect": {}, "actions": []}]
    hmock._save_template_set("myset", mocks)
    loaded = hmock._load_template_set("myset")
    assert loaded[0]["key"] == "ts1"


def test_delete_template_set():
    hmock._save_template_set("todelete", [{"key": "x", "kind": "Behavior"}])
    hmock._delete_template_set("todelete")
    assert hmock._load_template_set("todelete") == []


def test_list_template_set_keys_sorted():
    hmock._save_template_set("zzz", [])
    hmock._save_template_set("aaa", [])
    keys = hmock._list_template_set_keys()
    assert "aaa" in keys and "zzz" in keys
    assert keys.index("aaa") < keys.index("zzz")


# ---------------------------------------------------------------------------
# Checkpoint 5: build_mock_set merge order (tasks 3.1, 6.11)
# ---------------------------------------------------------------------------

def _simple_mock(key, body="ok"):
    return {
        "key": key, "kind": "Behavior",
        "expect": {"http": {"method": "GET", "path": f"/{key}"}},
        "actions": [{"reply_http": {"status_code": 200, "body": body}}],
    }


def test_build_mock_set_merge_order(tmp_path):
    # Filesystem mock
    (tmp_path / "mocks.yaml").write_text(
        "- key: shared\n  kind: Behavior\n  expect:\n    http:\n      method: GET\n      path: /shared\n  actions:\n    - reply_http:\n        status_code: 200\n        body: 'filesystem'\n"
    )
    # API mock overrides filesystem
    hmock._save_api_mocks([_simple_mock("shared", "api")])
    # Template set overrides API
    hmock._save_template_set("s1", [_simple_mock("shared", "set")])

    behaviors = hmock.build_mock_set(str(tmp_path))
    shared = next((b for b in behaviors if b["key"] == "shared"), None)
    assert shared is not None
    body_tmpl = shared["actions"][0]["reply_http"]["body"]
    assert body_tmpl == "set"


def test_build_mock_set_template_sets_sorted(tmp_path):
    hmock._save_template_set("zzz", [_simple_mock("conflict", "zzz")])
    hmock._save_template_set("aaa", [_simple_mock("conflict", "aaa")])
    behaviors = hmock.build_mock_set(str(tmp_path))
    conflict = next((b for b in behaviors if b["key"] == "conflict"), None)
    # zzz loads after aaa, so zzz wins
    assert conflict["actions"][0]["reply_http"]["body"] == "zzz"


# ---------------------------------------------------------------------------
# Checkpoint 5: Admin HTTP server endpoints (tasks 4.3–4.9, 6.1–6.9, 6.12)
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_port(tmp_path):
    """Start an admin server on a free port; yield port; shut down after test."""
    server = HTTPServer(("127.0.0.1", 0), hmock.AdminRequestHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()


def _admin(method, path, port, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(len(data)))
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _admin_no_body(method, path, port):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_admin_health(admin_port):
    status, body = _admin("GET", "/api/v1/health", admin_port)
    assert status == 200
    assert body == {"status": "OK"}


def test_admin_get_templates_empty(admin_port):
    hmock._BEHAVIORS.clear()
    status, body = _admin("GET", "/api/v1/templates", admin_port)
    assert status == 200
    assert isinstance(body, list)


def test_admin_post_templates_valid(admin_port):
    mocks = [_simple_mock("admin-t1")]
    status, body = _admin("POST", "/api/v1/templates", admin_port, mocks)
    assert status == 200
    assert body[0]["key"] == "admin-t1"
    stored = hmock._load_api_mocks()
    assert any(m["key"] == "admin-t1" for m in stored)


def test_admin_post_templates_invalid(admin_port):
    status, body = _admin("POST", "/api/v1/templates", admin_port, [{"kind": "Behavior"}])
    assert status == 400
    assert "error" in body


def test_admin_post_templates_invalid_json(admin_port):
    url = f"http://127.0.0.1:{admin_port}/api/v1/templates"
    data = b"not json"
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Length", str(len(data)))
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 400


def test_admin_delete_templates(admin_port):
    hmock._save_api_mocks([_simple_mock("to-delete")])
    status, body = _admin_no_body("DELETE", "/api/v1/templates", admin_port)
    assert status == 204
    assert hmock._load_api_mocks() == []


def test_admin_delete_templates_leaves_sets(admin_port):
    hmock._save_template_set("keep", [_simple_mock("set-mock")])
    hmock._save_api_mocks([_simple_mock("api-mock")])
    _admin_no_body("DELETE", "/api/v1/templates", admin_port)
    assert hmock._load_api_mocks() == []
    assert len(hmock._load_template_set("keep")) == 1


def test_admin_delete_template_by_key(admin_port):
    hmock._save_api_mocks([_simple_mock("foo"), _simple_mock("bar")])
    status, _ = _admin_no_body("DELETE", "/api/v1/templates/foo", admin_port)
    assert status == 204
    remaining = [m["key"] for m in hmock._load_api_mocks()]
    assert "foo" not in remaining
    assert "bar" in remaining


def test_admin_delete_template_by_key_not_found(admin_port):
    hmock._save_api_mocks([])
    status, body = _admin("DELETE", "/api/v1/templates/nonexistent", admin_port, None)
    # Need to handle no-body delete with a 404
    url = f"http://127.0.0.1:{admin_port}/api/v1/templates/nonexistent"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 404


def test_admin_post_template_set(admin_port):
    mocks = [_simple_mock("set-item")]
    status, body = _admin("POST", "/api/v1/template_sets/mytest", admin_port, mocks)
    assert status == 200
    assert body[0]["key"] == "set-item"
    stored = hmock._load_template_set("mytest")
    assert stored[0]["key"] == "set-item"


def test_admin_post_template_set_replaces(admin_port):
    hmock._save_template_set("rep", [_simple_mock("old")])
    _admin("POST", "/api/v1/template_sets/rep", admin_port, [_simple_mock("new")])
    stored = hmock._load_template_set("rep")
    assert len(stored) == 1
    assert stored[0]["key"] == "new"


def test_admin_delete_template_set(admin_port):
    hmock._save_template_set("gone", [_simple_mock("g1")])
    hmock._save_template_set("kept", [_simple_mock("k1")])
    status, _ = _admin_no_body("DELETE", "/api/v1/template_sets/gone", admin_port)
    assert status == 204
    assert hmock._load_template_set("gone") == []
    assert hmock._load_template_set("kept")[0]["key"] == "k1"


def test_admin_disabled_env(monkeypatch):
    monkeypatch.setattr(hmock, "ADMIN_HTTP_ENABLED", False)
    # Just verify the flag is readable; we don't start the server in this test
    assert not hmock.ADMIN_HTTP_ENABLED


# ---------------------------------------------------------------------------
# Checkpoint 6: Binary file payloads — reply_http (task 6.1)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_server():
    """Start mock HTTP server on a free port."""
    server = HTTPServer(("127.0.0.1", 0), hmock.MockRequestHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()


def _mock_get(path, port):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _mock_req(method, path, port, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_reply_http_binary_body(tmp_path, mock_server, monkeypatch):
    bin_data = bytes(range(256))
    (tmp_path / "data.bin").write_bytes(bin_data)

    b = hmock._validate_behavior(
        {"key": "bin-reply", "kind": "Behavior",
         "expect": {"http": {"method": "GET", "path": "/bin"}},
         "actions": [{"reply_http": {"status_code": 200, "body_from_binary_file": "data.bin"}}]},
        "test", str(tmp_path)
    )
    b["_pattern"] = hmock._compile_path("/bin")
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, headers, body = _mock_get("/bin", mock_server)
    assert status == 200
    assert body == bin_data
    assert headers.get("Content-Length") == str(len(bin_data))


def test_reply_http_binary_content_length(tmp_path, mock_server, monkeypatch):
    payload = b"\x00\x01\x02\x03"
    (tmp_path / "small.bin").write_bytes(payload)
    b = hmock._validate_behavior(
        {"key": "b", "kind": "Behavior",
         "expect": {"http": {"method": "GET", "path": "/small"}},
         "actions": [{"reply_http": {"status_code": 200, "body_from_binary_file": "small.bin"}}]},
        "test", str(tmp_path)
    )
    b["_pattern"] = hmock._compile_path("/small")
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, headers, _ = _mock_get("/small", mock_server)
    assert status == 200
    assert headers.get("Content-Length") == "4"


def test_reply_http_binary_content_disposition(tmp_path, mock_server, monkeypatch):
    (tmp_path / "img.png").write_bytes(b"\x89PNG")
    b = hmock._validate_behavior(
        {"key": "img", "kind": "Behavior",
         "expect": {"http": {"method": "GET", "path": "/img"}},
         "actions": [{"reply_http": {
             "status_code": 200,
             "body_from_binary_file": "img.png",
             "binary_file_name": "photo.png",
         }}]},
        "test", str(tmp_path)
    )
    b["_pattern"] = hmock._compile_path("/img")
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, headers, _ = _mock_get("/img", mock_server)
    assert status == 200
    assert headers.get("Content-Disposition") == 'inline; filename="photo.png"'


def test_reply_http_nonempty_body_wins_over_binary(tmp_path, mock_server, monkeypatch):
    (tmp_path / "x.bin").write_bytes(b"\xFF\xFE")
    b = hmock._validate_behavior(
        {"key": "txt-wins", "kind": "Behavior",
         "expect": {"http": {"method": "GET", "path": "/txt"}},
         "actions": [{"reply_http": {
             "status_code": 200,
             "body": "hello",
             "body_from_binary_file": "x.bin",
         }}]},
        "test", str(tmp_path)
    )
    b["_pattern"] = hmock._compile_path("/txt")
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, _, body = _mock_get("/txt", mock_server)
    assert status == 200
    assert body == b"hello"


def test_validate_binary_file_escapes_dir(tmp_path):
    with pytest.raises(ValueError, match="escapes templates dir"):
        hmock._validate_behavior(
            {"key": "evil", "kind": "Behavior",
             "expect": {}, "actions": [{"reply_http": {
                 "status_code": 200,
                 "body_from_binary_file": "../../etc/passwd",
             }}]},
            "test", str(tmp_path)
        )


# ---------------------------------------------------------------------------
# Checkpoint 6: Binary file payloads — send_http (task 6.2)
# ---------------------------------------------------------------------------

def test_send_http_binary_post_multipart(tmp_path):
    payload = b"binary-content"
    (tmp_path / "upload.bin").write_bytes(payload)

    done = threading.Event()
    captured = {}
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured["method"] = req.get_method()
        captured["ct"] = req.get_header("Content-type") or req.get_header("Content-Type") or ""
        captured["body"] = req.data
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        b = hmock._validate_behavior(
            {"key": "s", "kind": "Behavior", "expect": {}, "actions": [{"send_http": {
                "url": "http://example.com/upload",
                "method": "POST",
                "body_from_binary_file": "upload.bin",
            }}]},
            "test", str(tmp_path)
        )
        cfg = b["actions"][0]["send_http"]
        ctx = hmock.build_context("POST", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2)
        assert captured["method"] == "POST"
        assert "multipart/form-data" in captured["ct"]
        assert payload in captured["body"]
    finally:
        urllib.request.urlopen = original


def test_send_http_binary_post_uses_file_field_name(tmp_path):
    payload = b"data"
    (tmp_path / "f.bin").write_bytes(payload)

    done = threading.Event()
    captured_body = []
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured_body.append(req.data)
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        b = hmock._validate_behavior(
            {"key": "s", "kind": "Behavior", "expect": {}, "actions": [{"send_http": {
                "url": "http://example.com/up",
                "method": "POST",
                "body_from_binary_file": "f.bin",
            }}]},
            "test", str(tmp_path)
        )
        cfg = b["actions"][0]["send_http"]
        ctx = hmock.build_context("POST", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2)
        # multipart body should contain 'name="file"'
        assert b'name="file"' in captured_body[0]
    finally:
        urllib.request.urlopen = original


def test_send_http_binary_post_binary_file_name_as_filename(tmp_path):
    payload = b"x"
    (tmp_path / "orig.bin").write_bytes(payload)

    done = threading.Event()
    captured_body = []
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured_body.append(req.data)
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        b = hmock._validate_behavior(
            {"key": "s", "kind": "Behavior", "expect": {}, "actions": [{"send_http": {
                "url": "http://example.com/up",
                "method": "POST",
                "body_from_binary_file": "orig.bin",
                "binary_file_name": "renamed.bin",
            }}]},
            "test", str(tmp_path)
        )
        cfg = b["actions"][0]["send_http"]
        ctx = hmock.build_context("POST", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2)
        assert b'filename="renamed.bin"' in captured_body[0]
    finally:
        urllib.request.urlopen = original


def test_send_http_binary_post_basename_fallback(tmp_path):
    payload = b"x"
    (tmp_path / "myfile.bin").write_bytes(payload)

    done = threading.Event()
    captured_body = []
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured_body.append(req.data)
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        b = hmock._validate_behavior(
            {"key": "s", "kind": "Behavior", "expect": {}, "actions": [{"send_http": {
                "url": "http://example.com/up",
                "method": "POST",
                "body_from_binary_file": "myfile.bin",
            }}]},
            "test", str(tmp_path)
        )
        cfg = b["actions"][0]["send_http"]
        ctx = hmock.build_context("POST", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2)
        assert b'filename="myfile.bin"' in captured_body[0]
    finally:
        urllib.request.urlopen = original


def test_send_http_binary_non_post_raw_body(tmp_path):
    payload = b"\xDE\xAD\xBE\xEF"
    (tmp_path / "raw.bin").write_bytes(payload)

    done = threading.Event()
    captured = {}
    original = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        captured["method"] = req.get_method()
        captured["body"] = req.data
        done.set()
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    urllib.request.urlopen = mock_urlopen
    try:
        b = hmock._validate_behavior(
            {"key": "s", "kind": "Behavior", "expect": {}, "actions": [{"send_http": {
                "url": "http://example.com/put",
                "method": "PUT",
                "body_from_binary_file": "raw.bin",
            }}]},
            "test", str(tmp_path)
        )
        cfg = b["actions"][0]["send_http"]
        ctx = hmock.build_context("PUT", "/", "", {}, "")
        hmock.execute_send_http(cfg, ctx)
        assert done.wait(timeout=2)
        assert captured["method"] == "PUT"
        assert captured["body"] == payload
    finally:
        urllib.request.urlopen = original


# ---------------------------------------------------------------------------
# Checkpoint 6: CORS middleware (task 6.3)
# ---------------------------------------------------------------------------

def test_cors_headers_on_matched_response(mock_server, monkeypatch):
    monkeypatch.setattr(hmock, "CORS_ENABLED", True)
    b = {
        "key": "hello", "kind": "Behavior",
        "expect": {"http": {"method": "GET", "path": "/hello"}},
        "actions": [{"reply_http": {"status_code": 200, "body": "hi"}}],
        "_pattern": hmock._compile_path("/hello"),
    }
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, headers, _ = _mock_get("/hello", mock_server)
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == "*"
    assert headers.get("Access-Control-Allow-Methods") == "*"
    assert headers.get("Access-Control-Allow-Headers") == "*"
    assert headers.get("Access-Control-Allow-Credentials") == "true"


def test_cors_headers_on_404(mock_server, monkeypatch):
    monkeypatch.setattr(hmock, "CORS_ENABLED", True)
    monkeypatch.setattr(hmock, "_BEHAVIORS", [])

    status, headers, _ = _mock_get("/missing", mock_server)
    assert status == 404
    assert headers.get("Access-Control-Allow-Origin") == "*"


def test_cors_mock_defined_header_overrides_middleware(mock_server, monkeypatch):
    monkeypatch.setattr(hmock, "CORS_ENABLED", True)
    b = {
        "key": "custom-cors", "kind": "Behavior",
        "expect": {"http": {"method": "GET", "path": "/custom"}},
        "actions": [{"reply_http": {
            "status_code": 200,
            "body": "ok",
            "headers": {"Access-Control-Allow-Origin": "https://example.com"},
        }}],
        "_pattern": hmock._compile_path("/custom"),
    }
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, headers, _ = _mock_get("/custom", mock_server)
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == "https://example.com"


def test_cors_unmatched_options_returns_200(mock_server, monkeypatch):
    monkeypatch.setattr(hmock, "CORS_ENABLED", True)
    monkeypatch.setattr(hmock, "_BEHAVIORS", [])

    status, headers, body = _mock_req("OPTIONS", "/api/anything", mock_server)
    assert status == 200
    assert body == b""
    assert headers.get("Access-Control-Allow-Origin") == "*"


def test_cors_disabled_options_returns_404(mock_server, monkeypatch):
    monkeypatch.setattr(hmock, "CORS_ENABLED", False)
    monkeypatch.setattr(hmock, "_BEHAVIORS", [])

    status, _, _ = _mock_req("OPTIONS", "/api/anything", mock_server)
    assert status == 404


def test_cors_matched_options_behavior_wins(mock_server, monkeypatch):
    monkeypatch.setattr(hmock, "CORS_ENABLED", True)
    b = {
        "key": "options-mock", "kind": "Behavior",
        "expect": {"http": {"method": "OPTIONS", "path": "/explicit"}},
        "actions": [{"reply_http": {"status_code": 204, "body": ""}}],
        "_pattern": hmock._compile_path("/explicit"),
    }
    monkeypatch.setattr(hmock, "_BEHAVIORS", [b])

    status, headers, _ = _mock_req("OPTIONS", "/explicit", mock_server)
    assert status == 204
    # CORS headers still added by middleware
    assert headers.get("Access-Control-Allow-Origin") == "*"


# ---------------------------------------------------------------------------
# Checkpoint 6: Hot reload (task 6.4)
# ---------------------------------------------------------------------------

def test_hot_reload_new_file_picked_up(tmp_path):
    hmock._REDIS.flushall()
    # Start with no YAML files
    behaviors = hmock.build_mock_set(str(tmp_path))
    assert behaviors == []

    # Add a YAML file
    (tmp_path / "new.yaml").write_text(
        "- key: new-behavior\n  kind: Behavior\n"
        "  expect:\n    http:\n      method: GET\n      path: /new\n"
        "  actions:\n    - reply_http:\n        status_code: 200\n        body: new\n"
    )
    behaviors2 = hmock.build_mock_set(str(tmp_path))
    assert any(b["key"] == "new-behavior" for b in behaviors2)


def test_hot_reload_edited_file_reflected(tmp_path):
    hmock._REDIS.flushall()
    f = tmp_path / "edit.yaml"
    f.write_text(
        "- key: editable\n  kind: Behavior\n"
        "  expect:\n    http:\n      method: GET\n      path: /edit\n"
        "  actions:\n    - reply_http:\n        status_code: 200\n        body: v1\n"
    )
    b1 = hmock.build_mock_set(str(tmp_path))
    body_v1 = b1[0]["actions"][0]["reply_http"]["body"]
    assert body_v1 == "v1"

    f.write_text(
        "- key: editable\n  kind: Behavior\n"
        "  expect:\n    http:\n      method: GET\n      path: /edit\n"
        "  actions:\n    - reply_http:\n        status_code: 200\n        body: v2\n"
    )
    b2 = hmock.build_mock_set(str(tmp_path))
    body_v2 = b2[0]["actions"][0]["reply_http"]["body"]
    assert body_v2 == "v2"


def test_hot_reload_deleted_file_removed(tmp_path):
    hmock._REDIS.flushall()
    f = tmp_path / "del.yaml"
    f.write_text(
        "- key: deletable\n  kind: Behavior\n"
        "  expect:\n    http:\n      method: GET\n      path: /del\n"
        "  actions:\n    - reply_http:\n        status_code: 200\n        body: bye\n"
    )
    b1 = hmock.build_mock_set(str(tmp_path))
    assert any(b["key"] == "deletable" for b in b1)

    f.unlink()
    b2 = hmock.build_mock_set(str(tmp_path))
    assert not any(b["key"] == "deletable" for b in b2)


def test_hot_reload_failure_preserves_previous_state(tmp_path, monkeypatch):
    hmock._REDIS.flushall()
    f = tmp_path / "good.yaml"
    f.write_text(
        "- key: valid\n  kind: Behavior\n"
        "  expect:\n    http:\n      method: GET\n      path: /valid\n"
        "  actions:\n    - reply_http:\n        status_code: 200\n        body: ok\n"
    )
    hmock.build_mock_set(str(tmp_path))

    # Capture current _BEHAVIORS before the failing reload
    original_behaviors = list(hmock._BEHAVIORS)

    # Simulate a reload failure by patching _load_filesystem_items to raise
    monkeypatch.setattr(hmock, "_load_filesystem_items", lambda _: (_ for _ in ()).throw(ValueError("bad yaml")))
    hmock._reload_event.set()
    # Manually run one reload cycle
    hmock._reload_event.wait(timeout=0.1)
    hmock._reload_event.clear()
    try:
        new_behaviors = hmock.build_mock_set(str(tmp_path))
    except ValueError:
        pass
    # _BEHAVIORS should be unchanged (still has the valid behavior)
    with hmock._BEHAVIORS_LOCK:
        current = list(hmock._BEHAVIORS)
    assert current == original_behaviors


# ---------------------------------------------------------------------------
# Checkpoint 6: omctl CLI (task 6.5)
# ---------------------------------------------------------------------------

import omctl as omctl_mod


def test_omctl_push_no_set_key_posts_to_templates(tmp_path, admin_port):
    (tmp_path / "t.yaml").write_text(
        "- key: omctl-test\n  kind: Behavior\n  expect: {}\n  actions: []\n"
    )
    args = omctl_mod._parse_args(["push", "-d", str(tmp_path), "-u", f"http://127.0.0.1:{admin_port}"])
    omctl_mod.cmd_push(args)
    stored = hmock._load_api_mocks()
    assert any(m["key"] == "omctl-test" for m in stored)


def test_omctl_push_with_set_key_posts_to_template_sets(tmp_path, admin_port):
    (tmp_path / "ts.yaml").write_text(
        "- key: set-item\n  kind: Behavior\n  expect: {}\n  actions: []\n"
    )
    args = omctl_mod._parse_args(["push", "-d", str(tmp_path), "-u", f"http://127.0.0.1:{admin_port}", "-k", "mytest2"])
    omctl_mod.cmd_push(args)
    stored = hmock._load_template_set("mytest2")
    assert any(m["key"] == "set-item" for m in stored)


def test_omctl_delete_sends_delete(tmp_path, admin_port):
    hmock._save_template_set("todel", [_simple_mock("d1")])
    args = omctl_mod._parse_args(["delete", "-u", f"http://127.0.0.1:{admin_port}", "-k", "todel"])
    omctl_mod.cmd_delete(args)
    assert hmock._load_template_set("todel") == []


def test_omctl_delete_missing_set_key_exits_nonzero():
    with pytest.raises(SystemExit) as exc_info:
        omctl_mod._parse_args(["delete", "-u", "http://localhost:9998"])
    assert exc_info.value.code != 0


def test_omctl_push_server_error_exits_nonzero(tmp_path, admin_port):
    (tmp_path / "t.yaml").write_text("- key: err\n  kind: Widget\n")  # invalid kind → 400
    args = omctl_mod._parse_args(["push", "-d", str(tmp_path), "-u", f"http://127.0.0.1:{admin_port}"])
    with pytest.raises(SystemExit) as exc_info:
        omctl_mod.cmd_push(args)
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# 8.1  _resolve_kafka_role_config
# ---------------------------------------------------------------------------

def test_kafka_role_config_producer_uses_own_brokers(monkeypatch):
    monkeypatch.setattr(hmock, "KAFKA_SEED_BROKERS", "default:9092")
    monkeypatch.setattr(hmock, "KAFKA_PRODUCER_BROKERS", "prod:9092")
    monkeypatch.setattr(hmock, "KAFKA_CONSUMER_BROKERS", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PROD_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PROD_PASSWORD", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PASSWORD", "")
    monkeypatch.setattr(hmock, "_KAFKA_TLS_PROD_RAW", "")
    monkeypatch.setattr(hmock, "KAFKA_TLS_ENABLED", False)
    cfg = hmock._resolve_kafka_role_config("producer")
    assert cfg["brokers"] == ["prod:9092"]


def test_kafka_role_config_consumer_falls_back_to_shared_brokers(monkeypatch):
    monkeypatch.setattr(hmock, "KAFKA_SEED_BROKERS", "default:9092")
    monkeypatch.setattr(hmock, "KAFKA_CONSUMER_BROKERS", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_CONS_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_CONS_PASSWORD", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PASSWORD", "")
    monkeypatch.setattr(hmock, "_KAFKA_TLS_CONS_RAW", "")
    monkeypatch.setattr(hmock, "KAFKA_TLS_ENABLED", False)
    cfg = hmock._resolve_kafka_role_config("consumer")
    assert cfg["brokers"] == ["default:9092"]


def test_kafka_role_config_consumer_sasl_from_shared(monkeypatch):
    monkeypatch.setattr(hmock, "KAFKA_SEED_BROKERS", "kafka:9092")
    monkeypatch.setattr(hmock, "KAFKA_CONSUMER_BROKERS", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_CONS_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_CONS_PASSWORD", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_USERNAME", "user")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PASSWORD", "pass")
    monkeypatch.setattr(hmock, "_KAFKA_TLS_CONS_RAW", "")
    monkeypatch.setattr(hmock, "KAFKA_TLS_ENABLED", False)
    cfg = hmock._resolve_kafka_role_config("consumer")
    assert cfg["sasl_enabled"] is True
    assert cfg["username"] == "user"
    assert cfg["password"] == "pass"


def test_kafka_role_config_sasl_disabled_when_password_empty(monkeypatch):
    monkeypatch.setattr(hmock, "KAFKA_SEED_BROKERS", "kafka:9092")
    monkeypatch.setattr(hmock, "KAFKA_CONSUMER_BROKERS", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_CONS_USERNAME", "user")
    monkeypatch.setattr(hmock, "KAFKA_SASL_CONS_PASSWORD", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PASSWORD", "")
    monkeypatch.setattr(hmock, "_KAFKA_TLS_CONS_RAW", "")
    monkeypatch.setattr(hmock, "KAFKA_TLS_ENABLED", False)
    cfg = hmock._resolve_kafka_role_config("consumer")
    assert cfg["sasl_enabled"] is False


def test_kafka_role_config_producer_tls_override(monkeypatch):
    monkeypatch.setattr(hmock, "KAFKA_SEED_BROKERS", "kafka:9092")
    monkeypatch.setattr(hmock, "KAFKA_PRODUCER_BROKERS", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PROD_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PROD_PASSWORD", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_USERNAME", "")
    monkeypatch.setattr(hmock, "KAFKA_SASL_PASSWORD", "")
    monkeypatch.setattr(hmock, "_KAFKA_TLS_PROD_RAW", "true")
    monkeypatch.setattr(hmock, "KAFKA_TLS_ENABLED", False)
    cfg = hmock._resolve_kafka_role_config("producer")
    assert cfg["tls_enabled"] is True


# ---------------------------------------------------------------------------
# 8.2  _validate_behavior — publish_kafka and publish_amqp
# ---------------------------------------------------------------------------

def test_validate_publish_kafka_valid():
    b = {"key": "k1", "actions": [{"publish_kafka": {"topic": "events", "payload": "hello"}}]}
    result = hmock._validate_behavior(b, "test")
    assert result["key"] == "k1"


def test_validate_publish_kafka_missing_topic():
    b = {"key": "k1", "actions": [{"publish_kafka": {"payload": "hello"}}]}
    with pytest.raises(ValueError, match="publish_kafka requires 'topic'"):
        hmock._validate_behavior(b, "test")


def test_validate_publish_kafka_missing_payload():
    b = {"key": "k1", "actions": [{"publish_kafka": {"topic": "events"}}]}
    with pytest.raises(ValueError, match="publish_kafka requires 'payload' or 'payload_from_file'"):
        hmock._validate_behavior(b, "test")


def test_validate_publish_amqp_valid():
    b = {
        "key": "k1",
        "actions": [{"publish_amqp": {"exchange": "ex", "routing_key": "rk", "payload": "hi"}}],
    }
    result = hmock._validate_behavior(b, "test")
    assert result["key"] == "k1"


def test_validate_publish_amqp_missing_exchange():
    b = {
        "key": "k1",
        "actions": [{"publish_amqp": {"routing_key": "rk", "payload": "hi"}}],
    }
    with pytest.raises(ValueError, match="publish_amqp requires 'exchange'"):
        hmock._validate_behavior(b, "test")


def test_validate_publish_amqp_missing_routing_key():
    b = {
        "key": "k1",
        "actions": [{"publish_amqp": {"exchange": "ex", "payload": "hi"}}],
    }
    with pytest.raises(ValueError, match="publish_amqp requires 'routing_key'"):
        hmock._validate_behavior(b, "test")


def test_validate_publish_amqp_missing_payload():
    b = {
        "key": "k1",
        "actions": [{"publish_amqp": {"exchange": "ex", "routing_key": "rk"}}],
    }
    with pytest.raises(ValueError, match="publish_amqp requires 'payload' or 'payload_from_file'"):
        hmock._validate_behavior(b, "test")


# ---------------------------------------------------------------------------
# 8.3  find_all_behaviors_for_kafka
# ---------------------------------------------------------------------------

def _kafka_behavior(key, topic, condition=None):
    expect: dict = {"kafka": {"topic": topic}}
    if condition:
        expect["condition"] = condition
    return {"key": key, "kind": "Behavior", "expect": expect, "actions": [], "values": {}}


def test_kafka_topic_match_returns_behavior():
    behaviors = [_kafka_behavior("b1", "events"), _kafka_behavior("b2", "other")]
    ctx = {"KafkaTopic": "events", "KafkaPayload": ""}
    result = hmock.find_all_behaviors_for_kafka(behaviors, "events", ctx)
    assert [b["key"] for b in result] == ["b1"]


def test_kafka_execute_all_matching():
    behaviors = [_kafka_behavior("b1", "events"), _kafka_behavior("b2", "events")]
    ctx = {"KafkaTopic": "events", "KafkaPayload": ""}
    result = hmock.find_all_behaviors_for_kafka(behaviors, "events", ctx)
    assert [b["key"] for b in result] == ["b1", "b2"]


def test_kafka_no_match_wrong_topic():
    behaviors = [_kafka_behavior("b1", "events")]
    ctx = {"KafkaTopic": "orders", "KafkaPayload": ""}
    result = hmock.find_all_behaviors_for_kafka(behaviors, "orders", ctx)
    assert result == []


def test_kafka_condition_filters_behavior():
    behaviors = [
        _kafka_behavior("b1", "events", condition="{{ false }}"),
        _kafka_behavior("b2", "events"),
    ]
    ctx = {"KafkaTopic": "events", "KafkaPayload": ""}
    result = hmock.find_all_behaviors_for_kafka(behaviors, "events", ctx)
    assert [b["key"] for b in result] == ["b2"]


def test_kafka_loaded_order_preserved():
    behaviors = [_kafka_behavior("b1", "t"), _kafka_behavior("b2", "t"), _kafka_behavior("b3", "t")]
    ctx = {"KafkaTopic": "t", "KafkaPayload": ""}
    result = hmock.find_all_behaviors_for_kafka(behaviors, "t", ctx)
    assert [b["key"] for b in result] == ["b1", "b2", "b3"]


# ---------------------------------------------------------------------------
# 8.4  find_all_behaviors_for_amqp
# ---------------------------------------------------------------------------

def _amqp_behavior(key, exchange, routing_key, queue=None, condition=None):
    amqp: dict = {"exchange": exchange, "routing_key": routing_key}
    if queue:
        amqp["queue"] = queue
    else:
        amqp["queue"] = routing_key
    expect: dict = {"amqp": amqp}
    if condition:
        expect["condition"] = condition
    return {"key": key, "kind": "Behavior", "expect": expect, "actions": [], "values": {}}


def test_amqp_match_returns_behavior():
    behaviors = [
        _amqp_behavior("b1", "ex", "rk"),
        _amqp_behavior("b2", "ex", "other"),
    ]
    ctx = {"AMQPExchange": "ex", "AMQPRoutingKey": "rk", "AMQPQueue": "rk", "AMQPPayload": ""}
    result = hmock.find_all_behaviors_for_amqp(behaviors, "ex", "rk", "rk", ctx)
    assert [b["key"] for b in result] == ["b1"]


def test_amqp_execute_all_matching():
    behaviors = [_amqp_behavior("b1", "ex", "rk"), _amqp_behavior("b2", "ex", "rk")]
    ctx = {"AMQPExchange": "ex", "AMQPRoutingKey": "rk", "AMQPQueue": "rk", "AMQPPayload": ""}
    result = hmock.find_all_behaviors_for_amqp(behaviors, "ex", "rk", "rk", ctx)
    assert [b["key"] for b in result] == ["b1", "b2"]


def test_amqp_no_match_wrong_exchange():
    behaviors = [_amqp_behavior("b1", "ex", "rk")]
    ctx = {"AMQPExchange": "other", "AMQPRoutingKey": "rk", "AMQPQueue": "rk", "AMQPPayload": ""}
    result = hmock.find_all_behaviors_for_amqp(behaviors, "other", "rk", "rk", ctx)
    assert result == []


def test_amqp_condition_filters_behavior():
    behaviors = [
        _amqp_behavior("b1", "ex", "rk", condition="{{ false }}"),
        _amqp_behavior("b2", "ex", "rk"),
    ]
    ctx = {"AMQPExchange": "ex", "AMQPRoutingKey": "rk", "AMQPQueue": "rk", "AMQPPayload": ""}
    result = hmock.find_all_behaviors_for_amqp(behaviors, "ex", "rk", "rk", ctx)
    assert [b["key"] for b in result] == ["b2"]


# ---------------------------------------------------------------------------
# 8.5  _assemble_behaviors — AMQP queue defaulting
# ---------------------------------------------------------------------------

def test_amqp_queue_defaults_to_routing_key():
    items = [{
        "key": "b1",
        "kind": "Behavior",
        "expect": {"amqp": {"exchange": "ex", "routing_key": "rk"}},
        "actions": [],
    }]
    _, behaviors = hmock._assemble_behaviors(items)
    assert behaviors[0]["expect"]["amqp"]["queue"] == "rk"


def test_amqp_explicit_queue_not_overridden():
    items = [{
        "key": "b1",
        "kind": "Behavior",
        "expect": {"amqp": {"exchange": "ex", "routing_key": "rk", "queue": "myqueue"}},
        "actions": [],
    }]
    _, behaviors = hmock._assemble_behaviors(items)
    assert behaviors[0]["expect"]["amqp"]["queue"] == "myqueue"
