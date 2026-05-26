## Why

The mock server currently only supports stateless replies. Adding Redis-backed state and outbound HTTP side effects enables modeling stateful workflows (counters, queues, stored data) and webhook/callback patterns — use cases that are common in integration testing.

## What Changes

- Add `HM_REDIS_TYPE` and `HM_REDIS_URL` environment variables to configure an in-memory or external Redis backend.
- Add `redisDo` template function usable in any template context (conditions, bodies, headers, `redis` action items).
- Add `redis` action: an ordered list of Redis command template strings executed as side effects.
- Add `send_http` action: makes an outbound HTTP request as a side effect; failures do not affect the mock response.

## Capabilities

### New Capabilities
- `redis-state`: Redis backend configuration, the `redis` action, and the `redisDo` template function — including supported commands, return value serialization, and environment-variable-driven backend selection.
- `send-http`: The `send_http` action for making outbound HTTP requests as side effects from a behavior, including field definitions and failure-isolation semantics.

### Modified Capabilities
- `http-mock-server`: Behavior validation requirements expand to recognize `redis` and `send_http` as valid action types alongside `sleep` and `reply_http`.

## Impact

- `hmock.py`: new env-var handling, Redis client abstraction, `redisDo` template function, `redis` and `send_http` action executors.
- Dependencies: add an in-memory Redis-compatible library (e.g., `fakeredis`) and an HTTP client (e.g., `httpx` or `requests`).
- Existing behaviors are unaffected; the new actions are additive.
