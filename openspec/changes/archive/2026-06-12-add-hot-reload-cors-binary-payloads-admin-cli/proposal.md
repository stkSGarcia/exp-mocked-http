## Why

Operators need filesystem template edits and admin changes to become useful without restarts, and browser-based clients need a predictable CORS mode for mock responses. The mock server also needs to handle binary payload fixtures and provide a small CLI so template collections can be pushed and removed remotely.

## What Changes

- Add `HM_TEMPLATES_DIR_HOT_RELOAD` with filesystem hot reload enabled by default, so template creations, edits, and deletions under the templates directory become visible automatically.
- Preserve snapshot semantics when hot reload is disabled, while keeping successful admin API mutations visible within the normal reload window.
- Add `HM_CORS_ENABLED` for global mock-server CORS headers, including fallback handling for unmatched `OPTIONS` preflight requests.
- Preserve mock-defined CORS headers when a behavior explicitly sets the same response header.
- Add binary file-backed payload fields for `reply_http` and `send_http`, including stable snapshots, raw byte responses, multipart POST uploads, and raw non-POST outbound bodies.
- Add `omctl` remote admin commands for pushing local YAML template directories to base templates or named template sets, and for deleting named template sets.
- Allow admin template upsert endpoints to receive YAML payloads sent by `omctl` in addition to existing JSON payloads.

## Capabilities

### New Capabilities
- `omctl-admin-cli`: Defines the remote admin CLI commands, flags, payload loading, and expected admin API interactions.

### Modified Capabilities
- `mock-definition-loading`: Add the hot-reload configuration, filesystem reload visibility rules, binary file field validation, binary snapshot loading, and binary path safety.
- `http-behavior-mocking`: Add global mock-server CORS behavior, unmatched preflight responses, binary response bodies, and outbound binary request execution.
- `admin-http-api`: Accept YAML admin upsert payloads for base templates and template sets so `omctl push` can use `application/yaml`.

## Impact

- Affects runtime configuration, template directory scanning, active mock reload coordination, request response middleware, `reply_http` execution, `send_http` execution, admin API payload parsing, and CLI packaging/entry points.
- Adds binary-safe response and outbound request handling, including `Content-Length` computation from bytes and multipart form upload support.
- Requires tests for hot reload enabled/disabled behavior, CORS header precedence and preflight fallback, binary response and outbound payload handling, YAML admin upserts, and `omctl` command behavior.
