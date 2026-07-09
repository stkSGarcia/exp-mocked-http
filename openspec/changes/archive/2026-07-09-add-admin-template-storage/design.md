## Context

`hmock.py` currently owns configuration, mock definition loading, template rendering, Redis access, the mock HTTP server, and the CLI entry point. Mock definitions are loaded from YAML files at startup into a static `HMockHTTPServer.behaviors` list, while `redisDo` and `redis` actions share the configured `RedisStore`.

This change adds runtime-administered mock definitions, so the active behavior set can no longer be treated as filesystem-only startup state. The implementation should preserve the compact single-file shape while adding clear helper boundaries for persistent raw definitions, active behavior rebuilds, and admin request handling.

## Related Work

**`mock-definition-loading/add-stateful-actions`**: Defines runtime configuration from environment variables with documented defaults. This informs adding admin config fields to `Config` and `load_config` because the existing server configuration already follows environment-default semantics.

**`http-behavior-mocking/add-stateful-actions`**: Defines selected behavior action execution order. This informs reusing existing `Behavior` validation/execution paths because API-added mocks must behave like filesystem mocks once active.

**`http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`**: Defines stable ascending action ordering for reusable/inherited mocks. This informs loading persisted raw definitions before validation rather than constructing behaviors by hand because ordering belongs in the existing validation pipeline.

**`mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`**: Defines `Template` definitions as named reusable fragments. This informs storing raw submitted definitions and rebuilding templates from the merged definition set because API mocks and sets may include reusable templates.

**`mock-definition-loading/add-http-yaml-mock-server`**: Defines filesystem loading and server defaults. This informs keeping filesystem discovery as the first source in the merge and adding the admin server beside the mock server because persisted mocks extend, not replace, file-backed startup loading.

**`template-rendering/add-reusable-templates-inheritance-values-action-ordering`**: Defines named reusable template rendering. This informs the active-set rebuild because persisted templates must populate the same `templates` map as filesystem templates.

**`template-rendering/add-stateful-actions`**: Defines `redisDo` availability and Redis render errors. This informs wrapping Redis calls with internal-keyspace validation because the persistence store shares the Redis backend used by templates.

**`http-behavior-mocking/add-template-helpers-file-backed-bodies`**: Defines richer body rendering and file-backed response behavior. This informs validating API-added raw definitions through the existing behavior validator so rendering remains consistent.

**`structured-http-logging/add-http-yaml-mock-server`**: Defines structured JSON logs. This informs logging admin startup, mutation success, and mutation failure through `JsonLogger`.

## Goals / Non-Goals

**Goals:**
- Add an admin HTTP server controlled by `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST`.
- Persist API-added base templates and named template sets under reserved Redis keys.
- Rebuild the active behavior list from filesystem definitions plus persisted definitions after successful admin mutations.
- Keep all admin-submitted definitions on the same validation/rendering/execution path as filesystem definitions.
- Block template-level Redis access to `__hmock_internal:*` before any Redis command executes.

**Non-Goals:**
- Add authentication or authorization for the admin API.
- Introduce a web framework or background worker dependency.
- Change the YAML file format or existing filesystem mock precedence outside the required persisted-source merge.
- Add partial update endpoints for template sets.

## Decisions

### Store raw definitions as JSON in reserved Redis keys

Persist base API-added definitions at `__hmock_internal:templates` and template sets at keys derived from `__hmock_internal:template_sets:<setKey>`. Store each value as compact JSON containing the submitted mock definition array. This keeps persistence compatible with both `MemoryRedisStore` and `ExternalRedisStore` through the existing `GET`, `SET`, `DEL`, and `KEYS` command surface _(see `mock-definition-loading/add-stateful-actions`)_.

Alternative considered: add a separate filesystem persistence directory. That would be easier to inspect manually, but it would bypass the existing Redis stateful capability and introduce another state backend to configure.

### Rebuild active behaviors through raw definition merge helpers

Split loading into helpers that produce raw definitions from filesystem YAML, persisted base definitions, and persisted template sets, then pass the merged raw definitions through existing definition validation, inheritance resolution, template extraction, and action sorting. Filesystem definitions load first, persisted base definitions load after them, and template sets load after base definitions in deterministic set-key order so the existing last-loaded-wins duplicate-key rule remains explicit _(see `mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`)_.

Alternative considered: append API-added `Behavior` objects directly to `server.behaviors`. That would avoid refactoring `load_behaviors`, but it would duplicate validation and miss `Template`/`AbstractBehavior` interactions.

### Share mutable runtime state between mock and admin servers

Introduce a small runtime state object containing the config, logger, Redis store, a lock, and the current behavior list. `HMockHTTPServer` reads behaviors from that state for each request; the admin server mutates persistent storage and immediately rebuilds the state under the same lock. This provides bounded reload visibility without polling: a successful admin mutation makes the new set visible as soon as the request completes _(see `admin-template-api`)_.

Alternative considered: run a periodic reload loop. That would satisfy eventual visibility, but immediate reload is simpler and gives a tighter bound.

### Implement admin API with `BaseHTTPRequestHandler`

Add `AdminHTTPRequestHandler` and `HMockAdminHTTPServer` alongside the existing mock HTTP handler. Reuse local JSON response helpers and the same `ThreadingHTTPServer` base. `main()` starts the admin server in a daemon thread when enabled and keeps the mock server as the foreground server _(see `mock-definition-loading/add-http-yaml-mock-server`)_.

Alternative considered: route admin endpoints through the mock server. Separate listeners match the requested admin host/port config and avoid collisions with user-defined mock paths.

### Guard internal Redis keys at command parsing time

Add a helper that parses Redis commands once, identifies command key positions for supported commands, and rejects any key matching `__hmock_internal:*`. Use it in the `redisDo` callable exposed to templates and in rendered `redis` action execution so internal storage is protected before any backend call. Rejections raise `RedisError`, which already behaves as a template render error in request handling _(see `template-rendering/add-stateful-actions`)_.

Alternative considered: block inside each Redis store implementation. A wrapper keeps the persistence helpers able to access internal keys while blocking only template/user commands.

## Risks / Trade-offs

- Persisted invalid JSON or stale schema data could prevent a clean active reload -> Treat invalid persisted records as validation failures, log a structured error, and keep the previous active behavior list during admin-request reload failures.
- `KEYS __hmock_internal:template_sets:*` may be inefficient on large external Redis instances -> The keyspace is narrow and admin reload is bounded to mutation/startup paths; document this as an implementation trade-off.
- Lack of admin authentication exposes powerful mutation endpoints -> Keep auth out of scope for this checkpoint but isolate the admin listener with host/port configuration.
- Immediate reload means mutating requests pay validation cost -> The mock set is expected to be small enough for synchronous validation, and this provides the tightest reload visibility.

## Migration Plan

1. Add config defaults and runtime-state helpers without changing existing mock-server behavior.
2. Add persistence helpers and startup merge with empty-store behavior matching the current filesystem-only state.
3. Add admin endpoints and mutation-triggered reloads.
4. Add reserved-key guards around user-visible Redis execution.
5. Roll back by disabling the admin listener with `HM_ADMIN_HTTP_ENABLED=false`; persisted keys remain inert if no admin server writes them.

## Open Questions

- Should invalid persisted definitions fail process startup or be logged and skipped? The current design skips invalid persisted definitions during startup but preserves the previous active list during admin reload failure.
- Should `setKey` accept any non-empty path segment or a stricter identifier pattern? The initial implementation should reject empty or slash-containing keys because the endpoint shape treats `setKey` as one path segment.
