## 1. Configuration And Reloading

- [x] 1.1 Extend `Config` and `load_config` for `HM_TEMPLATES_DIR_HOT_RELOAD` and `HM_CORS_ENABLED` defaults.
- [x] 1.2 Add filesystem template signature tracking for discovered YAML files.
- [x] 1.3 Update runtime state to refresh filesystem snapshots at request/reload boundaries when hot reload is enabled.
- [x] 1.4 Preserve startup-pinned filesystem snapshots when hot reload is disabled while keeping admin mutations visible.

## 2. Binary Payload Loading

- [x] 2.1 Add safe binary file resolution and byte snapshot loading for `reply_http.body_from_binary_file`.
- [x] 2.2 Add safe binary file resolution and byte snapshot loading for `send_http.body_from_binary_file`.
- [x] 2.3 Validate optional `binary_file_name` fields on binary `reply_http` and `send_http` payloads.
- [x] 2.4 Preserve inline non-empty `body` precedence over binary file fields.

## 3. Mock HTTP Behavior

- [x] 3.1 Add response finalization that applies global CORS headers only when enabled and only for missing header names.
- [x] 3.2 Add unmatched `OPTIONS` preflight handling after normal mock matching fails.
- [x] 3.3 Send binary `reply_http` bodies as raw bytes with byte-based `Content-Length`.
- [x] 3.4 Add binary response `Content-Disposition` when `binary_file_name` is configured.
- [x] 3.5 Send binary `send_http` POST bodies as multipart form data with field name `file`, filename selection, and default part content type.
- [x] 3.6 Send binary `send_http` non-POST bodies as raw outbound request bytes.

## 4. Admin API And CLI

- [x] 4.1 Teach admin POST endpoints to parse `application/yaml` payloads through the existing YAML subset parser.
- [x] 4.2 Reuse existing candidate validation and persistence paths for YAML and JSON admin payloads.
- [x] 4.3 Add an `omctl` CLI entry point with `push` and `delete` subcommands.
- [x] 4.4 Implement `omctl push` recursive YAML loading, base-template POSTs, template-set POSTs, and CLI flags.
- [x] 4.5 Implement `omctl delete` template-set DELETE behavior and required `--set-key` argument handling.

## 5. Tests And Verification

- [x] 5.1 Add config tests for new hot reload and CORS environment variables.
- [x] 5.2 Add runtime tests for hot reload file creation, edit, deletion, and disabled hot reload behavior.
- [x] 5.3 Add CORS tests for normal responses, mock-defined header precedence, explicit `OPTIONS`, and unmatched preflight.
- [x] 5.4 Add binary `reply_http` tests for snapshots, raw bytes, content length, content disposition, and inline body precedence.
- [x] 5.5 Add binary `send_http` tests for multipart POST, raw non-POST, filename defaults, content type, and inline body precedence.
- [x] 5.6 Add admin YAML payload tests for base templates, template sets, and invalid definitions.
- [x] 5.7 Add `omctl` CLI tests for push defaults, push flags, set-key upload, delete success, and missing set-key failure.
- [x] 5.8 Run the project test suite with `uv run pytest`.
