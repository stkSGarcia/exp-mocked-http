## Context

`hmock.py` is a compact Python HTTP mock server with in-process YAML loading, validation, request matching, action execution, and template rendering. Existing behavior actions cover `sleep` and `reply_http`; templates are string-oriented and already support helper functions, strict render errors, and request context in conditions, bodies, and response headers.

This change adds stateful behavior through Redis-compatible commands and observable outbound HTTP side effects. It should preserve the single-file, dependency-light project shape and keep existing static mock behavior unchanged.

## Goals / Non-Goals

**Goals:**
- Support an embedded in-memory Redis-compatible store by default.
- Support an external Redis server when configured by environment.
- Expose Redis operations through `redisDo` in every template rendering surface.
- Execute ordered `redis` action templates as side effects.
- Execute outbound `send_http` requests as non-blocking-to-inbound-success side effects from the selected behavior's action list.
- Validate the new action shapes at mock load time.

**Non-Goals:**
- Implement the full Redis command surface beyond the listed commands.
- Provide Redis persistence for the in-memory backend.
- Retry, queue, or guarantee delivery of outbound `send_http` requests.
- Change behavior matching order, response defaults, or existing template syntax.

## Decisions

1. Introduce a small Redis adapter boundary with `MemoryRedisStore` and `ExternalRedisStore`.

   The template engine and action executor should call a single `redis_do(command: str) -> str` operation. The in-memory implementation can use Python dictionaries/lists protected by a lock. The external implementation can use a minimal RESP client over `socket` for the supported commands, avoiding a new package in this dependency-light repo.

   Alternative considered: add `redis-py`. That would reduce protocol code, but the repository currently has no dependency manifest and the command set is small enough for a focused adapter.

2. Carry runtime services through the server/execution context instead of global state.

   `Config` should include `redis_type` and `redis_url`. `build_server` should construct the Redis adapter and attach it to `HMockHTTPServer`. `find_behavior` and `execute_behavior` should build template contexts that include a callable `redisDo` bound to that adapter.

   Alternative considered: a module-level Redis singleton. That would be simpler to wire but harder to isolate in tests and unsafe across server instances.

3. Keep `redisDo` string-oriented.

   Single-value Redis command results should render as strings. Array results should join with `;;`, allowing templates to call `splitList ";;"` when a list is needed. This matches the checkpoint and avoids changing template pipeline semantics.

   Alternative considered: return Python lists directly. That would be convenient for `range`, but it would make the same Redis call render differently depending on context and would conflict with the explicit delimiter contract.

4. Validate action shapes during mock loading, render action contents during execution.

   `redis` actions must be arrays of strings. `send_http` actions must include string `url` and `method`, optional string-map `headers`, and at most one body source. `body_from_file` should reuse the safe, templates-directory-relative file loading pattern already used by `reply_http`.

   Alternative considered: defer all validation until execution. That would allow more malformed mocks to start serving and fail only when a route is hit.

5. Use `urllib.request` for outbound HTTP side effects.

   The request executor can render URL, method, headers, and body, then send the request with a short timeout. It should catch outbound request exceptions, log a warning, and continue action execution so inbound mock responses are not affected by callback failures.

   Alternative considered: fire-and-forget background threads. That would make inbound latency lower, but it would complicate ordering. The checkpoint requires mixed actions to execute together, so synchronous side effects with isolated failures are clearer.

## Risks / Trade-offs

- External Redis availability can affect `redisDo` renders and `redis` action execution. Mitigation: keep the in-memory backend as the default and surface Redis command failures as template/action errors where the command result is required.
- The minimal RESP client may not cover every Redis edge case. Mitigation: constrain validation and command execution to the explicitly supported commands and test each command family.
- `send_http` is synchronous and can add latency. Mitigation: use a conservative timeout and do not retry.
- `;;` is a lossy delimiter if list values contain that sequence. Mitigation: document it as the required delimiter and keep `splitList` as the supported reverse operation.

## Migration Plan

Existing mocks continue to run with `HM_REDIS_TYPE=memory` by default and no new actions required. Deploying the change only adds optional environment variables and optional action/template features. Rollback is to remove mocks that depend on `redis`, `redisDo`, or `send_http` before reverting the code.

## Open Questions

- What timeout should `send_http` use by default?
- Should outbound HTTP side-effect failures be logged at `warn` or `debug` once the structured logging spec is extended?
