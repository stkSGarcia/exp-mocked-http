## 1. Configuration And Runtime State

- [x] 1.1 Extend `Config` and `load_config` in `hmock.py` with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` defaults. [extends http-behavior-mocking/add-http-yaml-mock-server]
- [x] 1.2 Add an `HMockRuntimeState` in `hmock.py` that owns the logger, Redis store, templates directory, active behaviors, and a lock for reload/swap operations. [extends http-behavior-mocking/add-http-yaml-mock-server]
- [x] 1.3 Update `HMockHTTPServer`, `MockHTTPRequestHandler`, `build_server`, and `main` in `hmock.py` to read active behaviors from runtime state while preserving existing mock server behavior. [extends http-behavior-mocking/add-http-yaml-mock-server]

## 2. Persistent Definition Store

- [x] 2.1 Add persistence helpers in `hmock.py` for base API-managed mocks at `__hmock_internal:templates` and template sets under `__hmock_internal:template_sets:{setKey}`. [extends http-behavior-mocking/add-stateful-actions]
- [x] 2.2 Refactor `load_behaviors` in `hmock.py` so filesystem definitions, persisted base definitions, and persisted template-set definitions can share the existing validation, inheritance, template registration, and duplicate-key replacement path. [extends http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering]
- [x] 2.3 Implement startup loading and post-mutation reload so persisted API-managed mocks survive runtime rebuilds and become active after successful admin writes. [extends mock-definition-loading]

## 3. Admin HTTP API

- [x] 3.1 Add `AdminHTTPRequestHandler` and an admin server builder in `hmock.py` with explicit routing for `GET /api/v1/health`. [extends admin-template-management]
- [x] 3.2 Implement `GET /api/v1/templates` in `hmock.py` to return the active mock definition set, including filesystem definitions, base API-managed definitions, and template-set definitions. [extends admin-template-management]
- [x] 3.3 Implement `POST /api/v1/templates` in `hmock.py` to validate, persist, reload, and return submitted base API-managed mocks or return `400 Bad Request` with an error message. [extends admin-template-management]
- [x] 3.4 Implement `DELETE /api/v1/templates` and `DELETE /api/v1/templates/{templateKey}` in `hmock.py`, including `404 Not Found` for missing persistent base keys. [extends admin-template-management]
- [x] 3.5 Implement `POST /api/v1/template_sets/{setKey}` and `DELETE /api/v1/template_sets/{setKey}` in `hmock.py` with set-key isolation and synchronous reload after successful mutations. [extends admin-template-management]
- [x] 3.6 Start and stop the admin server from `main` when `HM_ADMIN_HTTP_ENABLED` is true, without changing mock server startup when admin is disabled. [extends admin-template-management]

## 4. Reserved Redis Keyspace

- [x] 4.1 Add a template-facing Redis command guard in `hmock.py` that rejects `redisDo` commands targeting `__hmock_internal:*` before command execution. [extends template-rendering]
- [x] 4.2 Use the guarded `redisDo` in `find_behavior`, `execute_behavior`, rendered Redis action items, and rendered outbound HTTP/response fields while allowing internal persistence helpers to call Redis directly. [extends http-behavior-mocking/add-stateful-actions]

## 5. Tests

- [x] 5.1 Add `tests/test_hmock.py` coverage for admin config defaults, overrides, and disabled admin behavior.
- [x] 5.2 Add `tests/test_hmock.py` coverage for admin health, template listing, base template create/update/delete, validation failures, and reload visibility.
- [x] 5.3 Add `tests/test_hmock.py` coverage for template-set create/replace/delete, set isolation, startup load from persistence, and duplicate-key last-loaded behavior.
- [x] 5.4 Add `tests/test_hmock.py` coverage proving `redisDo` fails for `__hmock_internal:templates` and template-set keys without executing the command, while non-internal keys still work.
- [x] 5.5 Run the focused test suite with `uv run pytest tests/test_hmock.py` and fix failures.
