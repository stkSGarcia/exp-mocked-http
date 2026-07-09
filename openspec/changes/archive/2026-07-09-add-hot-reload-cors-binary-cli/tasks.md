## 1. Configuration and Hot Reload

- [x] 1.1 Update `hmock.py` `Config` and `load_config()` with `HM_TEMPLATES_DIR_HOT_RELOAD` defaulting to enabled and `HM_CORS_ENABLED` defaulting to disabled. [extends mock-definition-loading/add-stateful-actions]
- [x] 1.2 Add filesystem YAML signature tracking to `hmock.py` `HMockRuntimeState` using the existing template discovery path as the starting point. [extends mock-definition-loading/add-stateful-actions]
- [x] 1.3 Call the hot-reload check from `hmock.py` `MockHTTPRequestHandler._handle()` before behavior matching when hot reload is enabled. [extends mock-definition-loading/add-stateful-actions]
- [x] 1.4 Add `tests/test_hmock.py` coverage for default hot reload, disabled snapshot behavior, and created/edited/deleted filesystem templates becoming visible without restart.
- [x] 1.5 Add `tests/test_hmock.py` coverage that admin API mutations still reload when filesystem hot reload is disabled.

## 2. CORS Handling

- [x] 2.1 Add CORS response decoration helpers in `hmock.py` that insert global headers case-insensitively while preserving mock-defined header values. [extends mock-definition-loading/add-stateful-actions]
- [x] 2.2 Update `hmock.py` `MockHTTPRequestHandler._handle()` to apply CORS headers to matched, unmatched, error, and preflight responses when enabled.
- [x] 2.3 Add `do_OPTIONS()` support in `hmock.py` and return `200 OK` with an empty body for unmatched `OPTIONS` requests only after normal mock matching fails.
- [x] 2.4 Add `tests/test_hmock.py` coverage for global headers, explicit `OPTIONS` mocks, unmatched preflight fallback, disabled CORS behavior, and mock header precedence.

## 3. Binary HTTP Payloads

- [x] 3.1 Add binary file resolution helpers in `hmock.py` for bytes snapshots relative to `HM_TEMPLATES_DIR`, reusing the existing text file path validation shape. [extends mock-definition-loading/add-stateful-actions]
- [x] 3.2 Extend `hmock.py` action validation for `reply_http.body_from_binary_file`, `reply_http.binary_file_name`, `send_http.body_from_binary_file`, and `send_http.binary_file_name`. [extends mock-definition-loading/add-stateful-actions]
- [x] 3.3 Widen `hmock.py` `ResponseInfo.body` handling to support `str | bytes`, including content-length calculation, network writes, and safe logging.
- [x] 3.4 Update `hmock.py` `execute_behavior()` so binary `reply_http` responses send stored bytes as-is, skip template rendering, honor text body precedence, and add `Content-Disposition` when configured.
- [x] 3.5 Update `hmock.py` `_send_http()` so binary POST requests use multipart form data with field `file`, the correct filename, and octet-stream file part defaults, while non-POST methods send raw bytes.
- [x] 3.6 Add `tests/test_hmock.py` coverage for binary reply snapshots, content length, content disposition, body precedence, missing/out-of-root validation, multipart POST upload, and raw non-POST outbound body.

## 4. Admin CLI

- [x] 4.1 Add `omctl` command dispatch in `hmock.py` or a thin executable wrapper that exposes `push` and `delete` commands with the documented defaults and short aliases.
- [x] 4.2 Implement `omctl push` recursive YAML loading and POST behavior for base templates and named template sets using `Content-Type: application/yaml`.
- [x] 4.3 Extend `hmock.py` admin request parsing to accept YAML upload bodies while preserving existing JSON admin API behavior.
- [x] 4.4 Implement `omctl delete` to require `--set-key`, send the template-set DELETE request, and treat `204 No Content` as success.
- [x] 4.5 Add `tests/test_hmock.py` coverage for CLI push defaults, set-key routing, recursive YAML loading, delete validation, delete success, and admin YAML parsing.

## 5. Verification

- [x] 5.1 Run `uv run pytest tests/test_hmock.py` and fix regressions.
- [x] 5.2 Run any project lint or formatting command used by this repository, if available.
- [x] 5.3 Manually review `hmock.py` for compatibility with existing text `body_from_file`, JSON admin API requests, and disabled CORS behavior.
