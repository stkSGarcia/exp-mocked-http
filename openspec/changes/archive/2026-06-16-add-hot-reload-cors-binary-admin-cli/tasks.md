## 1. Configuration And Reload State

- [x] 1.1 Update `hmock.py` `Config` and `load_config()` to read `HM_TEMPLATES_DIR_HOT_RELOAD` defaulting to `true` and `HM_CORS_ENABLED` defaulting to `false`. [extends mock-definition-loading]
- [x] 1.2 Extend `hmock.py` `HMockRuntimeState` to accept the hot reload setting and track a filesystem YAML signature for `templates_dir`.
- [x] 1.3 Update `hmock.py` `HMockRuntimeState.get_behaviors()` so enabled hot reload rebuilds when YAML files are created, edited, or deleted, while disabled hot reload keeps the existing loaded configuration until explicit `reload()`.
- [x] 1.4 Preserve existing admin API mutation reload behavior in `hmock.py` `upsert_base_definitions()`, `delete_all_base_definitions()`, `delete_base_definition()`, `replace_template_set()`, and `delete_template_set()` when hot reload is disabled.

## 2. Binary Payload Loading

- [x] 2.1 Add a binary file resolver in `hmock.py` alongside `_resolve_body_file()` that enforces templates-directory containment, missing-file validation, and byte-for-byte snapshots. [extends mock-definition-loading]
- [x] 2.2 Update `hmock.py` `_validate_actions()` to validate `reply_http.body_from_binary_file`, `reply_http.binary_file_name`, `send_http.body_from_binary_file`, and `send_http.binary_file_name`.
- [x] 2.3 Store loaded binary snapshots on action payloads without passing them through template rendering.
- [x] 2.4 Add validation tests in `tests/test_hmock.py` for binary file snapshots, missing binary files, path traversal rejection, and optional filename validation.

## 3. Binary HTTP Execution

- [x] 3.1 Update `hmock.py` `ResponseInfo`, `execute_behavior()`, and `MockHTTPRequestHandler._handle()` to support byte response bodies and byte-accurate `Content-Length`. [extends http-behavior-mocking]
- [x] 3.2 Implement `reply_http.body_from_binary_file` execution in `hmock.py`, including inline body precedence and optional `Content-Disposition: inline; filename="<binary_file_name>"`.
- [x] 3.3 Update `hmock.py` `_send_http()` to send `send_http.body_from_binary_file` as multipart form data for `POST` and raw bytes for non-`POST` methods.
- [x] 3.4 Implement multipart filename selection and default file part content type handling in `hmock.py` `_send_http()`.
- [x] 3.5 Add `tests/test_hmock.py` coverage for binary response bytes, no binary template rendering, binary `Content-Length`, disposition filename, outbound multipart `POST`, outbound raw non-`POST`, and inline body precedence.

## 4. CORS Behavior

- [x] 4.1 Pass the CORS setting from `hmock.py` server construction into `HMockHTTPServer` or runtime state. [extends http-behavior-mocking]
- [x] 4.2 Add a `hmock.py` CORS helper that fills missing global CORS headers case-insensitively and preserves mock-defined CORS header values.
- [x] 4.3 Update `MockHTTPRequestHandler` in `hmock.py` to handle `OPTIONS`, run normal mock matching first, return empty `200 OK` for unmatched preflight when CORS is enabled, and keep normal unmatched behavior otherwise.
- [x] 4.4 Add `tests/test_hmock.py` coverage for CORS defaults, matched response headers, mock header precedence, explicit `OPTIONS` behavior, unmatched preflight, and unmatched non-`OPTIONS`.

## 5. Admin YAML And CLI

- [x] 5.1 Update `hmock.py` admin POST parsing to accept `application/yaml` payloads for `/api/v1/templates` and `/api/v1/template_sets/{setKey}` while keeping existing JSON parsing behavior.
- [x] 5.2 Add `omctl push` implementation using `argparse` and `urllib.request`, with `--directory/-d`, `--url/-u`, and `--set-key/-k` flags and recursive deterministic YAML file loading. [extends admin-cli-operations]
- [x] 5.3 Add `omctl delete` implementation with `--url/-u` and required `--set-key/-k`, expecting `204 No Content`. [extends admin-cli-operations]
- [x] 5.4 Add a thin executable `omctl` launcher or equivalent testable entry point that invokes the CLI implementation.
- [x] 5.5 Add `tests/test_hmock.py` coverage for admin YAML parsing, `omctl push` base uploads, `omctl push --set-key` uploads, CLI defaults, and `omctl delete` behavior.

## 6. Verification

- [x] 6.1 Run focused tests from `tests/test_hmock.py` for reload, CORS, binary payloads, admin YAML, and CLI behavior.
- [x] 6.2 Run the full test suite with `uv run pytest`.
- [x] 6.3 Run `openspec status --change "add-hot-reload-cors-binary-admin-cli"` and confirm the change is ready to apply.
