## 1. Configuration and Runtime State

- [x] 1.1 Update `hmock.py` `Config` and `load_config` with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_HOST`, and `HM_ADMIN_HTTP_PORT`, including defaults and boolean parsing. [extends http-yaml-mock-server/add-http-yaml-mock-server]
- [x] 1.2 Refactor `hmock.py` definition assembly to return effective raw definitions, compiled behaviors, and named templates without mutating live globals during validation. [extends http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering]
- [x] 1.3 Add locked runtime snapshot and atomic install helpers in `hmock.py`, then update `MockRequestHandler` and named-template rendering to consume stable snapshots. [extends http-yaml-mock-server/add-http-yaml-mock-server]

## 2. Persistent Definition Collections

- [x] 2.1 Add `hmock.py` internal Redis persistence helpers for JSON base definitions at `__hmock_internal:templates` and isolated named sets in `__hmock_internal:template_sets`.
- [x] 2.2 Implement deterministic `hmock.py` source loading in filesystem, base API, and lexicographically ordered named-set order, preserving order inside each collection. [extends http-yaml-mock-server/add-http-yaml-mock-server]
- [x] 2.3 Load, validate, compile, and atomically install persisted definitions during `hmock.py` startup while treating missing internal records as empty.
- [x] 2.4 Implement candidate-state validation and synchronous reload helpers in `hmock.py` so failed mutations leave persistence and active state unchanged.

## 3. Admin HTTP API

- [x] 3.1 Add JSON request parsing and JSON/no-content/error response helpers plus an `AdminRequestHandler` in `hmock.py`.
- [x] 3.2 Implement `GET /api/v1/health` and `GET /api/v1/templates` in `hmock.py`, returning health JSON and effective winning definitions.
- [x] 3.3 Implement `POST /api/v1/templates`, `DELETE /api/v1/templates`, and `DELETE /api/v1/templates/{templateKey}` in `hmock.py` with validation, persistence isolation, status codes, and synchronous runtime reload.
- [x] 3.4 Implement `POST /api/v1/template_sets/{setKey}` and `DELETE /api/v1/template_sets/{setKey}` in `hmock.py` with full-set replacement, idempotent deletion, isolation, and synchronous runtime reload.
- [x] 3.5 Update `hmock.py` server construction and `main` lifecycle to start the configured admin `ThreadingHTTPServer` on a separate thread and close both listeners on shutdown. [extends http-yaml-mock-server/add-http-yaml-mock-server]

## 4. Reserved Redis Protection

- [x] 4.1 Add command-aware key and key-pattern extraction in `hmock.py` for every Redis command supported by `MemoryRedisBackend`.
- [x] 4.2 Reject `redisDo` commands targeting `__hmock_internal:*` before backend execution while leaving direct trusted persistence access available. [extends http-yaml-mock-server/add-template-helpers-file-backed-bodies]
- [x] 4.3 Add `test_hmock.py` coverage proving blocked direct keys, set keys, and `KEYS` patterns raise `TemplateRenderError` without invoking the Redis backend, while non-reserved commands still execute.

## 5. Verification

- [x] 5.1 Extend `test_hmock.py` configuration tests for admin defaults, overrides, invalid values, and disabled startup.
- [x] 5.2 Add `test_hmock.py` persistence and merge tests for restart loading, missing records, deterministic duplicate precedence, cross-source inheritance/templates, and file-backed validation. [extends http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering]
- [x] 5.3 Add `test_hmock.py` admin endpoint tests for health, active listing, base upsert/delete/error responses, named-set replace/delete, isolation, and atomic validation failure.
- [x] 5.4 Add `test_hmock.py` integration coverage showing successful mutations are visible to later mock requests by response completion and filesystem definitions survive API deletions.
- [x] 5.5 Run the complete project test suite and correct any regressions in existing YAML loading, template rendering, Redis actions, and HTTP request handling.
