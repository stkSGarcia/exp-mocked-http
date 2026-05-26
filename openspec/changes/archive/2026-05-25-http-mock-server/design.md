## Context

`hmock.py` is a greenfield single-file HTTP mock server. There is no prior implementation. The server must load YAML behavior definitions at startup, match incoming HTTP requests against them in order, and return configured responses. It is designed to be run with `uv run --project /app hmock.py` and configured entirely through environment variables and YAML files.

## Goals / Non-Goals

**Goals:**
- Single-file implementation (`hmock.py`) with no non-standard library setup beyond `uv`
- YAML-driven behavior definitions with recursive directory scanning
- HTTP method + path matching with named path parameters (`:param` syntax)
- Template-based conditional matching and response rendering
- Ordered action execution (`reply_http`, `sleep`)
- Structured JSON logging per request/response

**Non-Goals:**
- Non-HTTP protocols (covered by future checkpoints)
- Hot-reload of YAML files without restart
- Persistent state or stateful mocks
- Request recording or proxy mode

## Decisions

### Single-file Python with stdlib HTTP server
Use `http.server.BaseHTTPRequestHandler` (stdlib) to avoid external HTTP framework dependencies. The server runs in a single thread; no async complexity needed for a mock server.

**Alternatives considered:** FastAPI/Flask — adds external dependencies and startup overhead for a dev tool; unnecessary here.

### Go `text/template` semantics via Python implementation
The spec requires `{{ ... }}` delimiters, specific built-in and extended functions, and strict undefined-variable errors. Implement a custom renderer wrapping Python's string processing rather than using Jinja2 (which uses `{{ }}` but has different semantics and undefined-variable behavior).

**Decision:** Use Python's `string.Template`-style approach or a lightweight custom parser. Jinja2 is the closest match for syntax and can be configured for strict undefined handling — use Jinja2 with `StrictUndefined` and a custom function environment that matches the required extended function set.

**Alternatives considered:** Chevron/Mustache — wrong syntax. Pure stdlib string formatting — insufficient feature set.

### Path parameter matching with regex conversion
Convert `:param` syntax to named regex groups (`(?P<param>[^/]+)`) at load time. Match against incoming paths at request time.

### Behavior merging: last-key-wins
When multiple YAML files define the same `key`, keep the last loaded definition and emit a warning log. Files are scanned in filesystem order (deterministic via `os.walk` + sort).

### Template context is a dict passed to Jinja2
Build a `TemplateContext` dict per request containing `.HTTPHeader`, `.HTTPBody`, `.HTTPPath`, `.HTTPQueryString`. Wrap headers in a class that exposes a `.Get(name)` method callable from templates.

## Risks / Trade-offs

- **Jinja2 vs Go template semantics** → Minor behavioral gaps (e.g., pipe syntax `|` passes value as last arg in Go but first in Jinja2 filters). Mitigation: implement extended functions as Jinja2 globals/filters with matching signatures; document any gaps.
- **Single-threaded HTTP server** → Slow/sleeping responses will block other requests. Mitigation: acceptable for a local dev mock; document this limitation.
- **YAML load order is filesystem-dependent** → Duplicate key resolution may differ across OSes if walk order differs. Mitigation: sort paths before loading for determinism.

## Migration Plan

No existing code to migrate. Drop `hmock.py` in the project root, add dependencies to `pyproject.toml`, and run via `uv run`.
