## 1. Configuration and Runtime State

- [x] 1.1 Update `hmock.py` `Config` and `load_config` with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` defaults. [extends mock-definition-loading/add-stateful-actions]
- [x] 1.2 Add tests in `tests/test_hmock.py` for admin configuration defaults, overrides, and disabled startup behavior.
- [x] 1.3 Add an `ActiveMockRegistry` in `hmock.py` that can load filesystem mocks, persisted API-added base mocks, and persisted template sets into a lock-protected active behavior snapshot. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 1.4 Update `HMockHTTPServer` and `build_server` in `hmock.py` to read behaviors from the registry snapshot while preserving existing mock request behavior.

## 2. Internal Persistence

- [x] 2.1 Add internal storage helpers in `hmock.py` for `__hmock_internal:templates` and `__hmock_internal:template_sets:{setKey}` using the existing `RedisStore` abstraction. [extends template-rendering/add-stateful-actions]
- [x] 2.2 Implement canonical JSON serialization and deserialization for stored mock definition arrays, with validation before activation.
- [x] 2.3 Implement base API template upsert, delete-all, and delete-one operations on the registry with synchronous snapshot rebuilds. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 2.4 Implement template-set create/replace and delete operations on the registry with per-set isolation and synchronous snapshot rebuilds. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 2.5 Add persistence tests in `tests/test_hmock.py` for startup loading, duplicate-key last-loaded-wins behavior, base deletion isolation, template-set deletion isolation, and reload visibility.

## 3. Admin HTTP API

- [x] 3.1 Add `AdminHTTPRequestHandler` and `HMockAdminServer` in `hmock.py` as a separate listener from `MockHTTPRequestHandler`.
- [x] 3.2 Implement `GET /api/v1/health` returning `200 OK` with `{"status":"OK"}`.
- [x] 3.3 Implement `GET /api/v1/templates` returning a JSON array of active mock objects from filesystem and API-added sources.
- [x] 3.4 Implement `POST /api/v1/templates` with JSON parsing, mock validation, persistence, reload, `400 Bad Request` on validation failure, and `200 OK` with submitted mocks on success.
- [x] 3.5 Implement `DELETE /api/v1/templates` and `DELETE /api/v1/templates/{templateKey}` with required source isolation and `404 Not Found` for missing persisted keys.
- [x] 3.6 Implement `POST /api/v1/template_sets/{setKey}` and `DELETE /api/v1/template_sets/{setKey}` with full-set replacement and isolated deletion.
- [x] 3.7 Update `main()` in `hmock.py` to start and stop the admin server when enabled while keeping existing mock server startup intact. [extends mock-definition-loading/add-stateful-actions]
- [x] 3.8 Add admin endpoint tests in `tests/test_hmock.py` covering success responses, validation errors, not-found deletes, and listener disabled behavior.

## 4. Internal Redis Keyspace Guard

- [x] 4.1 Add Redis command key-position detection in `hmock.py` for all supported commands parsed by `_parse_redis_command`.
- [x] 4.2 Block any command targeting keys matching `__hmock_internal:*` before execution in both memory and external Redis paths. [extends template-rendering/add-stateful-actions]
- [x] 4.3 Ensure blocked internal-key access raises a template render error path and never mutates storage.
- [x] 4.4 Add tests in `tests/test_hmock.py` for `redisDo` and rendered `redis` action items against `__hmock_internal:templates` and template-set storage keys.

## 5. Verification

- [x] 5.1 Run `uv run pytest` and fix any regressions.
- [x] 5.2 Run focused admin API smoke tests against a real `HMockAdminServer` instance using the existing test request helper.
- [x] 5.3 Confirm `openspec status --change add-admin-api-template-storage` reports all proposal artifacts complete before apply.
