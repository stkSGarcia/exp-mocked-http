## Why

Operators need to add, update, inspect, and remove mock definitions at runtime without editing template files or restarting the mock server. Persisting API-added mocks and template sets makes those runtime changes durable while keeping filesystem-loaded mocks as the baseline source.

## What Changes

- Add an optional admin HTTP server with environment-controlled enablement, host, and port.
- Add admin endpoints for health checks and base template listing, upsert, bulk delete, and single-key delete.
- Add named template-set endpoints that persist independent groups of mock definitions by set key.
- Persist API-added base templates and template sets across process restarts.
- Merge filesystem-loaded mocks, persisted base templates, and persisted template sets into one active mock set using the existing duplicate-key rule where the last loaded definition wins.
- Block `redisDo` from reading or mutating the reserved `__hmock_internal:*` keyspace used for internal persistence.
- Ensure admin mutations become visible to subsequent mock requests within a bounded eventual-reload window.

## Capabilities

### New Capabilities
- `admin-http-api`: Defines the admin server configuration and HTTP endpoints for health, base templates, and template sets.

### Modified Capabilities
- `mock-definition-loading`: Persist API-added base templates and template sets, load them on startup, merge them with filesystem mocks, isolate named sets, and make mutations visible through bounded reload.
- `template-rendering`: Prevent `redisDo` from touching the reserved internal Redis keyspace and fail blocked calls as template render errors.

## Impact

- Affects server startup/configuration, admin HTTP routing, mock definition validation/loading, reload coordination, Redis-backed persistence, and template rendering.
- Adds runtime API behavior on port `9998` by default when `HM_ADMIN_HTTP_ENABLED` is true.
- Requires tests covering admin endpoint status codes and payloads, persistence across restart/load cycles, merge precedence, template-set isolation, reserved key blocking, and reload visibility.
