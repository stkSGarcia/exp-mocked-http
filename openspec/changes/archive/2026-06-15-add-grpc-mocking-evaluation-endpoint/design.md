## Context

`hmock.py` currently loads YAML mock definitions into effective behaviors, renders Go-template-like expressions against HTTP/Kafka/AMQP contexts, executes ordered actions, and exposes admin APIs through a separate HTTP server. gRPC support adds a new request transport with protobuf decoding/encoding, while the evaluation endpoint needs the same matcher, condition, ordering, and rendering semantics without opening broker connections or performing side effects.

The codebase is a compact Python implementation with tests driving behavior directly through module functions and local servers. The design should preserve the existing first-class script layout while isolating the new protobuf/gRPC mechanics behind small helper types so the core matching/evaluation rules remain shared.

## Goals / Non-Goals

**Goals:**
- Add opt-in cleartext HTTP/2 gRPC serving without changing existing HTTP, admin, Kafka, or AMQP defaults.
- Support `expect.grpc` and `reply_grpc` with descriptor-backed protobuf-to-JSON and JSON-to-protobuf conversion.
- Reuse existing behavior validation, condition rendering, action ordering, file-backed payload loading, and template functions.
- Add `POST /api/v1/evaluate` for one mock definition and simulated channel context with no side effects.
- Keep evaluation results deterministic and limited to explicitly supported dry-run action result types.

**Non-Goals:**
- TLS, authentication, streaming RPCs, reflection, health checking, or dynamic descriptor discovery.
- A full gRPC admin surface beyond the mock server listener itself.
- Dry-run execution of Redis, outbound HTTP, AMQP publish, sleep delays, or gRPC replies unless separately specified later.

## Decisions

1. Introduce gRPC-specific configuration on `Config` and parse it from `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
   - Rationale: this follows the existing HTTP/admin/Kafka/AMQP environment pattern and keeps gRPC disabled by default.
   - Alternative considered: always start a gRPC listener and return unavailable for missing descriptors. That would surprise existing users by opening a new port.

2. Resolve relative descriptor-set paths from `HM_TEMPLATES_DIR` and load them only when gRPC is enabled and at least one effective behavior uses `expect.grpc` or `reply_grpc`.
   - Rationale: descriptor validation is required for real gRPC traffic, but configurations that do not use gRPC should not need protobuf files.
   - Alternative considered: validate descriptors during all mock loading. That would make non-gRPC use cases depend on optional gRPC assets.

3. Add a descriptor registry helper that indexes service/method request and response message descriptors by fully-qualified service and method.
   - Rationale: matching is keyed by service/method, and request decoding plus response encoding both need method descriptors.
   - Alternative considered: keep descriptor lookups inline in the gRPC handler. That would duplicate error handling and make testing harder.

4. Model gRPC requests as a new trigger context with `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`.
   - Rationale: this mirrors the existing channel-specific contexts while preserving existing template functions and `.Values`.
   - Alternative considered: convert gRPC requests into HTTP-like context fields. That would obscure protobuf payload semantics and metadata naming.

5. Implement dry-run evaluation as a shared evaluator that returns matcher result, rendered condition, and rendered action results instead of calling side-effect executors.
   - Rationale: evaluation should test the same behavior rules users rely on in production while replacing action execution with pure rendering.
   - Alternative considered: build separate endpoint-specific matching and rendering logic. That would drift from runtime behavior.

6. Restrict dry-run action results to `reply_http` and `publish_kafka` initially.
   - Rationale: the checkpoint defines those result types and explicitly says other action types stay dry-run but omitted.
   - Alternative considered: include placeholder results for every action type. That would add response contracts without clear user value.

## Risks / Trade-offs

- New protobuf/gRPC dependency footprint -> Keep dependency usage localized to descriptor registry and gRPC server helpers, with tests covering missing dependency behavior if dependency metadata is added later.
- Unary-only implementation may reject valid streaming service definitions -> Detect streaming methods and return validation/startup errors for configured behaviors until streaming is intentionally supported.
- Descriptor mismatch can fail at request time -> Validate configured service/method pairs at startup when gRPC behaviors are loaded and return clear errors for invalid runtime payloads.
- Dry-run evaluation could accidentally execute template helper side effects such as `redisDo` -> Reuse rendering with the configured Redis guard, but do not run ordered `redis` actions; document and test that only action execution side effects are suppressed.
- Admin endpoint validation could diverge from load-time validation -> Route evaluate requests through the same validation functions used for submitted mock definitions, with extra checks for required simulated channel context.

## Migration Plan

- Add config fields with backward-compatible defaults so existing deployments do not start gRPC unless `HM_GRPC_ENABLED=true`.
- Add schema validation for gRPC fields; existing mocks without gRPC fields continue to load unchanged.
- Add the admin endpoint without changing existing admin routes.
- Rollback is disabling `HM_GRPC_ENABLED` and avoiding the new endpoint; existing mock files remain compatible unless they rely on new gRPC fields.

## Open Questions

- Which concrete Python dependency set will be used for cleartext HTTP/2 serving and dynamic protobuf messages in the implementation environment?
- Should future evaluation responses include omitted action metadata for unsupported dry-run action types, or continue returning only rendered side-effect-free result types?
