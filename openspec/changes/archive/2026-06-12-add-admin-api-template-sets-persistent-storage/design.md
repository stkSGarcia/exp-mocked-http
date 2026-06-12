## Context

`hmock.py` is a compact, dependency-light Python mock server that loads YAML definitions from `HM_TEMPLATES_DIR`, validates them, and serves requests from an in-memory behavior list. It already owns a Redis-compatible adapter boundary for stateful template helpers and actions, which is the natural place to persist API-added mocks without adding a separate database.

This change adds a second HTTP surface for admin operations. The admin surface must coexist with filesystem mocks, preserve runtime-added mocks across process restarts, isolate named template sets from the base API-added collection, and keep internal storage invisible to user templates.

## Goals / Non-Goals

**Goals:**
- Start an admin HTTP server by default, configurable independently from the mock server.
- Accept, validate, persist, list, and delete API-added mock definitions through `/api/v1`.
- Persist base API-added mocks and named template sets in the configured Redis backend under reserved internal keys.
- Load filesystem mocks, persisted base mocks, and persisted template sets into one active snapshot using last-loaded-wins duplicate handling.
- Make admin mutations visible to subsequent mock requests within a bounded reload window.
- Prevent user-facing `redisDo` calls and rendered `redis` actions from touching `__hmock_internal:*`.

**Non-Goals:**
- Add authentication or authorization to the admin API.
- Expose partial update operations for individual template-set members.
- Delete or rewrite filesystem-loaded mocks from admin endpoints.
- Implement persistence outside the existing Redis adapter boundary.
- Change template syntax, behavior matching semantics, or the supported user Redis command set.

## Decisions

1. Run the admin API as a separate `ThreadingHTTPServer`.

   The mock server keeps serving on `HM_HTTP_HOST`/`HM_HTTP_PORT`; the admin server listens on `HM_ADMIN_HTTP_HOST`/`HM_ADMIN_HTTP_PORT` when `HM_ADMIN_HTTP_ENABLED` is true. Both servers share one runtime state object containing configuration, logger, Redis store, and the active behavior snapshot.

   Alternative considered: route admin endpoints through the existing mock server. That would avoid a second listener, but it would mix admin paths with mocked paths and make it possible for user mocks to shadow admin endpoints.

2. Store admin-managed definitions as JSON under reserved Redis keys.

   Use `__hmock_internal:templates` for the base API-added collection and `__hmock_internal:template_sets:<setKey>` for named sets. Each value stores the submitted list of mock definition objects for that collection. Internal persistence helpers use a private Redis call path that bypasses the user keyspace guard.

   Alternative considered: store one Redis hash field per template key. Whole-collection JSON is simpler for create/replace/delete-all semantics, keeps submitted order stable, and is adequate for the expected mock-definition sizes.

3. Build active mocks from ordered definition sources.

   Loading should read filesystem definitions first, then persisted base API-added definitions, then persisted template sets in deterministic `setKey` order. Existing duplicate-key handling remains the conflict rule: later definitions replace earlier ones and emit the existing warning. Template sets stay isolated in storage even though their definitions join the active mock set.

   Alternative considered: give each template set an explicit priority. The checkpoint does not define priorities, so deterministic key order avoids hidden state while preserving last-loaded-wins behavior.

4. Validate before persistence and reload after mutation.

   Admin POST endpoints parse request JSON as a list of mock definition objects, validate the candidate active set, then write the submitted collection to Redis and reload the active snapshot under a lock before returning `200 OK`. DELETE endpoints update storage and reload before returning success. This makes the reload window bounded by the synchronous admin request path.

   Alternative considered: write first and let a background reload loop pick up changes. That would satisfy eventual visibility, but it would make validation failures harder to keep out of persistent storage and would leave tests waiting on timing.

5. Guard the internal Redis keyspace at the user-facing Redis boundary.

   `redisDo` and rendered `redis` action commands must parse the target key and reject any command that targets `__hmock_internal:*` before executing against Redis. The rejection should raise a `TemplateError`/`RedisError` so conditions, responses, and Redis action rendering follow existing render-error behavior. Internal persistence code uses a separate helper so admin storage remains functional.

   Alternative considered: rely on naming convention only. That would allow mocks to corrupt admin state, so an enforced guard is necessary.

## Risks / Trade-offs

- No admin authentication means the admin port is sensitive. Mitigation: keep the listener configurable and allow `HM_ADMIN_HTTP_ENABLED=false`.
- Whole-collection JSON writes are coarse grained. Mitigation: admin operations replace full submitted collections by design, and the collections are expected to be test-sized.
- Reloading synchronously can add latency to admin mutations. Mitigation: mock requests receive a fully validated active snapshot immediately after the admin response, and mutation volume is expected to be low.
- Template set merge ordering is deterministic but implicit. Mitigation: document set-key ordering in tests and keep storage isolation independent of active merge order.
- Internal key detection must be command-aware. Mitigation: apply the guard after command parsing and before execution so unsupported or malformed commands still fail through the normal Redis error path.
