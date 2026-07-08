## 1. Configuration and Loading

- [x] 1.1 Update `hmock.py` `Config` and `load_config` to parse `HM_TEMPLATES_DIR_HOT_RELOAD` defaulting to `true` and `HM_CORS_ENABLED` defaulting to `false`. [extends `mock-definition-loading/add-stateful-actions`]
- [x] 1.2 Extend `hmock.py` template loading/validation structures to accept `reply_http.body_from_binary_file`, `reply_http.binary_file_name`, `send_http.body_from_binary_file`, and `send_http.binary_file_name`. [extends `template-rendering/add-stateful-actions`]
- [x] 1.3 Resolve binary file paths relative to the templates directory in `hmock.py`, load binary bytes into the active configuration snapshot, and preserve existing text-body precedence.
- [x] 1.4 Add deterministic filesystem template directory fingerprinting in `hmock.py` so created, edited, and deleted YAML and referenced binary files can trigger reload when hot reload is enabled. [extends `api-template-persistence/add-admin-api-template-storage`]
- [x] 1.5 Keep admin API mutation reload visibility in `hmock.py` independent from filesystem hot reload disablement. [extends `template-set-storage/add-admin-api-template-storage`]

## 2. Mock HTTP Runtime

- [x] 2.1 Update `hmock.py` request handling to refresh the active filesystem snapshot before matching when `HM_TEMPLATES_DIR_HOT_RELOAD=true`, and retain the loaded filesystem snapshot when disabled.
- [x] 2.2 Add CORS response decoration in `hmock.py` that appends global CORS headers to every response only when enabled and does not overwrite mock-defined CORS headers. [extends `http-behavior-mocking/add-stateful-actions`]
- [x] 2.3 Add unmatched `OPTIONS` preflight fallback in `hmock.py` after normal mock matching, returning `200 OK`, an empty body, and global CORS headers only when CORS is enabled.
- [x] 2.4 Update `reply_http` execution in `hmock.py` to send binary bytes as-is, skip template rendering, set `Content-Length`, and add inline `Content-Disposition` when `binary_file_name` is set.
- [x] 2.5 Update `send_http` execution in `hmock.py` to send `POST` binary files as multipart form data with field `file` and to send non-`POST` binary files as raw request bodies. [extends `http-behavior-mocking/add-stateful-actions`]

## 3. omctl CLI

- [x] 3.1 Add `omctl.py` with `push` and `delete` subcommands using standard-library argument parsing and HTTP requests. [extends `api-template-persistence/add-admin-api-template-storage`]
- [x] 3.2 Implement `omctl push --directory/-d`, `--url/-u`, and `--set-key/-k` defaults and endpoint selection for `/api/v1/templates` versus `/api/v1/template_sets/{setKey}`.
- [x] 3.3 Implement recursive YAML payload loading in `omctl.py` with deterministic ordering and `Content-Type: application/yaml`.
- [x] 3.4 Implement `omctl delete --url/-u --set-key/-k`, require `--set-key`, send `DELETE /api/v1/template_sets/{setKey}`, and treat `204 No Content` as success. [extends `template-set-storage/add-admin-api-template-storage`]

## 4. Tests and Verification

- [x] 4.1 Add `tests/test_hmock.py` coverage for new config defaults and environment overrides.
- [x] 4.2 Add `tests/test_hmock.py` hot reload tests for filesystem create/edit/delete visibility, disabled filesystem reload behavior, and admin mutation visibility while disabled.
- [x] 4.3 Add `tests/test_hmock.py` CORS tests for enabled headers, disabled behavior, mock-defined header precedence, explicit `OPTIONS` match priority, and unmatched preflight fallback.
- [x] 4.4 Add `tests/test_hmock.py` binary `reply_http` tests for byte preservation, no template rendering, stable snapshots, `Content-Length`, `Content-Disposition`, and text-body precedence.
- [x] 4.5 Add `tests/test_hmock.py` binary `send_http` tests using the capture server for multipart `POST`, default or overridden content type, derived filename, configured filename, and raw non-`POST` bytes.
- [x] 4.6 Add CLI tests for `omctl.py` push/delete request formation, defaults, recursive YAML ordering, required delete set key, and non-success response failures.
- [x] 4.7 Run `uv run pytest` and fix any failures.
