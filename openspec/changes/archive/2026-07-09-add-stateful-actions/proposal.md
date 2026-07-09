## Why

Mock behaviors currently produce static request-scoped responses, which limits tests that need state transitions or observable side effects. Adding Redis-backed state and outbound HTTP side effects makes mocks useful for workflows such as queues, callbacks, counters, and multi-request scenarios.

## What Changes

- Add Redis backend configuration with an in-memory default and an external Redis option.
- Add a `redis` behavior action that renders ordered Redis command templates as side effects.
- Add a `redisDo` template function usable from conditions, bodies, headers, and Redis action templates.
- Add support for the required Redis command set and consistent string/list return formatting.
- Add a `send_http` behavior action for outbound HTTP side effects with templated URL, headers, and body.
- Ensure outbound HTTP failures do not affect inbound mock execution or response generation.

## Capabilities

### New Capabilities

### Modified Capabilities
- `mock-definition-loading`: Add Redis backend environment configuration and validate the new `redis` and `send_http` action shapes.
- `http-behavior-mocking`: Execute `redis` and `send_http` actions in declared order alongside existing actions.
- `template-rendering`: Add `redisDo` and list-splitting behavior for Redis command results.

## Impact

- Affected code: `hmock.py` configuration loading, behavior validation, action execution, template function registration, and tests.
- Runtime systems: optional external Redis via `HM_REDIS_TYPE=redis` and `HM_REDIS_URL`.
- Dependencies: may require a Redis client library and an embedded in-memory Redis-compatible implementation path.
