## Why

Runtime-created mocks currently cannot be managed through an API or survive a process restart, which makes dynamic test setup depend on filesystem writes and server restarts. Adding an admin API with persistent storage gives tests and operators a stable way to add, replace, list, and delete mocks while the mock server is running.

## What Changes

- Add a separately configurable admin HTTP server with health and template-management endpoints.
- Add endpoints to list all active mock definitions, add or update base API mocks, delete one API-persisted mock, and clear all base API mocks.
- Add named template sets that are persisted independently from the base template collection and can be replaced or deleted by set key.
- Load persisted base mocks and template sets on startup, merge them with filesystem mocks, and keep duplicate-key behavior as last loaded wins.
- Make admin mutations visible to subsequent mock requests within a bounded eventual-reload window.
- Block `redisDo` from executing commands against the reserved internal keyspace used for persisted admin-managed data.

## Capabilities

### New Capabilities
- `admin-http-api`: Defines the admin server configuration, health endpoint, template-management endpoints, template-set endpoints, mutation responses, and reload visibility contract.

### Modified Capabilities
- `mock-definition-loading`: Add persisted API mock loading, template-set isolation, startup merge behavior, and duplicate-key handling for persisted definitions.
- `template-rendering`: Prevent `redisDo` from touching the reserved `__hmock_internal:*` keyspace used by internal persistence.

## Impact

- Affected code: `hmock.py` configuration loading, server startup, active mock store/reload path, YAML validation reuse, Redis adapter usage, and tests.
- APIs: new admin HTTP endpoints on the configured admin host and port.
- Runtime systems: uses the configured Redis backend for internal persistence under reserved `__hmock_internal:*` keys.
- Compatibility: existing filesystem mocks and mock-server request behavior remain unchanged unless admin-managed mocks are added.
