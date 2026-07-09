## Why

HMock already supports filesystem templates, admin mutations, file-backed text bodies, and outbound HTTP callbacks, but development and integration workflows still require restarts or ad hoc scripts for common operations. This change makes mock definitions easier to iterate on, easier to use from browsers, and capable of serving and forwarding binary fixtures.

## Related Work

### Related Changes

- None found in the active KG search.

### Related Specs

- `mock-definition-loading/add-stateful-actions`: Covers runtime configuration from environment variables and existing mock-definition behavior. This change extends that configuration style with hot-reload and CORS toggles, and builds on the existing action model for binary `reply_http` and `send_http` payloads.

## What Changes

- Add `HM_TEMPLATES_DIR_HOT_RELOAD`, defaulting to `true`, so filesystem creations, edits, and deletions under the templates directory become visible without restarting the mock HTTP server.
- Add `HM_CORS_ENABLED`, defaulting to `false`, so the mock HTTP server can emit global CORS headers and treat unmatched `OPTIONS` requests as successful preflight responses.
- Extend `reply_http` with `body_from_binary_file` and optional `binary_file_name` for stable binary response snapshots that are not template-rendered.
- Extend `send_http` with `body_from_binary_file` and optional `binary_file_name`, sending multipart form uploads for `POST` and raw binary request bodies for non-`POST` methods.
- Add an `omctl` CLI with `push` and `delete` commands for uploading local YAML templates and deleting remote template sets through the admin API.

## Capabilities

### New Capabilities

- `template-hot-reload`: Controls whether filesystem template edits are automatically reloaded into request handling.
- `mock-cors`: Adds optional global CORS headers and fallback preflight handling for the mock HTTP server.
- `binary-http-payloads`: Adds binary file support for inbound mock responses and outbound `send_http` requests.
- `admin-cli`: Adds the `omctl` remote admin command-line interface.

### Modified Capabilities

- None.

## Impact

- Updates `hmock.py` configuration loading, runtime reload behavior, mock response generation, outbound HTTP action execution, and admin-facing helper code.
- Adds or extends tests in `tests/test_hmock.py` for hot reload behavior, CORS behavior, binary payload snapshots, outbound binary requests, and CLI admin operations.
- Introduces a command-line entry point or executable path for `omctl` while reusing the existing admin API routes.
