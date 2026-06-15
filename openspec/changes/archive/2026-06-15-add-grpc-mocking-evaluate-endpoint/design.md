## Context

`hmock.py` currently loads YAML behavior definitions, resolves inheritance and file-backed payloads, builds channel-specific template contexts, and executes matched actions for HTTP, Kafka, and AMQP. The admin server exposes mutation endpoints, while broker handling reuses the same behavior/action model with channel-specific matchers.

This change adds a fourth inbound channel, gRPC, and a dry-run evaluation endpoint that exercises the shared matching, condition, ordering, and rendering code without executing side effects.

## Goals / Non-Goals

**Goals:**
- Add optional gRPC serving over HTTP/2 cleartext with no TLS.
- Decode inbound protobuf requests to JSON and encode rendered JSON replies back to protobuf using configured descriptor-set files.
- Match gRPC behaviors by fully-qualified service and method.
- Expose gRPC service, method, payload, and metadata in templates.
- Add an admin dry-run endpoint that validates one mock and simulated context, reports matcher and condition results, and renders safe action previews.

**Non-Goals:**
- Do not add TLS, reflection, streaming RPCs, or automatic descriptor discovery.
- Do not execute outbound HTTP, Redis, Kafka, AMQP, sleep, or gRPC side effects from `/api/v1/evaluate`.
- Do not change existing HTTP, Kafka, or AMQP execution semantics.

## Decisions

### Use descriptor sets as the protobuf source of truth

Load paths from `HM_GRPC_DESCRIPTOR_SET_PATHS`, resolving relative paths against `HM_TEMPLATES_DIR`, and build an in-memory registry keyed by fully-qualified service and method.

Alternatives considered:
- Source `.proto` compilation at startup: more flexible, but adds import path and compiler complexity.
- gRPC reflection: convenient against live servers, but this mock server must run independently.

### Keep gRPC optional and fail fast only when needed

When `HM_GRPC_ENABLED=false`, no gRPC server or descriptor parsing is needed. When gRPC is enabled and loaded behaviors use `expect.grpc` or `reply_grpc`, startup fails if descriptors are missing, unreadable, invalid, or do not describe the configured service/method messages. When gRPC is enabled but loaded behaviors do not use gRPC fields, startup succeeds without descriptor configuration.

Alternatives considered:
- Always require descriptors when gRPC is enabled: simpler validation, but it prevents enabling the port before gRPC mocks are added.
- Defer descriptor errors to request time: easier startup, but produces harder-to-debug runtime failures.

### Add gRPC as a first-class channel beside broker handling

Represent gRPC request metadata separately from HTTP and broker request info, then build a channel context with `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`. gRPC matching uses first-match wins, aligning with HTTP behavior selection rather than Kafka/AMQP multi-match execution.

Alternatives considered:
- Treat gRPC as HTTP path matching: this would leak transport details and make service/method matching less explicit.
- Reuse broker matching: it would fit non-response side effects but not request/response gRPC semantics.

### Factor dry-run evaluation through shared render helpers

Add internal helpers that validate one definition, construct the simulated channel context, check channel-specific matching before condition rendering, sort actions by effective `order`, and render only supported preview action results. The endpoint returns `reply_http` and `publish_kafka` previews and intentionally omits every other action type.

Alternatives considered:
- Invoke normal execution with fake adapters: risky because Redis/template functions and outbound adapters could still perform side effects.
- Implement endpoint-specific rendering from scratch: safer initially, but likely to drift from real execution behavior.

## Risks / Trade-offs

- Protobuf support adds dependency and framing complexity. Mitigation: keep descriptor loading isolated behind a small registry API and cover it with unit tests using generated descriptor fixtures.
- Python's standard `http.server` does not support HTTP/2. Mitigation: introduce a gRPC-capable serving dependency or adapter only when gRPC is enabled.
- Descriptor/service mismatches can fail startup. Mitigation: include clear validation errors naming the missing service, method, or message type.
- Dry-run output can drift from actual execution. Mitigation: share body/header/topic/payload rendering helpers with normal action execution.
- Evaluation intentionally omits most action previews. Mitigation: document omitted side-effecting actions by returning only the supported `actions_performed` result types.

## Migration Plan

Existing deployments remain unchanged because gRPC is disabled by default and `/api/v1/evaluate` is additive. Deploy the new code, then opt in to gRPC by setting `HM_GRPC_ENABLED=true` and, for gRPC behaviors, `HM_GRPC_DESCRIPTOR_SET_PATHS`.

Rollback is to disable `HM_GRPC_ENABLED` or deploy the prior version. Existing mock definitions without gRPC fields continue to load.

## Open Questions

- Which concrete Python gRPC/HTTP2 stack should be used in implementation, given the current single-file architecture?
- Should future evaluate responses include dry-run result types for AMQP, Redis, outbound HTTP, sleep, or gRPC replies?
