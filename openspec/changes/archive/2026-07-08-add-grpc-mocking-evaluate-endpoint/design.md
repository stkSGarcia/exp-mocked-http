## Context

`hmock.py` currently centralizes configuration loading, mock validation, template rendering, HTTP request matching, broker matching, action execution, and the admin API. Kafka and AMQP already extend the original HTTP-only matcher model with channel-specific context builders and broker services, while `tests/test_hmock.py` covers most behavior at the module and HTTP API level.

This change adds a second serving protocol for gRPC and an admin-style dry-run evaluation endpoint. The two features share validation, matching, template context construction, and action rendering concerns, so implementation should factor common dry-run helpers from existing execution paths rather than duplicating matcher logic.

## Related Work

**`template-rendering/add-admin-api-template-storage`**: Documents template execution contexts and restrictions — informs the dry-run rendering boundary because evaluation must render templates without changing external state.

**`http-behavior-mocking/add-stateful-actions`**: Specifies ordered action execution after behavior selection — informs the dry-run action planner because `/api/v1/evaluate` must sort actions by `order` without executing them.

**`internal-keyspace-protection/add-admin-api-template-storage`**: Captures protected internal state boundaries — informs the decision to keep evaluation side-effect free because template/state helpers must not mutate protected runtime state during previews.

**`http-behavior-mocking/add-template-helpers-file-backed-bodies`**: Adds file-backed payload loading and templated response bodies — informs `reply_grpc.payload_from_file` behavior because gRPC should reuse the existing safe file-resolution pattern.

**`template-rendering/add-http-yaml-mock-server`**: Defines request template context and HTTP response rendering conventions — informs gRPC and simulated-context builders because each channel should expose equivalent values through one rendering model.

## Goals / Non-Goals

**Goals:**

- Add `GrpcConfig` to `Config` and parse `HM_GRPC_ENABLED`, `HM_GRPC_PORT`, `HM_GRPC_HOST`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` in `hmock.py`.
- Extend mock validation so `expect.grpc` is a supported matcher and `reply_grpc` is a supported action.
- Decode gRPC request frames to JSON using descriptor sets, expose gRPC template context, and encode rendered JSON replies back to protobuf frames.
- Add `POST /api/v1/evaluate` to the admin API path in `hmock.py` with strict request validation and side-effect-free rendering.
- Add tests in `tests/test_hmock.py` for config, validation, gRPC matching/context/reply rendering helpers, and evaluate endpoint behavior.

**Non-Goals:**

- TLS, mTLS, or HTTP/2 over TLS support for gRPC.
- Streaming gRPC RPCs; this design targets unary request/response behavior.
- Executing `reply_grpc`, `publish_amqp`, Redis, sleep, webhook, or other non-listed actions from the evaluate endpoint.
- Adding `omctl.py` commands for evaluate unless implementation finds a small helper necessary.

## Decisions

### Use a small gRPC service layer beside existing servers

Add a `HMockGRPCServer`/service wrapper in `hmock.py` that is built from the same registry, logger, Redis store, and publisher references used by HTTP and broker services. `main()` should start it only when `config.grpc.enabled` is true, and shutdown should follow the same lifecycle as the HTTP/admin/broker services.

Alternative considered: multiplex gRPC through `HMockHTTPServer`. That would entangle HTTP/1 handler assumptions with HTTP/2 framing and make the existing request handler harder to reason about.

### Keep protobuf handling isolated

Create descriptor-loading and message-conversion helpers that accept configured service/method pairs and descriptor-set paths. Relative paths resolve from `Config.templates_dir`, matching existing file-backed payload behavior _(see `http-behavior-mocking/add-template-helpers-file-backed-bodies`)_. Startup validation should only require readable descriptors when enabled gRPC behaviors need protobuf decoding or encoding.

Alternative considered: accept raw bytes or JSON-only gRPC payloads. That would avoid descriptors but would not satisfy real gRPC framing or response encoding requirements.

### Extend the existing behavior model

Add `grpc_service` and `grpc_method` fields to the `Behavior` dataclass and allow exactly one supported matcher among `http`, `kafka`, `amqp`, and `grpc`. Keep first-match wins for gRPC by scanning registry behaviors in order, mirroring the HTTP path.

Alternative considered: model gRPC as HTTP path matching against `/<service>/<method>`. That would leak transport details into mock definitions and skip the explicit `expect.grpc` contract.

### Reuse template context conventions

Build `build_grpc_template_context(service, method, payload_json, headers, behavior, redis_store)` alongside the existing HTTP/Kafka/AMQP context builders. It should expose `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`, while preserving `.Values`, named templates, and permitted helper functions _(see `template-rendering/add-http-yaml-mock-server`)_.

Alternative considered: embed gRPC values under one `.GRPC` object. The checkpoint specifies top-level context fields, and matching the existing top-level channel convention keeps templates consistent.

### Implement evaluate as a dry-run execution path

Add an evaluation function that validates the request, validates the embedded mock using the normal schema, builds the selected channel context, checks the channel matcher, renders the condition, then walks sorted actions without calling `execute_actions`. It should call smaller render helpers for `reply_http` and `publish_kafka` so returned action results match real rendering while avoiding publishers, Redis mutations, sleeps, and webhooks _(see `http-behavior-mocking/add-stateful-actions` and `internal-keyspace-protection/add-admin-api-template-storage`)_.

Alternative considered: run `execute_actions` with fake adapters. That would be brittle for future side-effecting actions and would make it too easy to accidentally perform work during evaluation.

## Risks / Trade-offs

- Descriptor loading can add a non-stdlib dependency or substantial reflection code -> keep the dependency isolated and fail with clear validation errors when unavailable or misconfigured.
- HTTP/2 cleartext support may not fit the current `http.server` stack -> use a dedicated gRPC-capable server layer rather than stretching `ThreadingHTTPServer`.
- Dry-run results may drift from real action rendering -> share low-level render helpers for `reply_http` and `publish_kafka` rather than creating parallel formatting logic.
- Template helpers such as `redisDo` can mutate state while rendering -> evaluation should use a dry-run rendering context that rejects side-effecting helpers or routes them to a non-mutating stub.
- gRPC payload conversion errors can be hard to diagnose -> include service, method, and descriptor path context in validation/runtime errors.

## Migration Plan

The change is additive. Existing deployments keep gRPC disabled by default and existing HTTP/Kafka/AMQP behavior remains unchanged. Rollback is to set `HM_GRPC_ENABLED=false` and avoid calling `/api/v1/evaluate`; no data migration is required.

## Open Questions

- Which protobuf reflection library will be used in the implementation environment if the standard library is insufficient?
- Should `/api/v1/evaluate` live only on the admin server or also on the public mock HTTP server? The checkpoint names an API endpoint but the existing admin API is the safer default.
