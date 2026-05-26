## 1. Dependencies

- [x] 1.1 Add `fakeredis` and `redis` to `pyproject.toml` dependencies
- [x] 1.2 Add `httpx` or confirm `urllib.request` (stdlib) is sufficient for `send_http`; update `pyproject.toml` if needed
- [x] 1.3 Run `uv lock` / `uv sync` and verify the environment resolves cleanly

## 2. Redis Backend

- [x] 2.1 Read `HM_REDIS_TYPE` and `HM_REDIS_URL` from environment at module level alongside existing config vars
- [x] 2.2 Implement `_make_redis_client()` that returns a `fakeredis.FakeRedis` instance when `HM_REDIS_TYPE=memory` and a `redis.Redis.from_url(HM_REDIS_URL)` instance when `HM_REDIS_TYPE=redis`
- [x] 2.3 Initialize a module-level `_REDIS` singleton by calling `_make_redis_client()` at startup

## 3. redisDo Template Function

- [x] 3.1 Implement `_redis_do(cmd, *args)` that calls `_REDIS.execute_command(cmd, *args)`, converts single-value results to `str`, and joins list results with `;;`
- [x] 3.2 Register `redisDo` as both a Jinja2 global and filter in `_make_jinja_env()`, pointing to `_redis_do`

## 4. redis Action

- [x] 4.1 Add `execute_redis(items, context)` that iterates the `redis` action list, renders each item as a template using `render()`, and discards the output (side effects via `redisDo` calls within the templates)
- [x] 4.2 Wire `execute_redis` into `execute_actions` so a `redis` key in an action dict calls the new executor

## 5. send_http Action

- [x] 5.1 Implement `execute_send_http(cfg, context)` that renders `url`, each header value, and `body` (or `body_from_file` snapshot when `body` is empty) as templates, then dispatches the outbound request in a daemon thread using `urllib.request`
- [x] 5.2 Catch all exceptions inside the thread and log at debug level; never propagate
- [x] 5.3 Handle `body_from_file` in `_validate_behavior`: apply the same path-resolution and snapshot logic already used for `reply_http`
- [x] 5.4 Wire `execute_send_http` into `execute_actions` so a `send_http` key in an action dict calls the new executor

## 6. Behavior Validation Update

- [x] 6.1 Update `_validate_behavior` to accept `redis` and `send_http` as known action types (no error if present)
- [x] 6.2 Verify that the existing `reply_http` duplicate-check and `sleep` duration-check are unaffected

## 7. Tests

- [x] 7.1 Add a test for `HM_REDIS_TYPE=memory`: a behavior uses `redisDo "SET"` then a second request uses `redisDo "GET"` to confirm state persists within a session
- [x] 7.2 Add a test for the `redis` action: verify Redis side effects after a request
- [x] 7.3 Add tests for all 14 supported `redisDo` commands (happy path)
- [x] 7.4 Add a test that array results from `redisDo` are joined with `;;`
- [x] 7.5 Add a test for `send_http`: verify the outbound request is dispatched and the mock response is returned regardless of outbound outcome
- [x] 7.6 Add a test that `send_http` failure does not affect the inbound response
- [x] 7.7 Add a test that `redisDo` is accessible inside a condition template
