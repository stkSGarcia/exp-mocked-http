## 1. Configuration And State

- [x] 1.1 Extend `Config` and `load_config` with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` defaults and environment parsing.
- [x] 1.2 Add tests for admin configuration defaults, overrides, and disabled mode.
- [x] 1.3 Introduce a thread-safe mock state object that returns active behavior snapshots and can atomically replace active raw definitions and behaviors.
- [x] 1.4 Update `HMockHTTPServer` and request handling to read behaviors from the shared mock state for each request.

## 2. Persistent Storage And Loading

- [x] 2.1 Add storage helpers for base API-added mocks at `__hmock_internal:templates` using JSON arrays of raw mock definitions.
- [x] 2.2 Add storage helpers for template sets under `__hmock_internal:template_sets:<setKey>` with deterministic set-key listing and validation.
- [x] 2.3 Refactor mock loading so filesystem definitions, persisted base API definitions, and persisted template-set definitions flow through one validation and merge path.
- [x] 2.4 Preserve duplicate-key replacement semantics across filesystem definitions, base API definitions, and template-set definitions with deterministic load order.
- [x] 2.5 Add tests for persisted base mocks, persisted template sets, restart/reload behavior with the same backend, merge precedence, and template-set isolation.

## 3. Admin HTTP API

- [x] 3.1 Implement an admin `ThreadingHTTPServer` and request handler separate from the mock HTTP server.
- [x] 3.2 Implement `GET /api/v1/health` returning `200 OK` and `{"status":"OK"}`.
- [x] 3.3 Implement `GET /api/v1/templates` returning the active filesystem-loaded and API-added mock definitions as a JSON array.
- [x] 3.4 Implement `POST /api/v1/templates` to validate, upsert, persist, reload, and return submitted base API mock definitions.
- [x] 3.5 Implement `DELETE /api/v1/templates` to delete all base API-added mocks, reload, and return `204 No Content`.
- [x] 3.6 Implement `DELETE /api/v1/templates/{templateKey}` to delete one base API-added mock, preserve any filesystem mock with the same key, return `404 Not Found` when absent, and reload on success.
- [x] 3.7 Implement `POST /api/v1/template_sets/{setKey}` to validate, replace, persist, reload, and return the submitted set definitions.
- [x] 3.8 Implement `DELETE /api/v1/template_sets/{setKey}` to delete one set without affecting others, reload, and return `204 No Content`.
- [x] 3.9 Wire admin server startup and shutdown in `main()` and helper builders according to admin enablement.
- [x] 3.10 Add endpoint tests covering success responses, validation failures, deletion semantics, and post-mutation request visibility.

## 4. Reserved Redis Keyspace

- [x] 4.1 Add a command guard that identifies key arguments for all supported Redis commands and rejects keys or patterns matching `__hmock_internal:*`.
- [x] 4.2 Apply the guard to template-accessible `redisDo` calls before backend execution.
- [x] 4.3 Apply the guard to rendered `redis` action commands before backend execution.
- [x] 4.4 Add tests proving blocked calls fail as template render errors and do not execute, while non-internal keys still work.

## 5. Verification

- [x] 5.1 Run the focused admin, persistence, loading, and Redis guard tests.
- [x] 5.2 Run the full test suite with `uv run pytest`.
- [x] 5.3 Run OpenSpec status or validation for `add-admin-api-template-sets-persistent-mocks` and resolve any artifact issues.
