## 1. Configuration and Runtime State

- [x] 1.1 Extend `Config` and `load_config` with `HM_ADMIN_HTTP_ENABLED=true`, `HM_ADMIN_HTTP_PORT=9998`, and `HM_ADMIN_HTTP_HOST=0.0.0.0`.
- [x] 1.2 Add tests for admin config defaults, overrides, and disabled admin server parsing.
- [x] 1.3 Introduce a shared runtime state object that holds config, logger, Redis store, active behaviors, active raw definitions, and a lock for reload-safe access.
- [x] 1.4 Update mock server construction and request handling to read active behaviors from the shared runtime state instead of a fixed server-local list.

## 2. Persistent Definition Storage

- [x] 2.1 Add internal persistence helpers for base API-added definitions at `__hmock_internal:templates` and template sets at `__hmock_internal:template_sets:<setKey>`.
- [x] 2.2 Store and load each persisted collection as ordered JSON arrays of mock definition objects.
- [x] 2.3 Add helpers to list, read, replace, and delete persisted template sets while keeping sets isolated by `setKey`.
- [x] 2.4 Add tests proving base API-added mocks and multiple template sets survive reload from the same Redis store.
- [x] 2.5 Add tests proving deleting one template set does not alter other template sets.

## 3. Loading, Validation, and Reload

- [x] 3.1 Refactor loading so filesystem definitions, persisted base definitions, and persisted template-set definitions can be merged into one candidate active set.
- [x] 3.2 Preserve filesystem discovery order, merge persisted base definitions after filesystem definitions, and merge template sets after base definitions in deterministic set-key order.
- [x] 3.3 Reuse existing schema validation, inheritance resolution, template registration, and duplicate-key replacement rules across the combined definition stream.
- [x] 3.4 Validate admin-submitted definitions against the full candidate active set before writing them to persistent storage.
- [x] 3.5 Reload the active snapshot synchronously under the runtime lock after every successful admin mutation.
- [x] 3.6 Add tests for persisted-source merge ordering, duplicate-key replacement across sources, duplicate-key warnings, and validation-before-persistence failures.

## 4. Admin HTTP API

- [x] 4.1 Implement a separate admin `ThreadingHTTPServer` that starts alongside the mock server only when admin HTTP is enabled.
- [x] 4.2 Implement `GET /api/v1/health` returning `200 OK` and `{"status":"OK"}`.
- [x] 4.3 Implement `GET /api/v1/templates` returning every active mock definition as a JSON array.
- [x] 4.4 Implement `POST /api/v1/templates` to validate, persist, reload, and return submitted base API-added definitions.
- [x] 4.5 Implement `DELETE /api/v1/templates` to clear only base API-added definitions, reload, and return `204 No Content`.
- [x] 4.6 Implement `DELETE /api/v1/templates/{templateKey}` to delete one base API-added mock, return `404 Not Found` when absent, and leave filesystem mocks with the same key intact.
- [x] 4.7 Implement `POST /api/v1/template_sets/{setKey}` to validate, replace, persist, reload, and return a full named template set.
- [x] 4.8 Implement `DELETE /api/v1/template_sets/{setKey}` to delete the named set without changing other sets and return `204 No Content`.
- [x] 4.9 Add admin API tests for every endpoint, success status, error status, response body, and filesystem/template-set deletion isolation rule.

## 5. Reserved Redis Keyspace

- [x] 5.1 Add command-aware detection for Redis commands targeting keys matching `__hmock_internal:*`.
- [x] 5.2 Block user-facing `redisDo` calls targeting the internal keyspace with a template render error before command execution.
- [x] 5.3 Block rendered `redis` action commands targeting the internal keyspace before command execution.
- [x] 5.4 Keep internal persistence helpers able to read and write reserved keys without going through the user-facing guard.
- [x] 5.5 Add tests proving blocked `redisDo` and blocked `redis` action calls fail as render errors and do not mutate internal storage.

## 6. End-to-End Verification

- [x] 6.1 Add an integration test proving an admin-added mock is visible to later mock requests after the reload window.
- [x] 6.2 Add an integration test proving an updated API mock replaces an earlier active mock according to the duplicate-key rule.
- [x] 6.3 Add an integration test proving a deleted API mock stops matching while a filesystem mock with the same key remains available.
- [x] 6.4 Add an integration test proving base API-added mocks and template-set mocks are loaded on startup from persistent storage.
- [x] 6.5 Run the full test suite with `uv run --with pytest pytest`.
