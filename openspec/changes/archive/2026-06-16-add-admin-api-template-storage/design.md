## Context

`hmock.py` currently loads YAML files from `HM_TEMPLATES_DIR` once during `build_server`, validates them into `Behavior` objects, and stores that list on `HMockHTTPServer`. Runtime Redis support already exists through `MemoryRedisStore` and `ExternalRedisStore`, and template rendering calls `redisDo` directly through the active store.

The new admin API crosses server configuration, definition loading, Redis persistence, HTTP routing, and template safety, so the implementation should introduce a small shared runtime state instead of spreading mutable globals across handlers.

## Related Work

> **`http-behavior-mocking/add-http-yaml-mock-server`**: Defines the mock server entry point and request-serving behavior — informs keeping the admin server separate from the mock server because the prior intent established a lightweight replay server with stable request behavior. _(see `http-behavior-mocking/add-http-yaml-mock-server`)_

> **`http-behavior-mocking/add-stateful-actions`**: Defines Redis-backed action execution and `redisDo` access — informs using the existing Redis abstraction for persistence and adding keyspace checks before user templates can execute commands because the prior intent introduced Redis state as observable mock behavior. _(see `http-behavior-mocking/add-stateful-actions`)_

> **`http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`**: Defines reusable templates, inheritance, duplicate-key behavior, and stable action ordering — informs reusing the same validation and effective-definition pipeline for API-added definitions because the prior intent made loaded definitions composable. _(see `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`)_

## Goals / Non-Goals

**Goals:**

- Add admin server configuration to `Config` and `load_config`.
- Serve admin endpoints from a separate `ThreadingHTTPServer` using the configured admin host and port.
- Persist base API-managed mocks and named template sets in Redis under `__hmock_internal:*`.
- Reload the active behavior list after successful admin mutations using the same validation, inheritance, template, and duplicate-key rules as filesystem loading.
- Block template-originated `redisDo` commands from touching `__hmock_internal:*`.
- Cover admin endpoints, persistence/reload behavior, merge ordering, isolation, and keyspace blocking in `tests/test_hmock.py`.

**Non-Goals:**

- Authentication or authorization for the admin API.
- A new storage backend beyond the existing Redis abstraction.
- Hot-reloading filesystem changes unrelated to admin mutations.
- Partial patch semantics for individual mock fields; admin writes replace whole submitted definitions or whole template sets.

## Decisions

### Shared Runtime State

Introduce an `HMockRuntimeState` that owns the logger, Redis store, templates directory, persistent template store, and active `Behavior` list behind a lock. `HMockHTTPServer` should read behaviors through this state per request instead of owning an immutable list.

Alternative considered: rebuild and replace the whole mock server after every admin mutation. That would complicate listener lifecycle and make reload visibility dependent on socket restarts.

### Redis Persistence Envelope

Store base API-managed mocks as JSON at `__hmock_internal:templates` and template sets as JSON at keys under `__hmock_internal:template_sets:{setKey}`. Store the submitted raw mock definition arrays rather than validated `Behavior` objects so startup reloads use the current validation and inheritance pipeline.

Alternative considered: serialize effective `Behavior` objects. That would duplicate derived state and risk stale behavior when validation or rendering rules evolve.

### Source Merge Order

Load filesystem definitions first, then base API-managed definitions, then template sets in stable sorted set-key order. Feed the combined raw definition stream through the existing key replacement, template registration, inheritance, and action validation path so the existing duplicate-key rule remains authoritative.

Alternative considered: keep separate behavior lists per source and merge at request time. That would duplicate matching logic and make reusable templates/inheritance harder to reason about across sources.

### Admin Request Handling

Add an `AdminHTTPRequestHandler` with explicit routing for `/api/v1/health`, `/api/v1/templates`, `/api/v1/templates/{templateKey}`, and `/api/v1/template_sets/{setKey}`. Parse request bodies as JSON arrays of mock definitions, validate by attempting a runtime reload from the proposed persisted data, then commit to Redis only when validation succeeds.

Alternative considered: accept YAML over the admin API. The checkpoint specifies JSON responses and request bodies as mock objects, and JSON avoids adding another input encoding path.

### Reload Visibility

After each successful mutation, call a state reload method synchronously before returning the admin response. This satisfies the bounded eventual-reload requirement with the request duration as the bound and keeps tests deterministic.

Alternative considered: background polling. Polling would be simpler for external changes, but admin calls can provide stronger visibility with direct reload.

### Internal Redis Key Guard

Wrap the `redisDo` function exposed to templates with a validator that parses the command and rejects any key argument beginning with `__hmock_internal:` before dispatching to Redis. Internal persistence code should call the Redis store directly and bypass only this template-facing guard.

Alternative considered: block inside `RedisStore.do`. That would also block internal persistence, forcing special cases into both memory and external Redis stores.

## Risks / Trade-offs

- [Risk] JSON persistence values may exceed practical size for very large mock sets. → Mitigation: keep storage format compact and isolated so a future file or external backend can replace it without changing admin contracts.
- [Risk] Reload under lock can briefly block request handling when many mocks are submitted. → Mitigation: validate and build new behavior lists before swapping active state where practical, and keep the lock around the final swap.
- [Risk] External Redis may be unavailable during startup or admin writes. → Mitigation: surface startup errors through existing validation/error paths and return admin failures without partially committing invalid state.
- [Risk] Key parsing for Redis commands can miss unsupported future commands. → Mitigation: base the guard on `_parse_redis_command`, so supported commands have one parsing path and unsupported commands already fail before execution.

## Migration Plan

1. Extend configuration with admin defaults while preserving all existing mock server defaults.
2. Add persistence and reload support in `hmock.py` without changing filesystem-only behavior.
3. Add the admin server and start it from `main` only when enabled.
4. Add tests for default disabled/enabled behavior, endpoint responses, persistence across runtime rebuilds, template-set isolation, reload visibility, and reserved keyspace blocking.
5. Rollback by disabling `HM_ADMIN_HTTP_ENABLED`; persisted internal keys can remain unused without affecting filesystem-loaded mocks.

## Open Questions

- None.
