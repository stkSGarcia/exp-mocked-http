## Context

`hmock.py` currently owns configuration, YAML discovery, definition validation and assembly, Redis access, template rendering, request dispatch, and the mock HTTP server lifecycle. Definitions are loaded once from `HM_TEMPLATES_DIR` into process-global runtime state, while `redisDo` and Redis actions share one configurable backend.

Checkpoint 5 adds a second HTTP surface and makes Redis both user-visible mock state and internal persistence. The design must prevent user templates from modifying internal records, preserve the existing definition schema and last-loaded-wins behavior, and update request-serving state without exposing a partially compiled set.

## Related Work

> **`http-yaml-mock-server/add-http-yaml-mock-server`**: Defines environment configuration, YAML discovery, validation, request matching, and last-loaded duplicate precedence — informs the reuse of one definition pipeline and deterministic source ordering because the original change established declarative filesystem mocks as the runtime source of truth.

> **`http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`**: Defines `Behavior`, `Template`, and `AbstractBehavior` composition, values, inheritance, and action ordering — informs validating and compiling API definitions together with filesystem definitions because cross-definition references must behave identically regardless of source.

> **`http-yaml-mock-server/add-template-helpers-file-backed-bodies`**: Defines shared template helpers and templates-directory-constrained file-backed bodies — informs preserving the current render environment and filesystem path boundary because API-added definitions must not gain a separate rendering or file-access model.

## Goals / Non-Goals

**Goals:**

- Add the configured admin HTTP listener and all checkpoint 5 endpoints.
- Persist base API definitions and isolated named sets through the configured Redis backend.
- Compile one deterministic merged definition collection and swap it into request-serving state atomically.
- Restore persisted definitions at startup and synchronously reload after successful mutations.
- Prevent `redisDo` from reading, writing, deleting, or enumerating the reserved internal namespace.
- Keep endpoint and persistence logic testable without requiring a real Redis service.

**Non-Goals:**

- Authentication, authorization, TLS, or network policy for the admin listener.
- Version history, partial patch operations, per-definition set deletion, or cross-process notifications.
- A new database, Redis client dependency, or multi-process consistency protocol.
- Changing the existing mock definition schema or template language.

## Decisions

### Use the existing Redis backend through an internal persistence adapter

Add a small persistence layer in `hmock.py` that calls `RedisBackend.execute` directly for internal records:

- `__hmock_internal:templates` stores the base API collection as JSON.
- `__hmock_internal:template_sets` is a Redis hash whose fields are set keys and whose values are JSON definition arrays.

Direct backend calls distinguish trusted server persistence from user-authored `redisDo`. JSON retains submitted object structure and works with both `MemoryRedisBackend` and `ExternalRedisBackend` without a new dependency. A Redis hash provides natural set isolation through `HSET`, `HGETALL`, and `HDEL`.

Alternative considered: one Redis key per set. That makes enumeration dependent on `KEYS` and complicates deterministic loading and cleanup.

### Normalize admin payloads before validation

Admin POST handlers parse JSON and normalize either one definition object or an array of definition objects to a list. They validate a complete candidate state before persistence, return normalized arrays on success, and return JSON `{"error":"..."}` with `400 Bad Request` for malformed JSON or invalid definitions.

The candidate is assembled through the same validation, inheritance, template registration, action preparation, and duplicate handling used by filesystem loading _(see `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`)_. Failed validation leaves persistence and active runtime state unchanged.

Alternative considered: validate each submitted object independently. That misses inheritance, duplicate, named-template, and file-backed failures that appear only when the full collection is compiled.

### Define deterministic source order

Build the merged input in this order:

1. Filesystem definitions in existing sorted file and document order.
2. Base API definitions in persisted list order.
3. Named template sets ordered lexicographically by set key, preserving definition order inside each set.

The existing assembly pipeline then applies last-loaded-wins by definition key _(see `http-yaml-mock-server/add-http-yaml-mock-server`)_. `GET /api/v1/templates` returns the effective raw definition for each winning key, including `Template` and `AbstractBehavior` objects, rather than only request-matchable behaviors.

Alternative considered: make filesystem definitions always override API definitions. That conflicts with the existing last-loaded-wins contract and makes runtime administration unable to replace a filesystem mock.

### Compile and swap runtime state atomically

Represent runtime state as the effective raw definitions, compiled behaviors, and named templates protected by an `RLock`. Refactor assembly so it returns compiled behaviors and named templates without mutating globals during validation; install the complete result only after compilation succeeds.

Mock request dispatch takes a stable state snapshot. Admin mutations execute under the mutation lock: read stored collections, construct and compile the candidate, persist the changed collection, and install the compiled state before returning success. This synchronous reload makes changes visible by response completion, satisfying the bounded reload requirement without a polling thread.

Alternative considered: background periodic reload. It introduces timing-sensitive tests, stale windows, and failure recovery complexity without providing a benefit for this single-process server.

### Run a second standard-library HTTP server

Add an `AdminRequestHandler` and start a `ThreadingHTTPServer` on the configured admin host and port in a daemon thread while the existing mock server remains the main serving loop. Both listeners share the persistence adapter, runtime state, and Redis backend. If admin HTTP is disabled, no admin server or thread is created.

The process shutdown path closes both servers. Keeping `BaseHTTPRequestHandler` avoids adding a web framework and follows the existing request/response model.

Alternative considered: route admin paths through the mock listener. A separate listener is explicitly required and allows independent exposure through host, port, and enablement settings.

### Guard reserved keys at the `redisDo` boundary

After `parse_redis_command`, identify key-bearing arguments for every Redis command supported by the in-memory backend. Reject a key or pattern beginning with `__hmock_internal:` before invoking `_REDIS_BACKEND.execute`. The raised error is converted by `render` into `TemplateRenderError`.

Internal persistence bypasses `redisDo` and calls the backend adapter directly. Existing declarative `redis` actions continue using the current command path; the checkpoint restriction is specifically applied to `redisDo`.

Alternative considered: enforce the guard inside all Redis backends. That would also block trusted persistence and require a bypass flag in the backend abstraction.

## Risks / Trade-offs

- [Persistence succeeds but runtime installation unexpectedly fails] -> Compile the full candidate before writing, keep installation to an in-memory assignment under lock, and return an error if persistence itself fails.
- [Multiple processes sharing Redis can overwrite each other's collections] -> This change provides persistence, not distributed transactions; document single-writer expectations and always rebuild from Redis before each mutation.
- [Named-set precedence depends on set key] -> Sort set keys lexicographically and test the rule so results do not depend on Redis hash iteration order.
- [Large definition collections increase mutation latency] -> Synchronous full compilation favors correctness; measure before introducing incremental compilation.
- [Admin listener is enabled without authentication] -> Preserve the requested default but keep it independently bindable and disableable for deployment network controls.
- [Direct access to process-global state can race] -> Centralize snapshots and swaps behind the runtime-state lock and avoid incremental mutation of global lists or maps.

## Migration Plan

1. Deploy the updated process with no existing internal keys; startup treats missing persistence records as empty collections.
2. Existing filesystem-only behavior remains active because filesystem definitions are still loaded first through the same pipeline.
3. API mutations begin creating `__hmock_internal:templates` and `__hmock_internal:template_sets` records.
4. Rollback can ignore those records because older versions do not read them; deleting the two internal records removes persisted API state if cleanup is required.

## Open Questions

None. The checkpoint leaves the exact reload duration unspecified; synchronous installation before a successful mutation response provides the strongest bounded behavior.
