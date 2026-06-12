## Context

The current project is a compact Python mock HTTP server with a single `hmock.py` implementation, a small YAML subset parser, runtime state around filesystem and persisted definitions, an optional admin HTTP server, and focused pytest coverage. File-backed text bodies are already snapshotted during definition loading, and admin mutations already flow through runtime state before becoming visible to mock requests.

This change extends that model in four related areas: filesystem visibility for template edits, CORS handling for browser clients, binary fixture support for inbound mock responses and outbound callbacks, and a small remote admin CLI.

## Goals / Non-Goals

**Goals:**
- Make template file creations, edits, and deletions visible without restart when hot reload is enabled.
- Preserve stable snapshots for a loaded configuration, including binary file contents.
- Add opt-in global CORS headers without overriding mock-defined CORS header values.
- Support binary `reply_http` responses and `send_http` request bodies, including multipart POST uploads.
- Provide `omctl push` and `omctl delete` as a lightweight admin API client.

**Non-Goals:**
- Add a filesystem watcher dependency; polling/reload-on-request is sufficient for this project.
- Add partial template-set mutation or diff behavior.
- Expand the YAML parser beyond the syntax needed for existing mock definitions.
- Add authentication, authorization, or TLS handling for the admin CLI.

## Decisions

### Reload active snapshots at request boundaries

When `HM_TEMPLATES_DIR_HOT_RELOAD` is true, the runtime state will check the templates directory before handling mock/admin-visible active definitions and rebuild the active snapshot when the filesystem signature changes. The signature can be based on discovered YAML file paths plus metadata such as mtime and size. This fits the current thread-safe runtime state model and avoids adding watcher threads or external dependencies.

Alternative considered: always rebuild for every request. That is simpler but unnecessarily reparses and revalidates unchanged templates, and would make request latency noisy for larger fixture directories.

### Keep disabled hot reload as startup snapshot behavior

When hot reload is disabled, filesystem definitions stay pinned to the startup snapshot. Admin API mutations continue using the existing eventual reload behavior because those changes are mediated by runtime state rather than direct filesystem discovery.

Alternative considered: expose an explicit reload endpoint. The checkpoint only asks for disabled edits to wait until a later reload boundary, so an explicit endpoint is outside this proposal.

### Store binary snapshots as bytes on validated actions

Binary file fields will use the same path safety checks as text `body_from_file`, but read bytes and store internal snapshot fields on the action payload. `reply_http.body_from_binary_file` will be selected only when inline `body` is absent or empty. Binary content is sent as-is and never template-rendered.

Alternative considered: base64-encode binary snapshots inside definitions. Raw bytes are simpler inside Python runtime objects and avoid accidental transformation before response/write time.

### Add CORS as response finalization

CORS headers will be applied just before sending the HTTP response, after a mock action determines status/body/headers. Existing mock-defined CORS headers remain authoritative by only filling missing global CORS header names. Unmatched `OPTIONS` requests will become a synthetic 200 response only when CORS is enabled and no normal mock matched.

Alternative considered: create implicit CORS behaviors during loading. Response finalization keeps CORS orthogonal to behavior ordering and avoids surprising duplicate-key or matching interactions.

### Implement `omctl` with standard-library HTTP

`omctl` will be a Python CLI that recursively reads local YAML files, concatenates their contents into the request body, and posts with `Content-Type: application/yaml`. The admin API will parse YAML payloads in addition to JSON arrays for the affected POST endpoints.

Alternative considered: shell out to `curl`. Keeping the CLI in Python makes it testable with the existing pytest style and portable in the same runtime as `hmock.py`.

## Risks / Trade-offs

- Filesystem metadata signatures can miss extremely fast same-size edits on filesystems with coarse mtimes -> include file size and mtime nanoseconds where available, and document that reload visibility is eventual rather than synchronous.
- Revalidating on request can add latency after large template changes -> cache the last good active snapshot and rebuild only when the signature changes.
- Binary payloads can increase memory use -> keep behavior consistent with existing snapshot semantics and treat fixture sizes as the operator's responsibility.
- Multipart construction is easy to get subtly wrong -> cover boundary, disposition, content type, filename, and body bytes in tests against a local capture server.
- YAML admin posts could diverge from JSON validation -> parse both content types into the same definition list and reuse existing candidate validation before persistence.

## Migration Plan

No breaking migration is required. Existing environments keep current behavior except that filesystem hot reload is enabled by default; operators that want startup-pinned filesystem templates can set `HM_TEMPLATES_DIR_HOT_RELOAD=false`. CORS remains disabled unless `HM_CORS_ENABLED=true`.
