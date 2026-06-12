## 1. Configuration and Runtime State

- [x] 1.1 Extend `Config` and `load_config` with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` defaults and overrides.
- [x] 1.2 Introduce a shared runtime/state object that can be used by both the mock HTTP server and the admin HTTP server.
- [x] 1.3 Update server startup and shutdown wiring to optionally run the admin HTTP server on its configured host and port.
- [x] 1.4 Add configuration tests for admin defaults, overrides, and disabled admin server behavior.

## 2. Persistent Mock Store

- [x] 2.1 Add persistence helpers for base API-added mocks under `__hmock_internal:templates`.
- [x] 2.2 Add persistence helpers for template sets under a reserved `__hmock_internal:*` template-set key prefix.
- [x] 2.3 Store and load JSON arrays of mock definitions while preserving submitted definition order within each collection.
- [x] 2.4 Add tests for base mock persistence, template-set persistence, set replacement, and set deletion isolation.

## 3. Active Definition Reload

- [x] 3.1 Refactor mock loading so filesystem definitions, persisted base API mocks, and persisted template sets can be merged through one validation path.
- [x] 3.2 Apply deterministic load order: filesystem mocks, base API-added mocks, then template sets in lexicographic set-key order.
- [x] 3.3 Preserve the existing duplicate-key rule so the last loaded definition wins across filesystem, base API, and template-set sources.
- [x] 3.4 Trigger or schedule active-set reload after every successful mutating admin request.
- [x] 3.5 Add tests proving startup loads persisted mocks and admin mutations become visible within the reload window.

## 4. Admin API Endpoints

- [x] 4.1 Implement `GET /api/v1/health` with `200 OK` and body `{"status":"OK"}`.
- [x] 4.2 Implement `GET /api/v1/templates` returning every active mock definition as a JSON array.
- [x] 4.3 Implement `POST /api/v1/templates` to validate, add or update, persist, and echo submitted base API mocks.
- [x] 4.4 Implement `DELETE /api/v1/templates` to clear only base API-added mocks and return `204 No Content`.
- [x] 4.5 Implement `DELETE /api/v1/templates/{templateKey}` with `204 No Content` for persisted base mock deletion and `404 Not Found` for missing keys.
- [x] 4.6 Implement `POST /api/v1/template_sets/{setKey}` to validate and replace the full named template set.
- [x] 4.7 Implement `DELETE /api/v1/template_sets/{setKey}` to delete only the named template set.
- [x] 4.8 Add endpoint tests for success responses, validation errors, not-found deletion, and isolation between filesystem mocks, base API mocks, and template sets.

## 5. Reserved Redis Keyspace Protection

- [x] 5.1 Add `redisDo` keyspace validation that rejects commands targeting `__hmock_internal:*` before execution.
- [x] 5.2 Ensure blocked `redisDo` calls surface as template render errors in conditions, response bodies, headers, and nested template contexts.
- [x] 5.3 Add tests proving internal keys are blocked and non-internal Redis keys still work.

## 6. End-to-End Verification

- [x] 6.1 Add an end-to-end test that creates a base API mock through the admin API and then matches it through the mock server.
- [x] 6.2 Add an end-to-end test that persists admin-created mocks, restarts/rebuilds the server, and verifies they are loaded.
- [x] 6.3 Add an end-to-end test that template-set deletion leaves other sets and base API mocks active.
- [x] 6.4 Run the full test suite with `uv run --with pytest pytest`.
