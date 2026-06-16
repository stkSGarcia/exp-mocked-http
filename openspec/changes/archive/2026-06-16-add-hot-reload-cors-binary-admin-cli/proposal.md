## Why

Mock users need runtime template edits, browser-facing mock responses, binary payload coverage, and remote admin workflows without restarting or hand-coding one-off tooling. This change expands the mock server from text-oriented local YAML replay into a more complete local and remote test fixture system.

## Related Work

### Related Changes
- `add-http-yaml-mock-server`: introduced the lightweight YAML-driven HTTP mock service; this change extends that server with CORS behavior and binary response handling.
- `add-template-helpers-file-backed-bodies`: added file-backed response payloads to keep large text responses out of YAML; this change complements it with binary file snapshots that are served or sent without template rendering.
- `add-admin-api-template-storage`: added runtime template storage over an admin API; this change builds on that remote-management direction by adding a CLI that can push YAML collections and delete named template sets.

### Related Specs
- `http-behavior-mocking`: defines request matching, action execution, response defaults, outbound HTTP action behavior, and unmatched-request handling; this change reuses those contracts for CORS injection, unmatched preflight handling, binary `reply_http`, and binary `send_http`.
- `mock-definition-loading`: defines environment configuration, recursive YAML discovery, schema validation, and stable file snapshots for text-backed bodies; this change adapts those loading rules for hot reload boundaries and binary file payload validation.
- `template-rendering`: defines where request-context template rendering applies; this change keeps binary file payloads outside template rendering while preserving existing rendering behavior for text bodies, headers, URLs, and conditions.

## What Changes

- Add `HM_TEMPLATES_DIR_HOT_RELOAD` with default `true` so filesystem creations, edits, and deletions under the templates directory are visible without restart when enabled, and remain fixed until a reload boundary when disabled.
- Add `HM_CORS_ENABLED` with default `false`; when enabled, add global CORS headers to mock server responses while preserving mock-defined CORS headers.
- Treat unmatched `OPTIONS` requests as CORS preflight responses when CORS is enabled, after normal mock matching has had the first chance to handle the request.
- Add `body_from_binary_file` and optional `binary_file_name` to `reply_http`, using stable binary snapshots, raw byte responses, `Content-Length` from byte size, and optional inline `Content-Disposition`.
- Add `body_from_binary_file` and optional `binary_file_name` to `send_http`, using multipart form-data for `POST` and raw request bodies for non-`POST` methods.
- Add `omctl push` for recursively loading YAML templates and uploading them to the admin API as the base collection or a named template set.
- Add `omctl delete` for deleting a named template set through the admin API.

## Capabilities

### New Capabilities
- `admin-cli-operations`: Remote CLI operations for pushing YAML template collections and deleting named template sets through the admin API.

### Modified Capabilities
- `mock-definition-loading`: Adds hot reload configuration and binary file validation/snapshot rules for `reply_http` and `send_http`.
- `http-behavior-mocking`: Adds CORS response behavior, unmatched preflight handling, binary `reply_http` responses, and binary `send_http` request-body execution.

## Impact

- Affects server configuration parsing, template directory loading/reload behavior, schema validation, action execution, outbound HTTP request construction, and response header middleware.
- Adds a user-facing `omctl` executable or entry point for remote admin operations.
- Expands YAML action schema with binary file fields while preserving existing text body precedence rules.
- Requires tests for reload on/off behavior, CORS header precedence, binary response bytes and framing, multipart/raw outbound binary requests, and CLI admin API calls.
