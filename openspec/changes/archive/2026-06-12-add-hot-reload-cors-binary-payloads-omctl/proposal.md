## Why

Operators need mock changes, browser-facing responses, and large or non-text payloads to be usable without rebuilding or restarting the server. A small admin CLI also makes remote mock management repeatable from local template directories instead of requiring hand-written HTTP calls.

## What Changes

- Add optional filesystem hot reload for the templates directory, enabled by default through `HM_TEMPLATES_DIR_HOT_RELOAD`.
- Add opt-in global CORS response headers for the mock HTTP server through `HM_CORS_ENABLED`, including unmatched `OPTIONS` preflight handling.
- Add binary file payload support for `reply_http` responses and `send_http` outbound requests.
- Add `omctl` as an admin CLI for pushing YAML templates to the base collection or a named template set, and for deleting named template sets.
- Preserve existing admin mutation visibility behavior and existing mock-defined CORS headers when global CORS is enabled.

## Capabilities

### New Capabilities
- `admin-cli`: Remote admin operations for uploading YAML templates and deleting template sets from a command-line tool.

### Modified Capabilities
- `mock-definition-loading`: Runtime configuration, hot reload behavior, and binary file snapshot validation for mock definitions.
- `http-behavior-mocking`: CORS response behavior, CORS preflight fallback, and binary `reply_http`/`send_http` action execution semantics.
- `admin-http-api`: Accepting YAML-formatted payloads from admin clients while preserving existing template mutation behavior.

## Impact

- Affects `hmock.py` server configuration, template loading, request handling, action validation, response construction, and outbound HTTP execution.
- Adds a new `omctl` command-line entry point for admin API operations.
- Adds tests covering hot reload on/off, CORS headers and preflight handling, binary response and outbound payloads, YAML admin payloads, and CLI push/delete behavior.
