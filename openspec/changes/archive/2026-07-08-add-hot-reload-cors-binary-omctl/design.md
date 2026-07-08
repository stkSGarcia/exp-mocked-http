## Context

The project is a compact Python mock HTTP server with runtime configuration, YAML template loading, request matching, action execution, admin API storage, and tests centered around `hmock.py` and `tests/test_hmock.py`. The new behavior crosses configuration, filesystem reload, HTTP response middleware, YAML validation, binary file IO, outbound HTTP requests, and a new CLI entry point, so a design artifact is useful before implementation.

## Related Work

**`mock-definition-loading/add-stateful-actions`**: Defines environment-driven runtime configuration and mock loading behavior — informs adding `HM_TEMPLATES_DIR_HOT_RELOAD` and `HM_CORS_ENABLED` to the existing config object because this change follows the same configuration/defaults pattern.

**`template-set-storage/add-admin-api-template-storage`**: Defines named template-set replacement, deletion, and reload visibility — informs `omctl --set-key` endpoint selection and delete success handling because the CLI is a client for that admin surface.

**`api-template-persistence/add-admin-api-template-storage`**: Defines persistence and reload visibility for API-added base templates — informs the hot reload boundary decision because admin API mutations must keep their eventual visibility even when filesystem hot reload is disabled.

**`template-rendering/add-stateful-actions`**: Defines template expression rendering contexts — informs binary payload handling because binary fixture bytes must bypass text template rendering.

**`template-rendering/add-admin-api-template-storage`**: Refines rendering behavior for admin-managed templates — informs stable binary snapshots because loaded configurations should behave consistently regardless of whether definitions originated from the filesystem or admin state.

**`http-behavior-mocking/add-stateful-actions`**: Defines HTTP action execution and selected behavior handling — informs the placement of CORS decoration, preflight fallback, binary replies, and binary `send_http` request bodies in the HTTP behavior path.

## Goals / Non-Goals

**Goals:**
- Add configuration defaults and parsing for hot reload and CORS.
- Make filesystem template changes visible automatically when enabled, while preserving a loaded snapshot when disabled.
- Preserve normal admin API mutation visibility regardless of filesystem hot reload state.
- Add opt-in CORS headers with mock-header precedence and unmatched `OPTIONS` preflight fallback.
- Load binary files relative to the templates directory and preserve byte-for-byte response/send behavior.
- Add `omctl push` and `omctl delete` as remote admin API clients with documented defaults.
- Cover the behavior in focused unit and integration tests.

**Non-Goals:**
- Add file watching dependencies or platform-specific filesystem notifications.
- Change the admin API contract beyond consuming existing base-template and template-set endpoints.
- Add MIME detection for binary files; default upload content type stays `application/octet-stream` unless configured headers override it.
- Add authentication, retries, or transport security features to `omctl`.

## Decisions

### Polling reload boundary inside the active registry

The active mock registry should own the loaded filesystem snapshot and expose a single read path for request handling. When `HM_TEMPLATES_DIR_HOT_RELOAD=true`, the registry can compare directory state before serving or at a bounded reload check interval and refresh the filesystem portion when YAML files are added, changed, or removed. When disabled, it should keep the initial filesystem snapshot until an explicit reload boundary used by existing admin mutation handling. _(see `mock-definition-loading/add-stateful-actions`; see `api-template-persistence/add-admin-api-template-storage`)_

Alternative considered: add a filesystem watcher. That would introduce an external dependency and platform-specific behavior for a small repo; polling or mtime fingerprinting is enough for the requirement.

### Separate filesystem reload from admin mutation reload

Filesystem hot reload controls only the templates directory. Admin API mutations should continue to update persisted state and become visible through the existing eventual-reload path even if filesystem edits are frozen. _(see `template-set-storage/add-admin-api-template-storage`; see `api-template-persistence/add-admin-api-template-storage`)_

Alternative considered: make the flag freeze all reload sources. That would violate the admin mutation visibility requirement and make remote management surprising.

### Apply CORS after mock response construction

CORS headers should be merged after the response status/body/headers are known. The merge should add missing global headers but never overwrite mock-defined CORS values. Unmatched `OPTIONS` preflight should be handled only after normal matching fails, so explicit `OPTIONS` mocks keep priority. _(see `http-behavior-mocking/add-stateful-actions`)_

Alternative considered: intercept every `OPTIONS` request before matching. That would prevent users from defining explicit mock behavior for `OPTIONS`.

### Treat binary fixture content as loaded bytes

Validation/loading should resolve `body_from_binary_file` relative to the templates directory and store bytes on the loaded behavior/action representation. Reply actions then send those bytes directly, set `Content-Length`, and optionally set inline `Content-Disposition`. `reply_http.body` keeps precedence when non-empty. _(see `template-rendering/add-stateful-actions`; see `template-rendering/add-admin-api-template-storage`)_

Alternative considered: read the binary file lazily during request handling. That would make binary responses change outside the loaded configuration snapshot and conflict with disabled hot reload behavior.

### Build outbound binary sends at action execution time

`send_http` should reuse the loaded binary bytes. For `POST`, construct multipart form data with field `file`, a configured or derived filename, and `application/octet-stream` unless headers specify otherwise. For non-`POST`, send the raw bytes as the request body. _(see `http-behavior-mocking/add-stateful-actions`)_

Alternative considered: always send raw bytes regardless of method. That would not satisfy the admin-style upload behavior expected for `POST`.

### Implement `omctl` as a small Python CLI next to `hmock.py`

Add an `omctl.py` entry point using the standard library for argument parsing, recursive YAML file reading, and HTTP requests. Keep request formation simple and deterministic: concatenate or otherwise preserve recursive YAML file contents into one `application/yaml` payload, choose the endpoint from `--set-key`, and surface non-success responses as command failures. _(see `template-set-storage/add-admin-api-template-storage`; see `api-template-persistence/add-admin-api-template-storage`)_

Alternative considered: fold CLI behavior into `hmock.py`. A separate file keeps server startup and remote admin operations easier to test and invoke.

## Risks / Trade-offs

- Reload checks on every request could add filesystem overhead -> Use a cheap directory fingerprint and consider a short debounce interval if tests reveal overhead.
- Binary files can be large -> Store bytes only for referenced binary fixtures and avoid extra copies during response/send assembly where practical.
- Multipart encoding is easy to get subtly wrong -> Add capture-server tests that assert boundary headers, field name, filename, content type, and byte presence.
- Header casing can vary through Python HTTP libraries -> Assert header values case-insensitively in tests where appropriate.
- CLI YAML aggregation order may affect duplicate-key behavior -> Load files in deterministic recursive path order to match existing filesystem loader expectations.

## Migration Plan

No data migration is required. Defaults preserve current CORS behavior (`HM_CORS_ENABLED=false`) while enabling filesystem hot reload by default. Rollback can disable hot reload with `HM_TEMPLATES_DIR_HOT_RELOAD=false` and stop using `omctl`.

## Open Questions

- Should `omctl push` preserve individual file boundaries with document separators when combining multiple YAML files, or mirror the server's existing recursive loader shape exactly?
- Should an explicit `Content-Type` header on `send_http` apply to the multipart file part, the whole request, or both? The current requirement only says headers may override the default file part content type.
