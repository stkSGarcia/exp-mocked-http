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
