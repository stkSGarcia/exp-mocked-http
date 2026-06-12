## 1. Redis Backend Configuration

- [x] 1.1 Extend `Config` and `load_config` with `HM_REDIS_TYPE` defaulting to `memory` and `HM_REDIS_URL` defaulting to `redis://redis:6379`.
- [x] 1.2 Add validation for supported Redis backend types and tests for default and overridden Redis configuration.
- [x] 1.3 Add an in-memory Redis-compatible backend for `SET`, `GET`, `RPUSH`, `LPUSH`, `LRANGE`, `LPOP`, `RPOP`, `HSET`, `HGET`, `HGETALL`, `HDEL`, `DEL`, `EXISTS`, and `KEYS`.
- [x] 1.4 Add an external Redis backend path for `HM_REDIS_TYPE=redis` and update project dependencies if a Redis client library is used.

## 2. Redis Template and Action Execution

- [x] 2.1 Add command parsing and result normalization so single values render as strings and array results join with `;;`.
- [x] 2.2 Register `redisDo` in the template environment as a global and filter backed by the configured Redis backend.
- [x] 2.3 Extend action preparation and validation so `redis` actions must contain an array of template strings.
- [x] 2.4 Extend `execute_actions` so `redis` action items render and execute independently in order before later actions continue.
- [x] 2.5 Add tests proving `redisDo` works in conditions, response bodies, response headers, and `redis` action item templates.

## 3. Outbound HTTP Side Effects

- [x] 3.1 Extend action preparation and validation for `send_http.url`, `send_http.method`, optional templated headers, optional `body`, and optional `body_from_file`.
- [x] 3.2 Reuse file-backed body resolution and snapshot behavior for `send_http.body_from_file`, including inline body precedence.
- [x] 3.3 Implement outbound HTTP request execution with rendered URL, method, headers, and body.
- [x] 3.4 Log outbound HTTP failures and continue matched behavior execution without changing the inbound response because of the failure.
- [x] 3.5 Add tests for successful outbound requests, templated fields, file-backed bodies, inline precedence, and failure isolation.

## 4. Mixed Action Integration

- [x] 4.1 Ensure behaviors can mix `redis`, `send_http`, `sleep`, and `reply_http` actions in one ordered list.
- [x] 4.2 Preserve the existing behavior that `reply_http` returns the inbound response and prevents later actions from executing.
- [x] 4.3 Add integration-style tests for action order across Redis writes, outbound HTTP side effects, sleeps, and replies.

## 5. Verification

- [x] 5.1 Run `uv run pytest`.
- [x] 5.2 Run `openspec status --change "add-stateful-actions-redis-http-side-effects"` and confirm the change is ready for implementation.
