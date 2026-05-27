## 1. Reserved Keyspace Guard in redisDo

- [x] 1.1 Add a prefix check in the `redisDo` wrapper: if the key argument starts with `__hmock_internal:`, raise a template render error without executing the Redis command
- [x] 1.2 Write tests for: blocked SET to `__hmock_internal:*`, blocked GET to `__hmock_internal:*`, normal keys unblocked

## 2. Persistent Storage Layer

- [x] 2.1 Implement `load_api_mocks()`: read `__hmock_internal:templates` from Redis and deserialize the JSON list (return empty list if key absent)
- [x] 2.2 Implement `save_api_mocks(mocks)`: serialize the mock list to JSON and write it to `__hmock_internal:templates`
- [x] 2.3 Implement `load_template_set(set_key)`: read `__hmock_internal:tset:<set_key>` and deserialize (return empty list if absent)
- [x] 2.4 Implement `save_template_set(set_key, mocks)`: serialize and write to `__hmock_internal:tset:<set_key>`
- [x] 2.5 Implement `delete_template_set(set_key)`: delete `__hmock_internal:tset:<set_key>`
- [x] 2.6 Implement `list_template_set_keys()`: run `KEYS __hmock_internal:tset:*` and return the set keys sorted

## 3. Mock Set Reload

- [x] 3.1 Extract mock-set building into a `build_mock_set()` function: load filesystem mocks (sorted), then API base mocks, then each template set in key-sorted order; apply last-loaded-wins dedup
- [x] 3.2 Store the active mock set in a thread-safe atomic reference that the primary HTTP server reads on each request
- [x] 3.3 Add a background reload thread: every ≤1 s, call `build_mock_set()` and swap the atomic reference

## 4. Admin HTTP Server

- [x] 4.1 Read `HM_ADMIN_HTTP_ENABLED` (default `true`), `HM_ADMIN_HTTP_PORT` (default `9998`), `HM_ADMIN_HTTP_HOST` (default `0.0.0.0`) at startup
- [x] 4.2 When enabled, start the admin server in a separate daemon thread on the configured host/port
- [x] 4.3 Implement `GET /api/v1/health` → `200 {"status": "OK"}`
- [x] 4.4 Implement `GET /api/v1/templates` → `200` JSON array of all active mocks (filesystem + API)
- [x] 4.5 Implement `POST /api/v1/templates`: parse body, validate each mock, on error return `400` with message; on success call `save_api_mocks()` and return `200` with submitted mocks
- [x] 4.6 Implement `DELETE /api/v1/templates`: call `save_api_mocks([])` and return `204`
- [x] 4.7 Implement `DELETE /api/v1/templates/{templateKey}`: check that the key exists in the persistent store, return `404` if not; otherwise remove it from the stored list, call `save_api_mocks()`, and return `204`
- [x] 4.8 Implement `POST /api/v1/template_sets/{setKey}`: parse body, validate, call `save_template_set()`, return `200` with submitted mocks
- [x] 4.9 Implement `DELETE /api/v1/template_sets/{setKey}`: call `delete_template_set()`, return `204`

## 5. Startup Integration

- [x] 5.1 On startup, after Redis is initialized, call `build_mock_set()` to merge filesystem mocks + persisted API mocks + template sets into the initial active set
- [x] 5.2 Start the background reload thread after startup
- [x] 5.3 Start the admin server thread after startup (when enabled)

## 6. Tests

- [x] 6.1 Test `GET /api/v1/health` returns `200 {"status": "OK"}`
- [x] 6.2 Test `GET /api/v1/templates` returns all active mocks including filesystem and API mocks
- [x] 6.3 Test `POST /api/v1/templates` with valid mocks: mocks become active, persisted in Redis
- [x] 6.4 Test `POST /api/v1/templates` with invalid body returns `400`
- [x] 6.5 Test `DELETE /api/v1/templates` removes API mocks, leaves filesystem mocks and template sets
- [x] 6.6 Test `DELETE /api/v1/templates/{templateKey}` for existing key returns `204` and removes mock
- [x] 6.7 Test `DELETE /api/v1/templates/{templateKey}` for missing key returns `404`
- [x] 6.8 Test `POST /api/v1/template_sets/{setKey}` creates/replaces a set and mocks become active
- [x] 6.9 Test `DELETE /api/v1/template_sets/{setKey}` removes set; other sets unaffected
- [x] 6.10 Test that `redisDo` raises a render error when key starts with `__hmock_internal:`
- [x] 6.11 Test mock merge order: filesystem → API base → template sets (key-sorted), last wins on conflict
- [x] 6.12 Test admin server does not start when `HM_ADMIN_HTTP_ENABLED=false`
