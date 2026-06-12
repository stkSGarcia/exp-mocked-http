## Context

`hmock.py` currently owns configuration, YAML discovery, mock validation, active state, mock request handling, admin API handling, persistence helpers, and outbound HTTP execution in one module. Existing file-backed text bodies are resolved during mock loading and stored on action payloads, giving each loaded configuration a stable snapshot until the next reload.

The previous admin API work introduced `MockState`, persisted base templates, persisted template sets, and bounded visibility for successful admin mutations. This change extends those same paths: filesystem hot reload should replace active state from a fresh collection, while admin mutations continue to update through the existing persistence and reload flow.

## Goals / Non-Goals

**Goals:**

- Add environment-driven hot reload, global CORS, and binary payload behavior without changing the YAML behavior model beyond the new fields.
- Preserve loaded-configuration snapshots for text and binary file payloads.
- Keep admin API mutations atomic from the point of view of request handling.
- Add a small `omctl` CLI that can push local YAML template directories and delete named template sets through the admin API.
- Keep the implementation dependency-light and consistent with the existing single-file, standard-library style.

**Non-Goals:**

- Add long-running filesystem watcher dependencies or event-based file monitoring.
- Add authentication, authorization, or TLS for the admin API or CLI.
- Add generic multipart form support for inbound mock requests.
- Infer binary content types from file extensions.
- Change existing JSON admin API behavior.

## Decisions

### Poll-free hot reload at request/admin boundaries

The server will treat `HM_TEMPLATES_DIR_HOT_RELOAD=true` as a request-time freshness check instead of introducing a background watcher. Before matching a mock request, compare a lightweight templates-directory fingerprint against the last loaded fingerprint; if it changed, rebuild the filesystem plus persisted collection and atomically replace `MockState`.

Alternative considered: background watcher thread. That would reduce per-request scanning but adds shutdown coordination, race handling, platform-specific filesystem edge cases, and a dependency or more complex polling loop. Request-boundary checking is simpler and matches the current synchronous reload model.

### Whole-collection reloads

Each reload will call the same collection-building path used at startup and admin mutation time. Successful reloads replace the active collection atomically; failed reloads keep the previous active set and log the error.

Alternative considered: mutate individual loaded behaviors for changed files. Incremental updates would complicate duplicate-key ordering, inheritance, named templates, persisted definitions, and validation failures. Rebuilding the whole collection preserves existing semantics.

### Binary snapshots as bytes on action payloads

Add a binary file resolver parallel to the existing text file resolver. It will enforce paths inside the templates directory, read bytes at load time, and store bytes plus filename metadata on the action payload. Binary fields are selected only when the inline `body` is absent or empty, matching existing file-backed precedence.

Alternative considered: read binary files at response/action execution time. That would make fixture edits visible outside reload boundaries and violate stable snapshot behavior.

### CORS at response finalization

Add global CORS headers immediately before a mock response is sent. Start from middleware defaults, then overlay mock-defined headers so explicit behavior headers win. Normal behavior matching still runs first; only unmatched `OPTIONS` requests become synthetic preflight responses when CORS is enabled.

Alternative considered: inject CORS headers during action execution. Response finalization centralizes unmatched, matched, success, and error behavior while preserving the selected mock's explicit header values.

### `send_http` multipart only for binary POST

When `send_http` uses `body_from_binary_file` with method `POST`, build a multipart/form-data request with field name `file`, the configured or derived filename, and default part content type `application/octet-stream` unless the action headers provide a content type override. For non-POST methods, send the raw binary bytes as the request body.

Alternative considered: send raw bytes for all methods. The checkpoint explicitly requires multipart POST uploads, and keeping that behavior method-specific avoids surprising existing non-POST uses.

### YAML admin payload support shared by API and CLI

The admin API will parse `application/yaml`, `application/x-yaml`, `text/yaml`, and compatible YAML content types using the existing YAML subset parser, then validate the resulting top-level array through the same definition validation path as JSON. `omctl push` will concatenate or parse all YAML files from the selected directory into one definition array and POST YAML to the existing base or template-set endpoint.

Alternative considered: have `omctl` convert YAML to JSON before posting. Accepting YAML at the API makes the CLI behavior transparent, matches the requested content type, and gives other clients the same capability.

### Separate `omctl.py` CLI module

Add `omctl.py` as a sibling command module with `argparse`, recursive YAML loading, and `urllib.request` calls. This keeps CLI concerns out of request handling while sharing parser/validation helpers from `hmock.py` where useful.

Alternative considered: add subcommands to `hmock.py`. A separate module keeps server startup and remote admin operations distinct and easier to test.

## Risks / Trade-offs

- Request-time directory fingerprinting can add overhead for large template trees -> Keep the fingerprint to path, mtime, size, and file count; only rebuild when it changes.
- Hot reload failures could hide template edits behind the previous active set -> Log validation/load errors and keep serving the last known-good collection.
- Multipart body formatting is easy to get subtly wrong -> Build focused tests against a capture server that verifies boundary, disposition, filename, content type, and bytes.
- Header override rules can be case-sensitive if implemented naively -> Normalize comparisons case-insensitively while preserving the final header spelling from the mock-defined header when present.
- YAML parser limitations may surprise CLI users -> Reuse the project's documented YAML subset behavior and surface parse errors with non-zero CLI exits.

## Migration Plan

No migration is required for existing templates or admin clients. Defaults preserve current CORS-off behavior, enable hot reload by default, and keep JSON admin upserts working. Rollback is to disable filesystem hot reload with `HM_TEMPLATES_DIR_HOT_RELOAD=false` and avoid the new binary fields and `omctl` command.

## Open Questions

- None.
