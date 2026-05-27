## Context

`hmock.py` is a single-file Python mock HTTP server. Templates are loaded once at startup from `HM_TEMPLATES_DIR`. The admin API (port 9998) already supports runtime mutations. Four capabilities are being added: filesystem hot reload, CORS headers, binary file payloads, and an `omctl` admin CLI.

## Goals / Non-Goals

**Goals:**

- Auto-reload templates on filesystem change when `HM_TEMPLATES_DIR_HOT_RELOAD=true`
- Inject permissive CORS headers on every mock server response when `HM_CORS_ENABLED=true`
- Serve binary file content from `reply_http` without template rendering
- Upload binary file bodies in `send_http` (multipart for POST, raw for others)
- Provide `omctl push` and `omctl delete` as a scriptable CLI over the admin API

**Non-Goals:**

- Fine-grained CORS policies (specific origins, methods, or headers)
- Hot reload for the admin API server itself
- Binary file streaming or partial-content (Range) responses
- `omctl` subcommands beyond `push` and `delete`

## Decisions

### Hot Reload: polling vs. `watchdog`

**Decision**: Use `watchdog` (third-party) if available, fall back to a polling loop every 1 second.

Rationale: `watchdog` uses OS-native inotify/FSEvents for low-latency, low-CPU detection. Polling is a reliable fallback that adds no extra dependency. The reload itself reuses the existing load-and-validate pipeline on a background thread. A `threading.Lock` guards template state replacement.

Alternatives considered: `inotifywait` subprocess — fragile cross-platform; reloading on every request — prohibitively expensive.

### CORS: middleware vs. per-route

**Decision**: Implement as a thin wrapper around the existing request handler. After the normal response is written (or after a synthetic 200 for unmatched OPTIONS), inject CORS headers only if `HM_CORS_ENABLED=true`.

Mock-defined CORS headers take precedence: when building the final header map, apply middleware headers first, then overlay `reply_http.headers`. This satisfies the "keep mock-defined value" rule without special-casing.

### Binary Payloads: load time vs. request time

**Decision**: Load and snapshot binary file bytes at configuration-load time, same as `body_from_file`. Path security check (must stay within `HM_TEMPLATES_DIR`) is applied at load time.

Rationale: consistent with existing `body_from_file` behavior; avoids per-request file I/O.

Binary content bypasses template rendering entirely. `Content-Length` is set from `len(bytes)`. When `binary_file_name` is present, `Content-Disposition: inline; filename="<name>"` is added.

### send_http binary: multipart vs. raw

**Decision**: POST sends a `multipart/form-data` upload using field name `file`; all other methods send raw bytes as the request body.

Rationale: POST + file upload is the dominant use case; multipart is the conventional encoding. Non-POST callers (PUT, PATCH) typically send a raw body.

### omctl: standalone script vs. module

**Decision**: `omctl` is a standalone Python script (entry point in `pyproject.toml`) using `argparse` and `urllib` from the standard library. No new dependencies.

Rationale: keeps the tool dependency-free and deployable as a single file. The admin API contract is stable enough that a thin HTTP wrapper suffices.

## Risks / Trade-offs

- **Hot reload race**: A request arriving mid-reload could see a partially rebuilt template map → Mitigation: swap the entire template map atomically under a lock after full validation.
- **watchdog optional dependency**: If not installed, polling is used silently; this may surprise users who expect instant reload → Mitigation: log a startup message indicating which mechanism is active.
- **Binary path traversal**: Malicious YAML could point `body_from_binary_file` outside the templates dir → Mitigation: apply the same `os.path.abspath` / `startswith` guard already used for `body_from_file`.
- **CORS + explicit OPTIONS behavior**: An explicit OPTIONS mock must win over the preflight catch-all → Mitigation: the CORS OPTIONS fallback is only triggered after the normal matching loop returns no match.

## Migration Plan

- `HM_TEMPLATES_DIR_HOT_RELOAD` defaults to `true`; existing deployments gain hot reload automatically. To opt out, set `HM_TEMPLATES_DIR_HOT_RELOAD=false`.
- `HM_CORS_ENABLED` defaults to `false`; no behavior change for existing deployments.
- New YAML fields (`body_from_binary_file`, `binary_file_name`) are optional; existing templates remain valid.
- `omctl` is a new tool; no breaking changes to existing server behavior.

## Open Questions

- Should hot reload debounce rapid successive changes (e.g., editor write-then-rename)? Current plan: reload on every detected change with a 200ms quiet period.
- Should `omctl push` print a success/error summary or remain silent on success (Unix convention)? Current plan: silent on success, error message + non-zero exit on failure.
