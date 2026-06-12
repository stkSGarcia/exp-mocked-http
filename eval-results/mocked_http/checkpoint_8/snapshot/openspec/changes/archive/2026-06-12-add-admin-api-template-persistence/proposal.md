## Why

The mock server currently loads definitions only from the filesystem, so running clients cannot manage mocks dynamically or retain API-created definitions across restarts. An isolated admin surface and persistent storage are needed to support runtime mock management without weakening existing filesystem behavior or exposing internal Redis state.

## Related Work

### Related Changes

- `add-http-yaml-mock-server` established the environment-configured HTTP server, YAML definition loading, validation, and duplicate-key behavior; this change extends that runtime with a separately configured admin server and additional persisted definition sources.
- `add-template-helpers-file-backed-bodies` expanded request-time rendering and file-backed behavior; this change preserves those rendering semantics for definitions submitted through the admin API.
- `add-stateful-actions-redis-http-side-effects` introduced Redis-backed template and action side effects; this change reserves the mock server's internal Redis namespace so user-authored `redisDo` expressions cannot alter persistence records.

### Related Specs

- `http-yaml-mock-server/add-http-yaml-mock-server` implements the core HTTP YAML mock server, including configuration, definition loading, validation, request matching, and last-loaded duplicate precedence. This change reuses its definition schema and extends its loading model to merge persisted and filesystem sources.
- `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering` implements `Behavior`, `Template`, and `AbstractBehavior` composition and validation. The admin API accepts and returns those same mock definition objects without introducing a second schema.
- `http-yaml-mock-server/add-template-helpers-file-backed-bodies` implements the shared template runtime and file-backed response behavior. API-added definitions continue to use that runtime, while filesystem-relative resources remain governed by the existing templates directory.

## What Changes

- Add an independently configurable admin HTTP server with health, template listing, base-template mutation, and named template-set mutation endpoints.
- Persist API-added base templates and named template sets in Redis-backed internal storage, and restore them on process startup.
- Merge filesystem definitions, persisted base templates, and persisted template sets into one active runtime using the existing last-loaded-wins duplicate-key rule.
- Keep base API templates and each named template set isolated for replacement and deletion operations.
- Validate submitted definitions and return endpoint-specific success, validation, missing-resource, and no-content responses.
- Trigger bounded eventual reloads after successful admin mutations so later mock requests observe the resulting active set.
- Reject `redisDo` commands targeting `__hmock_internal:*` before any Redis command executes.

## Capabilities

### New Capabilities

- `admin-template-management`: Configurable admin endpoints, persistent API-managed base templates, isolated named template sets, endpoint responses, and mutation visibility guarantees.

### Modified Capabilities

- `http-yaml-mock-server`: Load and merge persisted definitions with filesystem definitions, preserve duplicate-key precedence across sources, and prevent `redisDo` access to the reserved internal Redis keyspace.

## Impact

- `hmock.py`: configuration, process lifecycle, definition loading, Redis persistence, admin routing, reload coordination, and template Redis command validation.
- `test_hmock.py`: configuration, endpoint, persistence, merge precedence, restart/reload visibility, set isolation, and reserved-keyspace coverage.
- Runtime API: adds an admin listener and `/api/v1` endpoints, enabled by default on `0.0.0.0:9998`.
- Redis: adds internal persistence keys under `__hmock_internal:*`; no new package dependency is expected because Redis integration already exists.
