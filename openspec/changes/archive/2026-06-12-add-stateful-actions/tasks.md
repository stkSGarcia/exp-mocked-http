## 1. Configuration and Validation

- [x] 1.1 Extend `Config` and `load_config` with `HM_REDIS_TYPE` defaulting to `memory` and `HM_REDIS_URL` defaulting to `redis://redis:6379`.
- [x] 1.2 Update behavior validation to accept `redis` actions only when the payload is an array of strings.
- [x] 1.3 Update behavior validation to accept `send_http` actions with required string `url` and `method`, optional string-map `headers`, and optional string `body` or `body_from_file`.
- [x] 1.4 Reuse the safe templates-directory file loading path for `send_http.body_from_file` snapshots.
- [x] 1.5 Add validation tests for Redis config defaults/overrides, valid new actions, invalid new action shapes, and `send_http.body_from_file` path handling.

## 2. Redis Backend

- [x] 2.1 Add a Redis adapter interface used by templates and action execution.
- [x] 2.2 Implement an in-memory Redis-compatible backend with thread-safe support for `SET`, `GET`, `RPUSH`, `LPUSH`, `LRANGE`, `LPOP`, `RPOP`, `HSET`, `HGET`, `HGETALL`, `HDEL`, `DEL`, `EXISTS`, and `KEYS`.
- [x] 2.3 Implement an external Redis backend for `HM_REDIS_TYPE=redis` using `HM_REDIS_URL` and the supported command set.
- [x] 2.4 Add Redis command parsing, arity checks, unsupported-command errors, string return formatting, and `;;` array joining.
- [x] 2.5 Add unit tests for each supported Redis command family and return formatting.

## 3. Template Integration

- [x] 3.1 Bind a `redisDo` callable into template contexts for behavior conditions, response bodies, response headers, and action templates.
- [x] 3.2 Update behavior matching so conditions can evaluate `redisDo` without changing existing fall-through behavior for render failures.
- [x] 3.3 Update response rendering so bodies and headers can use `redisDo`.
- [x] 3.4 Add template tests covering `redisDo` in conditions, response bodies, response headers, Redis action items, and `splitList ";;"` usage.

## 4. Action Execution

- [x] 4.1 Update server construction to create the configured Redis backend and attach it to `HMockHTTPServer`.
- [x] 4.2 Execute `redis` action items by rendering each string independently in array order and running the rendered Redis command.
- [x] 4.3 Execute `send_http` actions by rendering URL, headers, and body or file-backed body, then issuing the outbound HTTP request.
- [x] 4.4 Isolate outbound HTTP failures so failed `send_http` requests do not replace or prevent the inbound mock response.
- [x] 4.5 Preserve declared action ordering when a behavior mixes `redis`, `send_http`, `sleep`, and `reply_http`.

## 5. End-to-End Verification

- [x] 5.1 Add an end-to-end test for state carried across multiple inbound requests using the default in-memory Redis backend.
- [x] 5.2 Add an end-to-end test proving `send_http` receives rendered method, URL, headers, and body.
- [x] 5.3 Add an end-to-end test proving failed `send_http` side effects do not affect the inbound response.
- [x] 5.4 Run the full test suite with `uv run --with pytest pytest`.
