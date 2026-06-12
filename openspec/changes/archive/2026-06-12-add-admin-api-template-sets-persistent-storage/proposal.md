## Why

Runtime tests need to add, replace, and remove mocks without rebuilding template files or restarting the mock server. An admin API with persisted API-added templates and isolated template sets makes dynamic mock setup repeatable across process restarts while preserving the existing filesystem mock workflow.

## What Changes

- Add an optional admin HTTP server controlled by `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST`.
- Add admin endpoints for health checks and CRUD operations over API-added mock definitions.
- Add named template-set endpoints that store isolated groups of mocks separately from the base template collection.
- Persist API-added base mocks and template sets so they are loaded on startup and survive process restarts.
- Merge filesystem-loaded mocks, persisted base mocks, and template sets into one active mock set using the existing duplicate-key rule.
- Reserve the internal Redis keyspace `__hmock_internal:*` so template-level Redis calls cannot read or mutate admin storage.
- Make admin mutations visible to later mock requests within a bounded eventual-reload window.

## Capabilities

### New Capabilities
- `admin-http-api`: Admin HTTP server configuration, health endpoint, template CRUD endpoints, template-set endpoints, persistence semantics, and reload visibility.

### Modified Capabilities
- `mock-definition-loading`: Load persisted API-added mocks and template sets alongside filesystem mocks, merge them with last-loaded-wins behavior, and validate submitted definitions before persistence.
- `http-behavior-mocking`: Serve requests from the active mock set after admin mutations become visible within the reload window.
- `template-rendering`: Block `redisDo` access to the internal `__hmock_internal:*` keyspace and fail blocked calls as render errors.

## Impact

- Affected code: `hmock.py` configuration, server startup, request handler routing, mock loading and merging, Redis adapter access checks, persistence helpers, and tests.
- APIs: adds admin HTTP endpoints under `/api/v1`.
- Runtime systems: uses the configured Redis backend for internal persistence keys while preventing templates from accessing that keyspace.
- Compatibility: filesystem-loaded mocks remain supported and are not deleted by admin operations.
