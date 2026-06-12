## Context

`hmock.py` currently loads mock definitions from YAML files at startup/reload time and serves them through one HTTP mock server. It already has validation, inheritance, template registration, ordered action execution, a Redis-compatible backend abstraction, and a `redisDo` helper exposed to templates.

This change adds a second HTTP surface for runtime mock administration. Admin-managed mocks must be validated with the same rules as filesystem mocks, persisted through restarts, and merged into the same active behavior/template set without allowing user templates to overwrite or inspect internal persistence keys.

## Goals / Non-Goals

**Goals:**
- Start an admin HTTP server by default with independent host, port, and enabled configuration.
- Provide admin endpoints for health checks, listing active definitions, adding/updating base API mocks, deleting base API mocks, and replacing/deleting named template sets.
- Persist admin-managed base mocks and named template sets in the configured Redis backend.
- Rebuild the active mock definitions from filesystem, base API mocks, and template sets after mutations within a bounded reload window.
- Protect the reserved internal Redis keyspace from `redisDo`.

**Non-Goals:**
- Add authentication, authorization, or TLS to the admin API.
- Add partial patch semantics for individual fields within a mock definition.
- Persist filesystem-loaded mocks into Redis.
- Expose internal persistence records directly through the public Redis template helper.

## Decisions

1. Run the admin API as a second `ThreadingHTTPServer` sharing the mock server runtime state.

   The existing mock server keeps request handling simple and synchronous. A second server instance avoids mixing admin routes with mocked application routes and allows `HM_ADMIN_HTTP_HOST`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_ENABLED` to be managed independently. The two servers should share a runtime object that owns configuration, Redis, filesystem loader settings, and the active loaded definitions.

   Alternative considered: serve admin routes from the main mock server. That would reduce threads, but it would make mocked routes and operational routes share the same namespace and port.

2. Store admin-managed definitions as JSON in reserved Redis keys.

   Base API mocks should be stored under `__hmock_internal:templates`. Template sets should be stored separately under a reserved prefix such as `__hmock_internal:template_sets:<setKey>`. Each value should contain the submitted mock-definition array for that collection. Keeping base and set storage separate makes delete operations precise and keeps set replacement atomic at the collection level.

   Alternative considered: store one Redis key per mock key. That would make individual deletes simple, but it would make set replacement and deterministic set isolation more complex.

3. Treat the active definition stream as filesystem, then base API mocks, then template sets sorted by set key.

   Filesystem definitions remain the base layer. API-added base mocks override filesystem mocks with matching keys. Template sets are loaded after the base collection in lexicographic `setKey` order, preserving declaration order inside each source. This gives the existing duplicate-key rule a deterministic meaning: last loaded wins.

   Alternative considered: order template sets by last update time. That would make behavior depend on mutation history and would be harder to reproduce after restart.

4. Validate before persistence and rebuild active definitions after every mutation.

   Admin `POST` handlers should parse JSON mock-definition arrays, run the existing definition validation/load path against the candidate collection, and persist only valid input. After persistence succeeds, the runtime should schedule or perform a reload that reads filesystem definitions and persisted collections into one active set. The visibility contract is bounded eventual consistency rather than same-handler synchronous matching, so implementations can use a short debounce window while tests can poll within the bound.

   Alternative considered: append new definitions directly to the in-memory active list. That would be faster for a single request but would create a second merge path that can drift from startup behavior.

5. Block `redisDo` access to the internal keyspace before command execution.

   The Redis adapter or template helper boundary should reject `redisDo` commands whose key or key-pattern arguments target `__hmock_internal:*`. The rejected operation should raise the same kind of render error as other unsupported Redis operations, and the Redis command must not be sent to either the memory backend or an external Redis server.

   Alternative considered: rely on obscure internal key names. That would not protect persisted mocks from deliberate or accidental template access.

## Risks / Trade-offs

- Admin API has no authentication -> keep it independently bindable and disable-able through environment configuration.
- Redis persistence can fail during admin mutations -> return a 5xx error for persistence failures and leave the previous active set in place.
- Reload debounce can make tests race the active set -> define a small bounded window and provide polling-friendly semantics.
- JSON persistence may preserve only JSON-compatible values -> admin input is JSON, while filesystem YAML remains loaded through the existing filesystem path.
- Template sets with duplicate mock keys can override each other -> deterministic set-key ordering makes the result reproducible and testable.

## Migration Plan

Existing deployments continue to serve filesystem mocks on the existing mock HTTP port. The admin server starts by default on `0.0.0.0:9998`; deployments that do not want it can set `HM_ADMIN_HTTP_ENABLED=false`. Rollback requires deleting or ignoring the reserved internal Redis keys if admin-managed mocks should no longer be loaded.

## Open Questions

- What exact reload-window duration should be used for polling tests and production documentation?
- Should future work add authentication or an allowlist for admin operations?
