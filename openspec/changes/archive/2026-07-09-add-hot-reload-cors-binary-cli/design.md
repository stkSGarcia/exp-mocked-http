## Context

HMock is currently implemented in `hmock.py` as a compact Python service with configuration loaded from environment variables, filesystem and persisted template definitions merged through `HMockRuntimeState.reload()`, mock HTTP handling in `MockHTTPRequestHandler`, admin routes in `AdminHTTPRequestHandler`, and tests in `tests/test_hmock.py`.

## Related Work

**`mock-definition-loading/add-stateful-actions`**: Defines environment-driven server configuration and established action validation for `send_http` file bodies — informs the decision to add the new flags to `Config`/`load_config()` and to model binary file validation after existing file-body validation because this change extends the same runtime configuration and action-loading surface.

## Goals / Non-Goals

**Goals:**

- Make filesystem template changes visible without restart when hot reload is enabled.
- Keep the existing loaded snapshot behavior available when hot reload is disabled.
- Add optional CORS headers and unmatched preflight handling to the mock HTTP server.
- Support binary response and outbound request payloads without template-rendering binary bytes.
- Provide an `omctl` CLI for pushing YAML templates and deleting template sets through the admin API.

**Non-Goals:**

- Add a filesystem watcher dependency.
- Change existing text `body_from_file` template-rendering semantics.
- Redesign the admin API resource model beyond accepting the CLI upload payload format.
- Add authentication, authorization, or TLS handling for admin operations.

## Decisions

### Use request-time filesystem signatures for hot reload

Add `templates_dir_hot_reload: bool = True` to `Config` and load it from `HM_TEMPLATES_DIR_HOT_RELOAD` using the existing `_env_bool()` pattern _(see `mock-definition-loading/add-stateful-actions`)_. `HMockRuntimeState` should keep a signature of the currently loaded filesystem YAML files, such as each discovered YAML path plus mtime, size, and existence. Before mock request matching, the mock handler asks runtime state to refresh if hot reload is enabled and the signature changed.

This keeps reload behavior local to `HMockRuntimeState`, avoids a watcher dependency, and naturally handles creations, edits, and deletions. The alternative was a background watcher thread, but that would introduce timing and shutdown complexity for little benefit in this small service.

Admin mutations should continue calling `_reload_after_storage_change()` directly. That path should bypass the hot-reload flag so persisted changes remain visible within the current eventual-reload behavior.

### Apply CORS as a response decoration layer

Add `cors_enabled: bool = False` to `Config` and load it from `HM_CORS_ENABLED` _(see `mock-definition-loading/add-stateful-actions`)_. After normal mock matching and behavior execution, decorate the `ResponseInfo` with global CORS headers only when enabled. Header insertion should be case-insensitive and preserve any header value already set by `reply_http.headers`.

For unmatched `OPTIONS`, run the normal matching flow first. If no behavior matches and CORS is enabled, return an empty `200 OK` response decorated with global CORS headers. This preserves explicit `OPTIONS` mock behavior and keeps CORS fallback out of `find_behavior()`.

### Represent binary responses as bytes at the boundary

`ResponseInfo.body` is currently a string and `MockHTTPRequestHandler` encodes it before writing. To serve binary fixtures as-is, widen the response body type to `str | bytes`, compute `Content-Length` using the actual encoded/text or byte length, and write bytes directly when the response body is binary. Logging can represent binary response bodies with a compact placeholder such as byte count rather than attempting to decode arbitrary bytes.

During validation, resolve `reply_http.body_from_binary_file` relative to `HM_TEMPLATES_DIR`, reject missing or out-of-root paths, and store the loaded bytes on the payload. At execution time, use those bytes only when `reply_http.body` is absent or empty, skip template rendering for bytes, set `Content-Length` from byte length, and add `Content-Disposition` when `binary_file_name` is present.

### Reuse file-body validation shape for outbound binary files

Extend `send_http` validation with `body_from_binary_file` and `binary_file_name`, following the same path resolution and snapshot pattern as existing `send_http.body_from_file` validation _(see `mock-definition-loading/add-stateful-actions`)_. Store bytes separately from text file content so `_send_http()` can avoid rendering binary data.

For `POST`, build a multipart/form-data request with a generated boundary, field name `file`, uploaded filename from `binary_file_name` or `Path(body_from_binary_file).name`, and file part content type `application/octet-stream` unless headers define a file content-type override. For non-`POST`, send raw binary bytes as the request body.

### Implement `omctl` in the existing Python module first

Add an `omctl_main()` command dispatcher in `hmock.py`, with a thin executable wrapper or entry point as needed by the project layout. Keeping the CLI beside the admin API client code avoids creating a package structure just for this change.

`omctl push` should recursively read YAML files from `--directory`, combine them into the admin payload format, and POST to `/api/v1/templates` or `/api/v1/template_sets/{setKey}` with `Content-Type: application/yaml`. The admin handler should accept that content type and parse YAML through the existing definition normalization path. `omctl delete` should send DELETE to the template-set endpoint and treat `204 No Content` as success.

## Risks / Trade-offs

- Request-time signature checks add filesystem stat work to each request -> Keep the signature scan limited to YAML files and reuse the existing recursive discovery helpers.
- File mtimes may have coarse resolution on some filesystems -> Include file size and path set in the signature; tests can force a changed size or wait only where necessary.
- Widening `ResponseInfo.body` can affect logging and helpers that assume strings -> Centralize body serialization for network writes and logs.
- Multipart generation can be subtly wrong -> Cover boundary, field name, filename, content type, and raw bytes in tests with a local capture server.
- YAML upload support changes admin request parsing -> Keep JSON support intact and route YAML parsing only when the request content type is `application/yaml`.

## Migration Plan

No data migration is required. Existing configurations keep their current behavior except that filesystem hot reload defaults to enabled. Operators that need strict loaded-snapshot behavior can set `HM_TEMPLATES_DIR_HOT_RELOAD=false`; CORS remains disabled unless explicitly enabled.

## Open Questions

- Which project-level executable convention should expose `omctl` if this repository remains a single-file Python application?
- What exact header name should override the multipart file part content type, if any, since the checkpoint only says headers may override it?
