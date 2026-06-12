## Context

`hmock.py` currently centralizes configuration, YAML discovery, behavior validation, admin persistence, request matching, response execution, and outbound HTTP actions in one testable module. It already snapshots text file-backed bodies at load time, runs a separate admin HTTP server, and rebuilds active definitions after admin mutations.

This change extends that foundation in four directions: filesystem changes can refresh the active mock set automatically, mock responses can opt into global CORS behavior, mock definitions can use binary payload files without template rendering, and operators can push/delete templates through a small `omctl` CLI.

## Goals / Non-Goals

**Goals:**
- Add `HM_TEMPLATES_DIR_HOT_RELOAD` with a default of `true` so filesystem additions, edits, and deletions under `HM_TEMPLATES_DIR` become visible without process restart.
- Add `HM_CORS_ENABLED` with a default of `false` so the mock HTTP server can emit global CORS headers and handle unmatched `OPTIONS` preflight requests.
- Support binary file snapshots for `reply_http.body_from_binary_file` and `send_http.body_from_binary_file`.
- Preserve binary bytes exactly and avoid template rendering for binary payloads.
- Add `omctl push` and `omctl delete` for admin API operations using local YAML files.
- Keep the existing JSON admin API behavior, reload visibility contract, and single-file implementation style unless a separate CLI module is clearer.

**Non-Goals:**
- Add authentication, authorization, or TLS for either the mock server or admin CLI.
- Add file watching dependencies.
- Add same-request strong consistency guarantees for admin mutations beyond the existing bounded reload window.
- Implement multipart support for inbound mocked request parsing.

## Decisions

1. Poll filesystem state at request boundaries when hot reload is enabled.

   The runtime should maintain a compact fingerprint of YAML files and binary/text payload files that participate in the loaded configuration. Before matching a mock-server request, compare the current fingerprint with the last loaded fingerprint and reload under the existing runtime lock when it changes. This keeps edits visible without a new dependency and makes deletes observable. When `HM_TEMPLATES_DIR_HOT_RELOAD=false`, the mock server continues using the loaded snapshot until a later explicit reload boundary such as startup or admin-triggered reload.

   Alternative considered: add an OS-level watcher. That would reduce per-request checks but adds dependency and platform complexity that is unnecessary for this small local mock server.

2. Extend configuration rather than route behavior for CORS.

   `HM_CORS_ENABLED` should be part of `Config`. When enabled, the mock response sender should merge global CORS headers into every mock-server response after behavior execution, while preserving any same-named headers produced by the selected mock. Normal matching still runs first, so explicit `OPTIONS` behaviors win. Only unmatched `OPTIONS` requests are converted from `404` to `200` with an empty body and the global CORS headers.

   Alternative considered: inject synthetic behavior definitions. That would make ordering and header precedence harder to reason about and could interact unexpectedly with user-defined `OPTIONS` mocks.

3. Store binary snapshots as bytes on normalized action payloads.

   Validation should resolve `body_from_binary_file` relative to `HM_TEMPLATES_DIR`, reject paths outside the templates directory, reject missing files, and store byte content separately from the original field. `binary_file_name`, when present, should remain metadata and must be a string. Binary response execution should select binary content only when inline `body` is absent or empty, set `Content-Length` from the byte length, and add `Content-Disposition` when `binary_file_name` is set.

   Alternative considered: reuse the existing text `body_from_file` storage path. Binary content cannot safely pass through string rendering or UTF-8 assumptions, so byte storage keeps the behavior exact.

4. Build outbound binary uploads with standard-library request bodies.

   For `send_http` with `body_from_binary_file`, POST should send multipart form data with field name `file`, a generated boundary, the selected filename, and a default part `Content-Type` of `application/octet-stream` unless action headers provide a content type override. Non-POST methods should send the binary bytes as the raw request body. Inline non-empty `body` should continue to take precedence over file-backed bodies.

   Alternative considered: add a multipart helper dependency. The body format is small and deterministic enough to build locally, and avoiding dependencies keeps the project easy to execute with `uv run`.

5. Implement `omctl` as a thin admin client.

   The CLI should recursively read `.yaml` and `.yml` files from `--directory`, concatenate them as one YAML stream, and POST that stream with `Content-Type: application/yaml` to either `/api/v1/templates` or `/api/v1/template_sets/{setKey}`. `omctl delete` should issue `DELETE /api/v1/template_sets/{setKey}` and treat `204 No Content` as success. The admin server should parse YAML request bodies for the existing mutation endpoints when the content type is YAML, while keeping JSON parsing for existing clients.

   Alternative considered: have `omctl` parse YAML locally and send JSON. Sending YAML preserves the user's source format and makes the CLI a minimal transport wrapper around the admin API.

## Risks / Trade-offs

- Per-request hot reload checks add filesystem I/O -> use a cheap fingerprint and only rebuild definitions when the fingerprint changes.
- Binary snapshots can consume memory for large files -> preserve the snapshot contract and keep payload files local to the templates tree.
- Multipart formatting bugs can be subtle -> cover the exact field name, filename, content type, boundary, and bytes in tests.
- Global CORS headers could override user intent -> merge defaults only when a mock did not already set the same header.
- YAML admin parsing broadens accepted input -> reuse the existing YAML loader and definition validation before persistence.

## Migration Plan

Existing deployments continue to work with default CORS disabled and hot reload enabled. Users who need startup-only filesystem behavior can set `HM_TEMPLATES_DIR_HOT_RELOAD=false`. Rollback is removing the new env vars, binary fields, YAML admin parsing, and `omctl`; existing JSON admin clients and text payload mocks remain compatible.

## Open Questions

None.
