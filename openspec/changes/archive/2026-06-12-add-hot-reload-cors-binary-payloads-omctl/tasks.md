## 1. Configuration And Reloading

- [x] 1.1 Add `HM_TEMPLATES_DIR_HOT_RELOAD` and `HM_CORS_ENABLED` to configuration loading with documented defaults.
- [x] 1.2 Add tests for default and overridden configuration values.
- [x] 1.3 Implement a templates-directory fingerprint that covers YAML definitions and file payload dependencies used by the loaded configuration.
- [x] 1.4 Reload active filesystem definitions at mock-request boundaries when hot reload is enabled and the fingerprint changes.
- [x] 1.5 Preserve startup snapshot behavior for filesystem edits when hot reload is disabled.
- [x] 1.6 Add tests proving filesystem create, edit, and delete visibility when enabled and non-visibility when disabled.

## 2. Binary Payload Loading

- [x] 2.1 Validate `reply_http.body_from_binary_file`, `send_http.body_from_binary_file`, and optional `binary_file_name` fields during behavior loading.
- [x] 2.2 Resolve binary file paths relative to `HM_TEMPLATES_DIR`, reject missing files, and reject paths outside the templates directory.
- [x] 2.3 Store stable byte snapshots for loaded binary files without template rendering.
- [x] 2.4 Add loader tests for binary snapshots, missing files, outside-root paths, and filename metadata.

## 3. Mock HTTP Runtime Behavior

- [x] 3.1 Add global CORS header merging for every mock HTTP server response when `HM_CORS_ENABLED=true`.
- [x] 3.2 Preserve mock-defined CORS header values when global CORS is enabled.
- [x] 3.3 Handle unmatched `OPTIONS` requests as empty `200 OK` preflight responses only when CORS is enabled.
- [x] 3.4 Implement binary `reply_http` response execution with exact bytes, byte `Content-Length`, optional inline `Content-Disposition`, and inline-body precedence.
- [x] 3.5 Add runtime tests for CORS enabled/disabled, explicit `OPTIONS` behavior, unmatched preflight, header precedence, binary responses, and inline-body precedence.

## 4. Outbound HTTP Binary Requests

- [x] 4.1 Implement `send_http` binary POST uploads as multipart form data with field name `file`.
- [x] 4.2 Use `binary_file_name` for multipart filenames when present and otherwise use the basename of `body_from_binary_file`.
- [x] 4.3 Default multipart file part content type to `application/octet-stream` unless action headers override it.
- [x] 4.4 Send binary bytes as the raw outbound request body for non-POST methods.
- [x] 4.5 Preserve inline non-empty `body` precedence over binary file payloads.
- [x] 4.6 Add outbound HTTP tests for multipart POST, filename selection, content type, raw non-POST bytes, and inline-body precedence.

## 5. Admin API YAML Payloads

- [x] 5.1 Extend admin `POST /api/v1/templates` and `POST /api/v1/template_sets/{setKey}` to parse `application/yaml` request bodies.
- [x] 5.2 Reuse existing mock-definition validation and persistence semantics for YAML admin payloads.
- [x] 5.3 Keep existing JSON admin payload behavior unchanged.
- [x] 5.4 Add admin API tests for valid YAML base templates, valid YAML template sets, invalid YAML, and JSON compatibility.

## 6. `omctl` CLI

- [x] 6.1 Add an `omctl` command-line entry point with `push` and `delete` subcommands.
- [x] 6.2 Implement `omctl push` recursive YAML discovery with `--directory/-d`, `--url/-u`, and optional `--set-key/-k`.
- [x] 6.3 Send `omctl push` payloads as `Content-Type: application/yaml` to the correct admin API endpoint.
- [x] 6.4 Implement `omctl delete` with `--url/-u` and required `--set-key/-k`, expecting `204 No Content`.
- [x] 6.5 Add CLI tests for default flags, short flags, base push, set push, delete success, missing set key, and non-success responses.

## 7. Verification

- [x] 7.1 Run the focused test suite covering configuration, loading, runtime behavior, admin API, and CLI changes.
- [x] 7.2 Run the full test suite with `uv run pytest`.
- [x] 7.3 Run OpenSpec validation/status for `add-hot-reload-cors-binary-payloads-omctl` and resolve any artifact issues.
