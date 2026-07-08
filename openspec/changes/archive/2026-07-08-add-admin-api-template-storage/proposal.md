## Why

Runtime mock management needs an HTTP admin surface so callers can add, replace, and delete mocks without editing filesystem fixtures or restarting the process. Those API-added mocks also need persistent storage and clear isolation rules so updates survive restarts without overwriting filesystem definitions or named template sets.

## What Changes

- Add a configurable admin HTTP server with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` defaults.
- Add health, template listing, template upsert, and template delete endpoints under `/api/v1`.
- Persist API-added base templates so they load on startup and merge with filesystem mocks using the existing last-loaded-wins duplicate-key behavior.
- Add named template-set storage under `/api/v1/template_sets/{setKey}` with create/replace and delete operations isolated by set key.
- Ensure mutating admin requests become visible to later mock-serving requests within a bounded eventual-reload window.
- Block `redisDo` from accessing the internal `__hmock_internal:*` Redis keyspace, including base template and template-set storage keys.

## Related Work

### Related Changes

- `add-reusable-templates-inheritance-values-action-ordering`: introduced reusable templates, inheritance, explicit values, and deterministic action ordering to reduce duplication across mock files. This change complements it by letting equivalent mock definitions be managed through an admin API and stored outside filesystem fixtures.
- `add-template-helpers-file-backed-bodies`: added richer template helpers and file-backed response bodies so mocks can stay readable while expressing larger payloads. This change keeps the same mock-definition shape available through the admin API while preserving validation and render behavior.

### Related Specs

- `mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`: defines reusable template registration and loading semantics. This change builds on that loader behavior by merging API-persisted templates into the active set without changing how filesystem templates are interpreted.
- `template-rendering/add-stateful-actions`: defines `redisDo` availability in template expression contexts. This change adapts that behavior by adding an internal Redis keyspace guard that fails blocked calls before execution.
- `http-behavior-mocking/add-template-helpers-file-backed-bodies`: defines file-backed body behavior for HTTP mock responses. This change reuses the existing mock object contract when returning and accepting template JSON through the admin API.
- `mock-definition-loading/add-stateful-actions`: defines environment-driven runtime configuration. This change adds admin-server configuration variables using the same defaulting model.
- `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`: defines stable action execution after reusable-template loading. This change preserves that runtime behavior after admin mutations trigger a reload.
- `mock-definition-loading/add-template-helpers-file-backed-bodies`: defines loader support for file-backed response content. This change relies on existing validation and loading rules when API-added mocks are merged into the active set.

## Capabilities

### New Capabilities

- `admin-http-api`: Admin HTTP server configuration and `/api/v1` health, template, and template-set endpoints.
- `api-template-persistence`: Persistent storage, startup loading, merge behavior, and delete behavior for API-added base templates.
- `template-set-storage`: Named template-set persistence with full-set replacement and isolated deletion.
- `internal-keyspace-protection`: Redis internal keyspace blocking for template-rendered `redisDo` calls.

### Modified Capabilities

- `mock-definition-loading`: Active mock loading includes persisted API-added mocks and keeps duplicate-key ordering semantics.
- `template-rendering`: `redisDo` fails as a template render error for `__hmock_internal:*` keys without executing the Redis command.

## Impact

- Adds an admin HTTP listener and request routing alongside the mock-serving runtime.
- Adds persistent storage for API-managed base templates and named template sets, likely backed by the existing Redis stateful action dependency.
- Touches mock definition validation/loading, active template reload, and render-time Redis command execution.
- Introduces new API behavior and tests for success, validation failure, deletion isolation, restart persistence, reload visibility, and blocked internal Redis access.
