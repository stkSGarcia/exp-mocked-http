## Why

Runtime tests need a way to add, inspect, and remove mocks without rewriting files under the templates directory or restarting the service. This change adds an admin API and persistent API-managed storage so externally supplied mocks and template sets survive restarts while staying isolated from filesystem definitions.

## Related Work

### Related Changes

- `add-http-yaml-mock-server`: introduced the file-backed HTTP mock server and its YAML loading model; this change complements it by adding a separate admin surface for runtime-managed definitions.
- `add-template-helpers-file-backed-bodies`: expanded mock definition expressiveness through reusable templates and file-backed bodies; this change preserves those validation and rendering behaviors for API-added definitions.
- `add-stateful-actions`: added Redis-backed state and template-side Redis access; this change builds on that by reserving an internal Redis keyspace for persisted admin data.

### Related Specs

- `http-behavior-mocking/add-http-yaml-mock-server`: defines the HTTP mock server entry point and request serving behavior; this change keeps the mock server behavior intact while adding a separate admin server.
- `http-behavior-mocking/add-stateful-actions`: defines Redis-backed action execution behavior; this change reuses Redis as the persistence mechanism but blocks template access to internal storage keys.
- `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`: defines inheritance, reusable templates, and stable action ordering; this change requires API-added definitions and template sets to participate in the same effective mock set semantics.

## What Changes

- Add an optional admin HTTP server controlled by `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST`.
- Add admin endpoints to health check, list active mock definitions, create or update base API-added mocks, and delete base API-added mocks.
- Add named template-set endpoints that create, replace, and delete isolated groups of API-added mocks.
- Persist API-added base templates and template sets so they load on process startup and merge with filesystem-loaded definitions.
- Preserve the existing duplicate-key rule where the last loaded definition wins.
- Block `redisDo` from accessing the internal `__hmock_internal:*` keyspace, including base template and template-set persistence keys.
- Make admin mutations visible to later mock requests within a bounded eventual-reload window.

## Capabilities

### New Capabilities

- `admin-template-management`: Defines the admin HTTP API for health, active-template listing, base API-added mock mutation, template-set mutation, persistence, and reload visibility.

### Modified Capabilities

- `mock-definition-loading`: Adds persisted API-managed sources and template-set merge behavior to the existing filesystem loading and duplicate-key semantics.
- `template-rendering`: Adds reserved Redis keyspace protection for `redisDo` calls.

## Impact

- Affected APIs: new admin HTTP endpoints under `/api/v1`.
- Affected configuration: new admin server environment variables with documented defaults.
- Affected storage: Redis/internal persistence keys under `__hmock_internal:*`.
- Affected runtime behavior: mock loading merges filesystem definitions with persisted API-managed definitions and reloads after admin mutations.
- Affected template behavior: `redisDo` calls targeting the internal keyspace fail as render errors before executing a Redis command.
