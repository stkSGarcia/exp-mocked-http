## Why

The mock server currently loads templates only from the filesystem at startup, making it impossible to add or remove mocks without restarting the process. An admin API with persistent storage enables dynamic mock management—critical for test orchestration where suites need to inject or clean up mocks programmatically across restarts.

## What Changes

- Add a separate admin HTTP server (default port 9998) controllable via environment variables.
- Add REST endpoints to list, add/update, and delete mocks at runtime.
- Add template-set endpoints to manage named groups of mocks independently.
- Persist API-added mocks and template sets so they survive process restarts.
- Merge persisted mocks with filesystem mocks on startup (last-loaded wins on key conflict).
- Block `redisDo` from touching the internal keyspace `__hmock_internal:*`.

## Capabilities

### New Capabilities

- `admin-api`: REST admin server with health, template CRUD, and template-set CRUD endpoints.
- `persistent-storage`: Persist API-added mocks and template sets across restarts via an internal Redis keyspace.

### Modified Capabilities

- `redis-state`: Block `redisDo` from writing to the reserved `__hmock_internal:*` keyspace.

## Impact

- **Code**: `hmock.py` — new admin server startup, new route handlers, storage layer for Redis-backed persistence.
- **APIs**: New admin API surface on a separate port; no changes to the existing mock-serving port.
- **Dependencies**: No new dependencies; uses the existing Redis connection.
- **Configuration**: Three new environment variables (`HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, `HM_ADMIN_HTTP_HOST`).
