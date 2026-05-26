## Context

`hmock.py` is a single-file, single-threaded HTTP mock server. Behaviors are defined in YAML and currently support `sleep` and `reply_http` actions plus a rich Jinja2 template context. There is no shared state between requests, and no side-effect mechanism beyond the HTTP response.

The change adds two orthogonal extensions: a Redis-backed state store (accessible via a `redisDo` template function and a `redis` action), and an outbound HTTP side-effect action (`send_http`).

## Goals / Non-Goals

**Goals:**
- Support stateful mock workflows using a Redis store (in-memory for local use, external for composed environments).
- Allow behaviors to read and write Redis state inside template expressions, including conditions.
- Allow behaviors to fire outbound HTTP requests as non-blocking side effects.

**Non-Goals:**
- Persistence across restarts in `memory` mode.
- Full Redis command coverage beyond the 14 listed commands.
- Retry logic or delivery guarantees for `send_http`.
- Observability/logging of `redisDo` results beyond existing structured log levels.

## Decisions

### Redis Client Abstraction

Use `redis-py` with `fakeredis` as the in-memory backend. Both expose the same `execute_command` / `command_call` interface, so a single code path handles both backends. A module-level `_REDIS` singleton is initialized at startup based on `HM_REDIS_TYPE`.

**Alternative considered**: a custom dict-based in-memory store. Rejected because `fakeredis` already implements the full Redis protocol and eliminates a custom parser.

### `redisDo` Return Values

Single-value results are cast to `str`. List results (e.g., `LRANGE`, `KEYS`, `HGETALL`) are joined with `;;` so they can be passed through template expressions and split back with the existing `splitList` filter.

**Alternative considered**: JSON encoding for lists. Rejected to keep templates simple and consistent with the `splitList ";;"`pattern already documented.

### `redis` Action Semantics

Each item in `redis` is a Jinja2 template string. Rendering produces a string; the string is discarded. The intent is that items call `redisDo` as a side effect. This means the `redis` action is purely for organizing Redis writes in a readable list — the actual command execution happens inside `redisDo` calls within the template.

**Alternative considered**: Parsing the rendered string as a Redis command. Rejected because it requires a command parser and makes quoting/escaping complex. Using `redisDo` directly in templates is already the established pattern.

### `send_http` Execution

Fire in a daemon thread immediately after the action is encountered, before the response is sent. Use `urllib.request` (stdlib) to avoid adding a new dependency. Exceptions are caught and logged at debug level; they never propagate to the handler.

**Alternative considered**: `httpx` or `requests`. Rejected for `send_http` to keep the dependency footprint minimal — `urllib.request` covers the required fields. `body_from_file` reuses the same file-resolution logic as `reply_http`.

### Thread Safety

The HTTP server is single-threaded (`HTTPServer` without `ThreadingMixIn`), so `redisDo` calls in the request handler are serialized. The `send_http` thread only reads the already-rendered strings (immutable at that point), so no locking is needed.

## Risks / Trade-offs

- **In-memory state is global per process** → All behaviors share one store; tests that rely on isolation must `DEL` keys explicitly. Mitigation: document this clearly; provide a behavior pattern for cleanup.
- **`send_http` timing** → The outbound request fires before the response is written but runs in a separate thread, so the caller may receive the mock response before the outbound request completes. Mitigation: this is intentional and documented; tests that depend on the outbound call should poll or add a `sleep` before assertions.
- **`fakeredis` version drift** → `fakeredis` must match the `redis-py` major version. Mitigation: pin both in `pyproject.toml`.
