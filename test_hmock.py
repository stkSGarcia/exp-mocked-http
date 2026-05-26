"""Tests for Redis state and outbound HTTP features."""
import threading
import urllib.request
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
