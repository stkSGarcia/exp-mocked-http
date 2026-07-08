## Context

`hmock.py` currently loads YAML mock definitions from `HM_TEMPLATES_DIR`, validates them into active `Behavior` objects, and serves mock traffic through `HMockHTTPServer`. Stateful actions already use a `RedisStore` abstraction with `MemoryRedisStore` and `ExternalRedisStore`, and template rendering exposes `redisDo` directly to user-authored templates.

This change adds a second HTTP listener for runtime administration. Admin mutations must persist API-added mocks, rebuild the active mock set, and protect internal storage keys from user templates.

## Related Work

**`mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`**: Defines reusable template registration and loader validation — informs the decision to route admin-submitted definitions through the existing validation and merge pipeline because that prior work made loader behavior the source of truth for concrete behaviors, templates, inheritance, and duplicate keys.

**`template-rendering/add-stateful-actions`**: Defines `redisDo` availability in template expression contexts — informs the decision to guard internal keys inside the Redis execution path because all template contexts eventually call the same store operation.

**`http-behavior-mocking/add-template-helpers-file-backed-bodies`**: Defines file-backed HTTP response body behavior — informs the decision to accept and return the same mock object schema through the admin API because HTTP behavior mocking already owns response payload interpretation.

**`mock-definition-loading/add-stateful-actions`**: Defines environment-driven runtime configuration — informs the decision to extend `Config` and `load_config` for admin listener settings because runtime options already follow that pattern.

**`http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`**: Defines stable action execution after template inheritance — informs the decision to rebuild the same `Behavior` objects after admin mutations because request execution should not learn a separate admin-specific path.

**`mock-definition-loading/add-template-helpers-file-backed-bodies`**: Defines loader support for file-backed response content — informs the decision to keep admin validation coupled to loader rules because file-backed payloads need the same path-safety and snapshot behavior.

## Goals / Non-Goals

**Goals:**

- Add a configurable admin HTTP server with the specified `/api/v1` endpoints.
- Persist API-added base templates and named template sets under reserved internal storage keys.
- Reuse existing mock validation, inheritance, template registration, and action ordering behavior.
- Apply admin mutations to active request handling within a bounded reload window.
- Prevent `redisDo` from reading or writing `__hmock_internal:*`.

**Non-Goals:**

- Add authentication or authorization for the admin API.
- Change the public mock definition schema beyond accepting the same objects over HTTP.
- Add partial template-set patch operations.
- Expose internal persistence keys or storage layout through the admin API.

## Decisions

### Use a Separate Admin HTTP Server

Add `AdminHTTPRequestHandler` and `HMockAdminServer` instead of mixing admin routes into `MockHTTPRequestHandler`. The main server remains focused on mock traffic while the admin listener uses `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_HOST`, and `HM_ADMIN_HTTP_PORT`. `main()` starts the mock server and, when enabled, starts the admin server on a daemon thread with shared runtime state.

Alternative considered: Serve admin routes on the mock listener. That would reduce one socket but would make admin paths compete with user-defined mocks and complicate route precedence.

This follows the environment configuration pattern from `Config` and `load_config`. _(see `mock-definition-loading/add-stateful-actions`)_

### Introduce a Shared Runtime Registry

Replace the server's plain `behaviors` list with an `ActiveMockRegistry` that owns:

- filesystem definitions loaded from `HM_TEMPLATES_DIR`
- API-added base definitions loaded from storage
- template-set definitions loaded from storage
- a lock-protected active `Behavior` snapshot

Mock requests read the current snapshot without mutating it. Admin writes update storage and synchronously rebuild the snapshot before returning success, which bounds reload visibility to the request duration plus validation time.

Alternative considered: Let each mock request reload from storage. That would simplify freshness but add avoidable I/O and validation cost to every request.

The registry uses the existing loader and duplicate-key ordering rules so admin changes do not create a second interpretation of mocks. _(see `mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`)_

### Store Admin Definitions in Reserved Internal Keys

Persist base API-added definitions at `__hmock_internal:templates` and template sets under a deterministic prefix such as `__hmock_internal:template_sets:{setKey}`. Store each value as canonical JSON for the submitted mock definition array. The admin API owns these keys; user templates cannot access them.

Alternative considered: Store admin definitions as YAML files under `HM_TEMPLATES_DIR`. That would make persistence visible to users but would blur the line between filesystem mocks and API-added mocks, and deletion rules require those sources to stay separate.

This uses the existing Redis state abstraction for internal storage while keeping user-authored `redisDo` isolated from internal data. _(see `template-rendering/add-stateful-actions`)_

### Validate Admin Payloads Before Committing

Admin POST handlers parse the request body as a JSON array of mock objects, run the same definition validation path used by file loading, and only commit storage after validation succeeds. Invalid bodies return `400 Bad Request` and leave active state unchanged.

Alternative considered: Store first and rely on reload failure handling. That risks persisting invalid state and makes rollback ambiguous.

The same schema and file-backed body behavior stays authoritative for API and filesystem definitions. _(see `http-behavior-mocking/add-template-helpers-file-backed-bodies`)_

### Block Internal Redis Keys Before Execution

Centralize key extraction and internal-key checks near `_parse_redis_command` or `RedisStore.do` so both `MemoryRedisStore` and `ExternalRedisStore` reject commands before mutation. Commands with key positions matching `__hmock_internal:*` raise `RedisError`, which already surfaces as a template render error in request handling.

Alternative considered: Wrap only the `redisDo` function injected into template contexts. That would miss rendered `redis` action items and any future call sites that use the same store.

This preserves supported Redis commands for non-internal keys while adding a consistent deny rule. _(see `template-rendering/add-stateful-actions`)_

## Risks / Trade-offs

[Admin mutation races] -> Protect storage writes and active snapshot rebuilds with one registry lock, and publish a complete snapshot only after validation succeeds.

[External Redis persistence assumptions] -> Document that durable restart persistence requires a durable Redis backend; tests can exercise the storage contract through the shared store abstraction.

[Invalid persisted data from older versions] -> On startup, validate persisted definitions before activation and log validation failures clearly.

[Internal key matching gaps] -> Add tests for each supported Redis command family and for both direct `redisDo` usage and rendered `redis` action items.

## Migration Plan

1. Extend `Config` with admin listener settings and keep defaults backward compatible.
2. Add internal storage helpers and registry rebuild behavior behind the existing server construction path.
3. Start the admin listener only when enabled.
4. Add endpoint and persistence tests, then add Redis keyspace guard tests.
5. Rollback by disabling `HM_ADMIN_HTTP_ENABLED`; existing filesystem mocks continue to load normally.

## Open Questions

- Should template sets always participate in the active mock set, or should a later checkpoint define selection/activation semantics per set?
- Should memory-backed storage be documented as non-durable across full process restarts, or should this change add a small file-backed internal store for the default configuration?
