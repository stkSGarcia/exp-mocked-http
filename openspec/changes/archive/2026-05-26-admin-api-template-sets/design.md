## Context

`hmock.py` is a single-file Python mock server. It loads YAML templates from disk at startup and applies them to incoming HTTP requests. There is no way to modify the active mock set at runtime, and no mocks survive a process restart unless they are on disk. Tests that need to inject mocks between runs must write files and restart the process.

The existing Redis backend (in-memory or external, controlled by `HM_REDIS_TYPE`) is already the shared state store for `redisDo` operations; extending it to also store admin-managed mocks is the natural persistence layer with no new dependencies.

## Goals / Non-Goals

**Goals:**
- Expose a separate admin HTTP server on a configurable port.
- Support full CRUD on mocks at runtime via REST.
- Support named template sets (isolated groups of mocks) via REST.
- Persist admin-managed mocks in Redis so they survive restarts.
- Block `redisDo` from touching the `__hmock_internal:*` keyspace.
- Reload the active mock set within a bounded window after any mutating admin call.

**Non-Goals:**
- Authentication or authorization on the admin API.
- Pagination, filtering, or search on the templates list endpoint.
- Changing the primary mock-serving port or its behavior.
- Persistent storage on the in-memory backend (data still lost on restart when `HM_REDIS_TYPE=memory`).

## Decisions

### Admin server runs as a separate thread/server on a distinct port

The mock-serving port (`HM_HTTP_PORT`) must continue to accept traffic with no added latency. Running the admin server in a separate thread on `HM_ADMIN_HTTP_PORT` keeps concerns separated and avoids routing collisions.

**Alternatives considered:** A single server with an `/admin` prefix — rejected because it pollutes the mock-matching surface and complicates test isolation.

### Redis as the persistence layer for admin mocks

Redis is already the shared state store used by `redisDo`. Writing admin mocks to a reserved Redis key (`__hmock_internal:templates`) and template sets to `__hmock_internal:tset:<setKey>` reuses the existing connection with zero new dependencies.

**Alternatives considered:** Flat file on disk — rejected because it requires filesystem access and introduces race conditions under concurrent writes; SQLite — rejected as an unnecessary new dependency.

### Reserved keyspace `__hmock_internal:*`

Admin persistence writes to `__hmock_internal:*`. Allowing `redisDo` to touch these keys would let templates accidentally overwrite or expose internal state. The simplest mitigation is a prefix check in the `redisDo` wrapper that raises a template render error before executing the command.

### Eventual reload via polling

After a mutating admin request, the primary server's active mock set must reflect the change within a bounded window. The cleanest approach given the single-file architecture is a short-interval background thread that re-reads Redis and rebuilds the in-memory mock list, capped at a small interval (e.g., ≤1 s). This avoids adding IPC, signals, or cross-thread locking beyond a simple swap of an atomic reference.

**Alternatives considered:** Immediate synchronous reload on every admin call — rejected because it couples the admin handler's latency to the full reload cost; push via threading.Event — viable but adds complexity without meaningful benefit for the expected reload frequency.

### Mock merge order

On startup: filesystem mocks are loaded first in sorted order, then API-persisted base mocks, then each template set in set-key sorted order. Last loaded wins on key conflict — consistent with the existing duplicate-key rule. This means API mocks can override filesystem mocks, and template sets can override both.

## Risks / Trade-offs

- **In-memory Redis drops admin mocks on restart** → Documented behavior; users who need persistence across restarts must configure `HM_REDIS_TYPE=redis`.
- **Reload window introduces a brief inconsistency window** → Acceptable for test orchestration; the window is bounded and small.
- **No auth on admin port** → Admin port should not be exposed externally; this matches the tool's local/test-environment positioning.
- **`__hmock_internal:*` keyspace block is enforced only in `redisDo`** → Direct Redis access outside of templates is unaffected, which is correct.

## Migration Plan

- Feature is additive; no changes to existing mock-serving behavior.
- Admin server is enabled by default (`HM_ADMIN_HTTP_ENABLED=true`) but runs on a separate port, so no existing integration is affected.
- To disable, set `HM_ADMIN_HTTP_ENABLED=false`.
