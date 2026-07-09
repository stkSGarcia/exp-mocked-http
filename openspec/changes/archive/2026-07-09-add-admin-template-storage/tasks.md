## 1. Runtime Configuration And State

- [x] 1.1 Extend `Config` and `load_config` in `hmock.py` with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST`, preserving current mock-server defaults. [extends mock-definition-loading/add-stateful-actions]
- [x] 1.2 Add tests in `tests/test_hmock.py` for admin config defaults, overrides, and disabled mode. [extends mock-definition-loading/add-stateful-actions]
- [x] 1.3 Introduce a shared runtime state helper in `hmock.py` that owns the logger, Redis store, active behaviors, and reload lock.

## 2. Persistent Template Loading

- [x] 2.1 Refactor `hmock.py` mock loading so filesystem YAML, API-added base definitions, and template-set definitions can be merged as raw definitions before validation. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 2.2 Add persistence helpers in `hmock.py` for `__hmock_internal:templates` and deterministic `__hmock_internal:template_sets:<setKey>` JSON storage.
- [x] 2.3 Implement startup loading and post-mutation reload so persisted definitions merge with filesystem mocks using last-loaded-wins precedence. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 2.4 Add tests in `tests/test_hmock.py` for persisted base templates surviving rebuild, template sets staying isolated, and duplicate keys honoring last-loaded-wins.
- [x] 2.5 Add tests in `tests/test_hmock.py` proving invalid persisted definitions are not served and invalid admin submissions are not persisted.

## 3. Admin HTTP API

- [x] 3.1 Add `AdminHTTPRequestHandler` and `HMockAdminHTTPServer` in `hmock.py` using `BaseHTTPRequestHandler`/`ThreadingHTTPServer` alongside the existing mock server. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 3.2 Implement `GET /api/v1/health` and JSON response helpers in `hmock.py`. [extends admin-template-api]
- [x] 3.3 Implement `GET /api/v1/templates` to return the current active mock objects from filesystem and persisted sources. [extends admin-template-api]
- [x] 3.4 Implement `POST /api/v1/templates`, `DELETE /api/v1/templates`, and `DELETE /api/v1/templates/{templateKey}` with validation, persistence, filesystem preservation, status codes, and reload visibility. [extends admin-template-api]
- [x] 3.5 Implement `POST /api/v1/template_sets/{setKey}` and `DELETE /api/v1/template_sets/{setKey}` with full-set replacement, set-key isolation, status codes, and reload visibility. [extends admin-template-api]
- [x] 3.6 Update `main()` and server builders in `hmock.py` so the admin server starts in a daemon thread when enabled and shuts down cleanly with the foreground mock server.
- [x] 3.7 Add admin endpoint tests in `tests/test_hmock.py` for health, list, upsert, delete-all, delete-one, missing delete, set replace, set delete, and post-mutation mock visibility.

## 4. Reserved Redis Keyspace

- [x] 4.1 Add a Redis command key-inspection helper in `hmock.py` that rejects any user-visible command targeting `__hmock_internal:*`. [extends template-rendering/add-stateful-actions]
- [x] 4.2 Wrap `redisDo` and rendered `redis` action execution in `hmock.py` so blocked internal-keyspace calls raise `RedisError` before backend execution while persistence helpers can still use reserved keys. [extends template-rendering/add-stateful-actions]
- [x] 4.3 Add tests in `tests/test_hmock.py` proving `redisDo` blocks `__hmock_internal:templates` and template-set keys as render errors without executing commands, while non-internal keys still work. [extends template-rendering/add-stateful-actions]

## 5. Verification

- [x] 5.1 Run `uv run ruff check hmock.py tests/test_hmock.py` and fix reported issues.
- [x] 5.2 Run `uv run pytest tests/test_hmock.py` and fix failing coverage for the new admin/persistence behavior.
- [x] 5.3 Run `openspec status --change add-admin-template-storage` and confirm all required proposal artifacts are complete.
