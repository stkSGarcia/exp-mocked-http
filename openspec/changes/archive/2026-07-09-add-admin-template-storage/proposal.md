## Why

Operators need a runtime control surface for adding, replacing, and deleting mock definitions without editing files or restarting the mock server. Persisting API-added mocks and named template sets makes that control surface reliable across restarts while keeping filesystem mocks intact.

## What Changes

- Add an optional admin HTTP server, enabled by default, with environment-controlled host and port.
- Add health, template listing, template upsert, template delete, and template-set replacement/delete endpoints under `/api/v1`.
- Persist API-added base templates and named template sets separately, reload them into the active mock set, and preserve existing last-loaded-wins duplicate-key behavior.
- Keep filesystem-loaded mocks immutable from admin deletion operations.
- Block `redisDo` from executing commands against the internal `__hmock_internal:*` Redis keyspace and surface blocked calls as template render errors.
- Make admin mutations visible to subsequent mock requests within a bounded eventual-reload window.

## Capabilities

### New Capabilities
- `admin-template-api`: Admin HTTP endpoints for health checks, active template listing, base template upsert/delete, and template-set replace/delete operations.

### Modified Capabilities
- `mock-definition-loading`: Load persisted API-added base templates and named template sets on startup, merge them with filesystem mocks, and keep set storage isolated by set key.
- `template-rendering`: Prevent `redisDo` from touching internal persistence keys and fail blocked calls before any Redis command executes.

## Related Work

### Related Changes
- `add-reusable-templates-inheritance-values-action-ordering`: Introduced reusable mock fragments, inherited behavior, explicit values, and deterministic action ordering. This change complements that work by making reusable template collections manageable at runtime and persistent across restarts.
- `add-template-helpers-file-backed-bodies`: Expanded template helpers and file-backed payload support so mock definitions can stay readable while handling richer bodies. This change builds on that runtime templating surface by ensuring API-added mocks participate in the same active template set as file-loaded mocks.

### Related Specs
- `mock-definition-loading/add-stateful-actions`: Defines environment-based runtime configuration. This change reuses that configuration style for `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST`.
- `http-behavior-mocking/add-stateful-actions`: Defines ordered action execution and behavior selection. This change preserves those semantics for mocks that enter the system through the admin API.
- `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`: Defines stable ordered action execution for inherited/reusable templates. This change keeps API-loaded mocks compatible with the same ordering behavior.
- `mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`: Defines loading of reusable template definitions by key. This change extends loading to persisted base templates and named template sets.
- `mock-definition-loading/add-http-yaml-mock-server`: Defines initial server configuration and filesystem mock loading. This change adds an admin server alongside the existing mock server and merges persisted definitions with filesystem definitions.
- `template-rendering/add-reusable-templates-inheritance-values-action-ordering`: Defines named template rendering. This change keeps rendered output behavior consistent for persisted API-added mocks and sets.
- `template-rendering/add-stateful-actions`: Defines `redisDo` availability in template contexts. This change constrains `redisDo` by reserving the internal persistence keyspace.
- `http-behavior-mocking/add-template-helpers-file-backed-bodies`: Defines richer response-body templating behavior. This change ensures API-added mocks can use the same rendering and response behavior.
- `structured-http-logging/add-http-yaml-mock-server`: Defines structured JSON logs. This change should log admin server startup and mutation failures consistently with the existing logging approach.

## Impact

- Affected APIs: new admin HTTP API under `/api/v1`.
- Affected configuration: `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST`.
- Affected persistence: internal Redis keys under `__hmock_internal:*` for base templates and template sets.
- Affected runtime behavior: startup loading, active mock merging, bounded reload visibility after mutations, and template-rendering error behavior for blocked internal-keyspace `redisDo` calls.
