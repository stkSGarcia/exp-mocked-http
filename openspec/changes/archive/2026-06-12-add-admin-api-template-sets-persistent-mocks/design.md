## Context

`hmock.py` currently loads YAML mock definitions from `HM_TEMPLATES_DIR` once at server startup, validates them into effective behaviors, and stores request-time Redis state in the configured Redis backend. There is no runtime management API, no persisted API-added definitions, and the mock HTTP server keeps a fixed `behaviors` list on the server instance.

This change adds a second HTTP surface for administration, persistent API-added definition storage, named template sets, and reload coordination between the admin server and the mock server. The implementation should preserve the existing filesystem loading and validation rules while making admin-added definitions participate in the same effective behavior/template merge.

## Goals / Non-Goals

**Goals:**
- Start an admin HTTP server when enabled by environment configuration.
- Support health, list, upsert, and delete operations for base API-added templates.
- Support replace and delete operations for named template sets.
- Persist base API-added templates and template sets under the reserved internal Redis keyspace.
- Rebuild active behaviors from filesystem definitions plus persisted definitions after every successful admin mutation.
- Keep template sets isolated by set key while allowing their definitions to participate in the active merged mock set.
- Block user templates from accessing internal persistence keys through `redisDo`.

**Non-Goals:**
- Add authentication or authorization for the admin API.
- Add partial updates inside a template set.
- Change existing mock definition schema rules beyond allowing admin JSON bodies to feed the same validation path.
- Expose filesystem writeback for admin-created mocks.

## Decisions

1. Run a separate `ThreadingHTTPServer` for admin traffic.

The mock server should continue serving on `HM_HTTP_HOST`/`HM_HTTP_PORT`. When `HM_ADMIN_HTTP_ENABLED` is true, `main()` starts an admin server on `HM_ADMIN_HTTP_HOST`/`HM_ADMIN_HTTP_PORT` in a background thread and keeps the mock server as the foreground server. This keeps the request routing surfaces separate and avoids reserving `/api/v1/*` paths on the mock server.

Alternative considered: serve admin endpoints from the mock server. That is simpler, but it would make admin paths unavailable as mockable paths and couple admin failures to request matching.

2. Introduce a shared mock state object.

Replace the static `server.behaviors` ownership with a small thread-safe state object that can atomically return the current behavior list and replace it after reload. Mock request handlers read a snapshot from this state for each request. Admin handlers mutate persistence, rebuild definitions, and then swap in the new validated behavior list.

Alternative considered: mutate `HMockHTTPServer.behaviors` directly. A dedicated state object makes tests and locking clearer and avoids exposing reload internals across handler classes.

3. Store admin definitions in the configured Redis backend under reserved keys.

Persist base API-added mocks at `__hmock_internal:templates` and template sets under a deterministic `__hmock_internal:template_sets:<setKey>` key. Values should be JSON arrays of raw mock definition objects. Storage helpers should validate set keys for non-empty path segment values and use JSON serialization consistently.

Alternative considered: persist admin definitions to files. Redis-backed storage matches the existing backend abstraction and the requested reserved Redis keyspace. External Redis provides durability across real process restarts; the in-memory backend keeps the same semantics for tests and local ephemeral runs.

4. Reuse existing validation and merge behavior.

Admin request bodies should be parsed as JSON arrays of mock definition objects, then passed through the same definition validation, inheritance, template registration, duplicate-key replacement, and effective behavior construction used for filesystem-loaded YAML. The loader should accept raw definition streams from multiple sources in explicit order: filesystem definitions, base API definitions, then template sets in stable set-key order. Existing duplicate-key behavior remains "last loaded wins".

Alternative considered: validate admin definitions separately. A separate path risks schema drift and duplicated edge cases.

5. Use bounded synchronous reload for admin mutations.

After a successful admin mutation, the admin handler should persist the new value, rebuild active behaviors, and swap the state before returning success. This satisfies the bounded eventual-reload requirement with a tight bound: subsequent requests after the admin response observe the update. If rebuild fails, the handler should return `400 Bad Request` for validation failures and keep the previous active state.

Alternative considered: background polling. Polling is more complex, creates a larger visibility window, and complicates tests.

6. Guard internal Redis keys at the template function boundary.

Wrap the `redisDo` callable placed in template context so any command whose key arguments touch `__hmock_internal:*` fails before it reaches the backend. Apply the same guard when rendering `redis` action commands, because rendered Redis actions share the same command execution surface as `redisDo`.

Alternative considered: add checks in each Redis backend. A shared guard keeps memory and external Redis behavior identical and lets persistence helpers use internal keys intentionally without exposing them to templates.

## Risks / Trade-offs

- Admin reload can briefly block the admin request while validation runs -> keep reload synchronous for predictable visibility and rely on the existing small in-process validation cost.
- Persisted invalid data from an older version can prevent startup reload -> log the validation error, fail startup rather than serving a silently partial configuration.
- Template-set ordering affects duplicate-key precedence -> sort set keys lexically for deterministic results and document that later-loaded definitions win.
- The memory Redis backend cannot provide durability across OS process exits -> use the same internal storage API for both backends, with external Redis required for true cross-process persistence.
- Blocking Redis commands by key requires command-aware parsing -> reuse `_parse_redis_command` and maintain an explicit map of key argument positions for the supported command set.

## Migration Plan

1. Extend configuration with admin environment variables and defaults.
2. Add storage helper functions for base templates and template sets under the reserved keyspace.
3. Refactor loading to build behaviors from filesystem definitions plus persisted raw definitions.
4. Add shared mock state and update mock request handling to read behavior snapshots.
5. Add admin request handler and server startup/shutdown wiring.
6. Add Redis internal-key guard for template-accessible commands.
7. Add focused tests for admin endpoints, persistence/reload, set isolation, duplicate precedence, and keyspace blocking.

Rollback is to disable the admin server with `HM_ADMIN_HTTP_ENABLED=false`; existing filesystem-loaded mock behavior remains the baseline path.

## Open Questions

- Should future admin APIs support authentication or network binding defaults that are safer for shared environments?
- Should template set ordering become explicitly configurable if users need precedence beyond lexical set-key order?
