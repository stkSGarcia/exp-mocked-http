## 1. Configuration And Reload State

- [x] 1.1 Extend `Config` and `load_config` with `HM_TEMPLATES_DIR_HOT_RELOAD` defaulting to true and `HM_CORS_ENABLED` defaulting to false.
- [x] 1.2 Add config tests for new defaults and environment overrides.
- [x] 1.3 Add a templates-directory fingerprint helper that tracks YAML file paths, mtimes, sizes, and deletions.
- [x] 1.4 Add a reload coordinator that rebuilds filesystem plus persisted definitions and atomically replaces `MockState` on successful filesystem changes.
- [x] 1.5 Wire request handling to refresh from the templates directory when hot reload is enabled.
- [x] 1.6 Ensure failed filesystem hot reloads keep the previous active set and log the validation or load error.
- [x] 1.7 Add tests for hot reload creation, edit, deletion, disabled filesystem reload behavior, admin mutation visibility while disabled, and failed reload preservation.

## 2. Binary File Payload Loading

- [x] 2.1 Add a binary file resolver that enforces templates-directory path containment and returns stable bytes.
- [x] 2.2 Validate `reply_http.body_from_binary_file` and optional `reply_http.binary_file_name`, storing loaded binary bytes and metadata on the action payload.
- [x] 2.3 Validate `send_http.body_from_binary_file` and optional `send_http.binary_file_name`, storing loaded binary bytes, source basename, and metadata on the action payload.
- [x] 2.4 Add loading tests for valid binary snapshots, missing files, path traversal rejection, filename validation, and stable bytes across fixture edits before reload.

## 3. Binary Response And Outbound Execution

- [x] 3.1 Update `reply_http` execution to send binary bytes when inline `body` is absent or empty and `body_from_binary_file` is present.
- [x] 3.2 Compute binary response `Content-Length` from bytes and add `Content-Disposition: inline; filename="<name>"` when `binary_file_name` is set.
- [x] 3.3 Preserve inline response body precedence over binary file bodies and skip template rendering for binary bytes.
- [x] 3.4 Update `send_http` execution to send binary POST bodies as multipart form data with field name `file`.
- [x] 3.5 Derive multipart filenames from `binary_file_name` or `basename(body_from_binary_file)` and default the file part content type to `application/octet-stream` unless headers override it.
- [x] 3.6 Update non-POST binary `send_http` execution to send raw bytes and preserve inline body precedence.
- [x] 3.7 Add response and capture-server tests for raw binary bytes, content length, content disposition, no template rendering, multipart POST, raw non-POST body, filename selection, content type override, and inline precedence.

## 4. CORS Behavior

- [x] 4.1 Add global CORS header helpers for `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials`.
- [x] 4.2 Apply global CORS headers to every mock-server response when `HM_CORS_ENABLED` is true.
- [x] 4.3 Preserve mock-defined CORS headers over global defaults using case-insensitive header-name comparison.
- [x] 4.4 Preserve normal matching for explicit `OPTIONS` behaviors before considering preflight fallback.
- [x] 4.5 Return `200 OK` with an empty body and global CORS headers for unmatched `OPTIONS` requests when CORS is enabled.
- [x] 4.6 Add tests for enabled/disabled CORS, matched responses, explicit `OPTIONS`, unmatched preflight fallback, 404 behavior without CORS, and mock header precedence.

## 5. Admin YAML Payloads

- [x] 5.1 Add admin request parsing for YAML content types while preserving JSON parsing for existing clients.
- [x] 5.2 Route YAML payloads through the same definition-array validation used for JSON base template and template set upserts.
- [x] 5.3 Return `400 Bad Request` without changing active state for invalid YAML or non-array YAML payloads.
- [x] 5.4 Add admin API tests for YAML base upsert, YAML template-set upsert, invalid YAML rejection, and continued JSON behavior.

## 6. `omctl` CLI

- [x] 6.1 Add an `omctl.py` command module with `argparse` subcommands for `push` and `delete`.
- [x] 6.2 Implement `omctl push` flags `--directory/-d`, `--url/-u`, and `--set-key/-k` with the specified defaults.
- [x] 6.3 Implement recursive YAML discovery for `omctl push`, ignoring non-YAML files and combining definitions into one YAML payload.
- [x] 6.4 POST `omctl push` payloads as `application/yaml` to `/api/v1/templates` or `/api/v1/template_sets/{setKey}` depending on `--set-key`.
- [x] 6.5 Implement `omctl delete` flags `--url/-u` and required `--set-key/-k`, sending `DELETE /api/v1/template_sets/{setKey}`.
- [x] 6.6 Make `omctl push` exit successfully only on `200 OK` and `omctl delete` exit successfully only on `204 No Content`.
- [x] 6.7 Add CLI tests for help, required flags, default and override URLs, recursive YAML loading, request content type, target endpoints, success exits, and failure exits.

## 7. Verification

- [x] 7.1 Run focused tests for configuration, hot reload, binary payloads, CORS, YAML admin payloads, and `omctl`.
- [x] 7.2 Run the full test suite with `uv run pytest`.
- [x] 7.3 Run `openspec validate add-hot-reload-cors-binary-payloads-admin-cli --strict` and resolve any issues.
- [x] 7.4 Run `openspec status --change add-hot-reload-cors-binary-payloads-admin-cli` and confirm the change is apply-ready.
