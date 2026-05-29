## Context

`hmock.py` is a single-file mock server with four concurrent channels: HTTP (`MockRequestHandler`), Kafka (async consumer loop), AMQP (async consumer loop), and Admin (`AdminRequestHandler`). All channels share a global behavior list loaded via `build_mock_set()`. Each channel owns its matching logic (`find_behavior`, `find_all_behaviors_for_kafka`, `find_all_behaviors_for_amqp`) and action execution (`execute_actions`). Jinja2 renders all templates into a typed context dict.

Adding gRPC follows the same pattern: a new server class, new env-var config, new `expect.grpc` / `reply_grpc` schema fields, and a new matching function. The evaluate endpoint lives in the existing `AdminRequestHandler`.

## Goals / Non-Goals

**Goals:**
- Run a gRPC server on a configurable port using HTTP/2 cleartext (no TLS).
- Match unary gRPC calls by `(service, method)` using first-match wins, same policy as HTTP.
- Decode inbound protobuf via descriptor-set files; expose as `.GRPCPayload` JSON string in template context.
- Encode protobuf responses from rendered JSON via the same descriptor-set registry.
- Validate descriptor-set presence at startup when any loaded behavior references gRPC fields.
- Add `POST /api/v1/evaluate` that validates a mock definition + simulated context and returns rendered results with no side effects.

**Non-Goals:**
- gRPC streaming (client-streaming, server-streaming, bidirectional).
- TLS / mTLS for gRPC.
- gRPC reflection (server reflection API).
- Evaluate endpoint returning results for `reply_grpc`, `publish_amqp`, `send_http`, `sleep`, or `redis` action types (checkpoint specifies only `reply_http` and `publish_kafka`).

## Decisions

### gRPC library: `grpcio` + `protobuf`

Use `grpcio` (Python gRPC runtime) together with the `protobuf` Python package. `grpcio` provides the HTTP/2 server, length-prefixed framing, and a `GenericMethodHandler` / `ServiceRpcHandlers` interface that lets us intercept all calls without code-gen. `protobuf`'s `descriptor_pool` + `MessageFactory` (or `descriptor_pb2.FileDescriptorSet`) allows dynamic message construction from `.pb` descriptor-set files, which is the standard approach for schema-free gRPC proxies.

Alternative considered: `grpclib` (pure-Python async). Rejected because it is less mature and would require adapting the existing threading model; `grpcio`'s blocking server fits the same thread-per-channel pattern used by `HTTPServer`.

### Descriptor-set loading

Load descriptor-set files at startup via `google.protobuf.descriptor_pool.DescriptorPool` and `google.protobuf.descriptor_pb2.FileDescriptorSet`. Relative paths are resolved from `TEMPLATES_DIR`. Build a registry mapping `"fully.qualified.ServiceName/MethodName"` → `(input_descriptor, output_descriptor)` for fast lookup at request time.

Fail startup (raise and exit) if `HM_GRPC_ENABLED=true` and any loaded behavior's `expect.grpc` or `reply_grpc` references a `(service, method)` pair that cannot be resolved from the registry. Allow startup without descriptor-set config when no loaded behavior uses gRPC fields (gRPC server still starts; it will return UNIMPLEMENTED for any call that arrives without a matching behavior).

### gRPC server threading model

Run the gRPC server with `grpcio`'s blocking `server.start()` + `server.wait_for_termination()` in its own daemon thread, matching how `HTTPServer.serve_forever()` is used for HTTP and Admin. The `GenericRpcHandler` looks up the current behavior list via the same shared `_behaviors` global.

### Evaluate endpoint: dry-run action execution

Introduce a `dry_run_actions()` function that mirrors `execute_actions()` but replaces real side effects with result collection:

- `reply_http`: renders status, headers, body and returns a `reply_http_action_performed` dict.
- `publish_kafka`: renders topic and payload and returns a `publish_kafka_action_performed` dict.
- All other action types (sleep, redis, send_http, publish_amqp, reply_grpc): skipped and omitted from `actions_performed`.

Matching and condition evaluation reuse existing `find_behavior` logic decomposed into helpers: channel-specific match check → condition render → action evaluation.

### Evaluate endpoint: channel dispatch

The `context` object may contain `http_context`, `kafka_context`, `amqp_context`, and/or `grpc_context`. The endpoint inspects which matcher is declared in `mock.expect` and verifies that the corresponding `*_context` key is present. It then builds the template context using the same per-channel context-builder pattern (`build_context`, or equivalent for each channel).

## Risks / Trade-offs

- **`grpcio` startup cost**: importing `grpcio` adds ~50 ms to cold start even when `HM_GRPC_ENABLED=false`. Mitigation: lazy-import `grpcio` inside the gRPC startup path so it is only loaded when the feature is enabled.
- **Dynamic protobuf decode complexity**: protobuf `Any`-typed fields and `oneof` variants need careful handling. Mitigation: use `MessageToJson` from `google.protobuf.json_format`; document that nested `Any` fields may not round-trip cleanly.
- **Single-file growth**: `hmock.py` is already ~1700 lines; gRPC adds ~200 more. Mitigation: group all gRPC logic under a clearly delimited section comment, consistent with the existing AMQP/Kafka sections.
- **Evaluate endpoint schema drift**: if mock validation rules change, the evaluate endpoint's inline validation must stay in sync. Mitigation: reuse `_validate_behavior()` directly rather than duplicating checks.

## Migration Plan

1. Add `grpcio` and `protobuf` to `pyproject.toml` dependencies.
2. Implement gRPC config constants, descriptor registry, and server thread.
3. Add `expect.grpc` / `reply_grpc` to schema and validation.
4. Add `POST /api/v1/evaluate` handler to `AdminRequestHandler`.
5. Add/extend tests in `test_hmock.py` (unit tests for matcher and evaluate; integration tests for gRPC call flow if `grpcio-testing` or a test channel is available).
6. No migration needed for existing deployments — all new env vars default to disabled/empty.

## Open Questions

- Should the evaluate endpoint support `reply_grpc` action rendering in the future? The checkpoint explicitly excludes it, but it may be a natural follow-on.
- Should gRPC behaviors also support `condition` filtering (same as HTTP/Kafka/AMQP)? The spec says first-match wins but doesn't explicitly mention conditions — assume yes, consistent with other channels.
