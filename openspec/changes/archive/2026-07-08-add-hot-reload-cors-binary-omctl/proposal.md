## Why

Runtime mock servers need to behave more like local development and integration environments: template edits should be picked up without restarts, browser clients should be able to call mocks with opt-in CORS, binary fixtures should be served and forwarded byte-for-byte, and teams need a small CLI for pushing or deleting remote admin template sets.

## What Changes

- Add `HM_TEMPLATES_DIR_HOT_RELOAD` with a default of `true` so filesystem creations, edits, and deletions under the templates directory become visible automatically.
- Add `HM_CORS_ENABLED` with a default of `false`; when enabled, the mock HTTP server appends global CORS headers to every response while preserving mock-defined CORS header values.
- Treat unmatched `OPTIONS` requests as CORS preflight only when CORS is enabled, returning `200 OK` with an empty body and the global CORS headers after normal matching has had a chance to select an explicit mock behavior.
- Add `body_from_binary_file` and optional `binary_file_name` to `reply_http` for stable binary response snapshots, byte-for-byte delivery, `Content-Length`, and optional inline `Content-Disposition`.
- Add `body_from_binary_file` and optional `binary_file_name` to `send_http`; send multipart uploads for `POST` and raw binary bodies for non-`POST` methods.
- Add the `omctl` CLI with `push` and `delete` subcommands for remote admin template collection and named template set operations.

## Related Work

### Related Changes

- `add-admin-api-template-storage`: introduced HTTP admin management for adding, replacing, deleting, and persisting mocks without editing filesystem fixtures or restarting. This change complements that work by adding a CLI client for the same admin surface and by clarifying how admin mutations interact with filesystem hot reload.

### Related Specs

- `mock-definition-loading/add-stateful-actions`: covers runtime configuration via environment variables and existing loading behavior. This change builds on that environment-driven configuration model for hot reload and CORS toggles.
- `template-set-storage/add-admin-api-template-storage`: covers named template set replacement through the admin API. This change reuses that storage surface as the target for `omctl push --set-key` and `omctl delete --set-key`.
- `api-template-persistence/add-admin-api-template-storage`: covers persistence of base and named templates added through the admin API. This change relies on those persistence semantics while adding CLI upload and delete operations.
- `template-rendering/add-stateful-actions`: covers template expression contexts. This change explicitly separates binary payload handling from template rendering so binary bytes are never rendered as text templates.
- `template-rendering/add-admin-api-template-storage`: refines rendering behavior for admin-managed templates. This change continues that separation by requiring stable binary snapshots for loaded configurations regardless of the source.
- `http-behavior-mocking/add-stateful-actions`: covers behavior selection and action execution order. This change extends HTTP behavior handling with CORS response decoration, CORS preflight fallback, binary replies, and binary outbound `send_http` bodies.

## Capabilities

### New Capabilities

- `template-hot-reload`: Controls when filesystem template directory changes become visible to request handling.
- `mock-cors`: Adds opt-in global CORS response headers and unmatched preflight handling for the mock HTTP server.
- `binary-http-payloads`: Adds binary file body support for inbound mock replies and outbound HTTP sends.
- `omctl-admin-cli`: Adds a remote admin CLI for pushing YAML templates and deleting named template sets.

### Modified Capabilities

- None.

## Impact

- Affected runtime configuration: `HM_TEMPLATES_DIR_HOT_RELOAD`, `HM_CORS_ENABLED`.
- Affected YAML schema: `reply_http.body_from_binary_file`, `reply_http.binary_file_name`, `send_http.body_from_binary_file`, `send_http.binary_file_name`.
- Affected HTTP behavior: response header merging, unmatched `OPTIONS` fallback, binary response bodies, outbound multipart and raw binary request bodies.
- Affected admin operations: CLI upload to `/api/v1/templates`, CLI upload to `/api/v1/template_sets/{setKey}`, and CLI delete of `/api/v1/template_sets/{setKey}`.
- Tests should cover hot reload enabled/disabled behavior, admin mutation visibility, CORS precedence, binary byte preservation, multipart upload construction, raw binary send bodies, and CLI request formation.
