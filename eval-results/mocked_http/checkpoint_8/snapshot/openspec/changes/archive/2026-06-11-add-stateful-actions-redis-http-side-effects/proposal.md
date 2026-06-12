## Why

Mock definitions need stateful behavior and side-effect hooks to model realistic workflows such as token issuance, queued callbacks, idempotency keys, and event forwarding. The current server can match requests and render responses, but checkpoint 3 requires declarative actions that can mutate shared state and call outbound HTTP endpoints while preserving the existing behavior pipeline.

## What Changes

- Add Redis backend configuration through `HM_REDIS_TYPE` and `HM_REDIS_URL`, with an embedded in-memory Redis-compatible store as the default.
- Add a `redis` action that executes an ordered array of rendered Redis command template strings.
- Add a `redisDo` template function that can be used from conditions, response bodies, response headers, and `redis` action items.
- Support the checkpoint Redis command set and normalize return values for template use.
- Add a `send_http` action that performs outbound HTTP requests as side effects with templated URL, headers, and body fields.
- Allow behaviors to mix `redis`, `send_http`, `sleep`, and `reply_http` actions while preserving action order and response semantics.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `http-yaml-mock-server`: Extend behavior actions, template helpers, and server configuration with Redis-backed state and outbound HTTP side effects.

## Impact

- Affects `hmock.py` configuration loading, behavior validation, template function registration, action execution, and HTTP response handling.
- Adds an in-memory Redis-compatible implementation and an external Redis client path selected by environment.
- Adds outbound HTTP side-effect execution that logs failures without failing the inbound mock response.
- Adds test coverage for Redis command behavior, `redisDo` rendering contexts, ordered action execution, backend configuration, and non-blocking outbound HTTP failures.
