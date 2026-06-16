## Context

`hmock.py` currently owns configuration, YAML loading, validation, runtime state, request handling, outbound `send_http`, admin API endpoints, and process startup. Existing file-backed bodies are loaded as text snapshots during validation, rendered at execution time, and tests live in `tests/test_hmock.py`.

The admin API already has base-template and template-set mutation endpoints, but the handler currently parses JSON arrays. `omctl push` must send `Content-Type: application/yaml`, so the admin POST path needs YAML request parsing in addition to the CLI.

## Related Work

**`http-behavior-mocking`**: Defines mock request matching, action execution, response defaults, outbound HTTP behavior, and unmatched-request handling. This informs the decision to run normal matching before CORS preflight fallback and to add CORS headers after `reply_http` response construction because mock-defined headers must win _(see `http-behavior-mocking`)_.

**`mock-definition-loading`**: Defines recursive YAML discovery, validation, and stable file-backed snapshots. This informs the decision to snapshot binary files during load with the same path containment rules used by text-backed bodies _(see `mock-definition-loading`)_.

**`template-rendering`**: Defines where template rendering applies. This informs the decision to store binary payloads as `bytes` and bypass rendering while leaving URL, method, headers, and text bodies on the existing render path _(see `template-rendering`)_.

## Goals / Non-Goals

**Goals:**
- Add configuration for filesystem hot reload and CORS without changing existing defaults except where checkpoint 6 requires new default values.
- Preserve stable snapshots for each loaded configuration, including binary files.
- Keep text and binary body precedence consistent: non-empty inline `body` wins, file body is used only when inline body is omitted or empty.
- Add CLI coverage that exercises real admin API behavior.

**Non-Goals:**
- No file watcher dependency is required; request-time reload checks are sufficient for the specified behavior.
- No authentication, authorization, or CORS origin filtering is added.
- No binary template rendering is introduced.

## Decisions

1. Extend `Config` with `templates_dir_hot_reload: bool = True` and `cors_enabled: bool = False`.
   - Rationale: The existing `load_config()` pattern already centralizes environment defaults.
   - Alternative considered: Read environment variables directly in handlers; rejected because it spreads configuration logic.

2. Put hot reload ownership in `HMockRuntimeState`.
   - When hot reload is enabled, `get_behaviors()` should refresh filesystem-backed definitions before returning behavior snapshots. A simple directory signature based on YAML file paths, mtimes, sizes, plus deleted-file detection is enough.
   - Admin mutations should continue to call `reload()` directly, independent of hot reload.
   - Alternative considered: Use a background watcher thread; rejected because it adds lifecycle complexity without being required.

3. Add binary snapshot helpers parallel to `_resolve_body_file()`.
   - `_resolve_binary_body_file()` should enforce templates-directory containment and return `bytes`.
   - Validation should accept optional string `binary_file_name` for both `reply_http` and `send_http`.
   - Alternative considered: Reuse `_resolve_body_file()` and encode/decode through text; rejected because binary bytes must be preserved exactly.

4. Change response writing to support bytes.
   - `ResponseInfo` should carry `body: str | bytes` or add a `body_bytes()` helper so handlers can write binary responses without UTF-8 encoding them.
   - Logging can represent binary bodies as a size marker rather than raw bytes to avoid invalid JSON or noisy logs.
   - Alternative considered: Store binary as Latin-1 text; rejected because it obscures byte intent and risks accidental rendering.

5. Apply CORS after response construction.
   - Add a helper that fills missing global CORS headers only when `cors_enabled` is true. Since it only fills missing keys case-insensitively, mock-defined `reply_http.headers` values remain authoritative.
   - Unmatched `OPTIONS` should be handled after normal behavior matching fails and before `not_found_response()`.
   - Alternative considered: Add CORS headers inside `execute_behavior()`; rejected because unmatched preflight and template errors also need consistent headers.

6. Implement `send_http` binary handling in `_send_http()`.
   - For `POST`, use multipart form-data with field name `file`, configured/default filename, and `application/octet-stream` unless action headers provide an override for the file part content type.
   - For non-`POST`, send the raw binary bytes as request data.
   - Existing URL, method, and header rendering remains unchanged.

7. Add `omctl` in the same module first, then expose it as an executable entry point if packaging metadata exists later.
   - Implement subcommands with `argparse`, recursively read YAML files in deterministic path order, combine them into one YAML document/list payload, and send with `urllib.request`.
   - Update admin POST parsing to accept `application/yaml` for `/api/v1/templates` and `/api/v1/template_sets/{setKey}` while retaining JSON compatibility.

## Risks / Trade-offs

- [Risk] Reloading on every request can add filesystem overhead for large template trees -> Mitigation: compare a cheap directory signature and only rebuild when it changes.
- [Risk] Binary response logs can break JSON logging or produce huge records -> Mitigation: log binary body size and content type metadata instead of raw bytes.
- [Risk] Multipart construction with only standard library code is easy to get subtly wrong -> Mitigation: keep the builder small, test request bytes and headers through a local test server.
- [Risk] YAML admin parsing could change existing JSON behavior -> Mitigation: choose parser by `Content-Type` and keep JSON as the default for existing clients.

## Migration Plan

No data migration is required. Rollout can add the new environment variables with defaults, deploy server changes, then add the CLI. Rollback is safe because existing YAML fields and admin JSON calls remain compatible.

## Open Questions

- The checkpoint says headers may override the multipart file part content type; implementation should define the exact override key, likely `Content-Type`, during coding and test it explicitly.
