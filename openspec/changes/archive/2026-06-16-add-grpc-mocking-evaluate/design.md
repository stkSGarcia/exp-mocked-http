## Context

`hmock.py` currently owns configuration, mock definition validation, YAML loading, template rendering, HTTP request matching, broker dispatch, action execution, and admin HTTP routes in one module. HTTP behavior matching uses `Behavior.pattern`, broker matching uses `KafkaExpectation` and `AMQPExpectation`, and action execution renders templates through a shared context before executing side effects.

This change adds a new transport surface and a dry-run endpoint, so the implementation should extend the existing data model and rendering paths without changing current HTTP, Kafka, or AMQP behavior.

## Related Work

> **`http-behavior-mocking/add-http-yaml-mock-server`**: Defines request matching, first eligible behavior selection, condition routing, action ordering, and response defaults — informs the gRPC service/method matcher and dry-run reply projection because gRPC should behave like another channel in the same mock model. _(see `http-behavior-mocking/add-http-yaml-mock-server`)_

> **`template-rendering/add-reusable-templates-inheritance-values-action-ordering`**: Defines shared template context and rendering behavior — informs adding `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader` to the existing render context because conditions and action fields should render through the same engine. _(see `template-rendering/add-reusable-templates-inheritance-values-action-ordering`)_

> **`http-behavior-mocking/add-stateful-actions`**: Defines ordered action execution for side-effecting actions — informs the evaluator's action sorting and omission of unsupported side-effect action results because dry-run must describe only renderable outcomes without executing actions. _(see `http-behavior-mocking/add-stateful-actions`)_

## Goals / Non-Goals

**Goals:**

- Add gRPC config fields and descriptor-set path handling to `Config` and `load_config`.
- Extend `Behavior` with a `GrpcExpectation` and validate `expect.grpc` plus `reply_grpc`.
- Add descriptor loading helpers that can resolve service/method input and output message descriptors from configured descriptor sets.
- Add an HTTP/2 cleartext gRPC server path that decodes length-prefixed protobuf requests, matches behaviors, renders conditions/actions, and returns length-prefixed protobuf replies with gRPC headers.
- Add a side-effect-free evaluator used by `POST /api/v1/evaluate`.
- Cover config, validation, matching, rendering, response projection, and endpoint behavior in `tests/test_hmock.py`.

**Non-Goals:**

- TLS for gRPC.
- gRPC streaming RPC support.
- Executing dry-run side effects for Redis, outbound HTTP, AMQP, Kafka, sleep, or gRPC replies.
- Replacing the current single-file module layout.

## Decisions

1. Extend the existing `Behavior` model instead of introducing a separate gRPC behavior type.

   `GrpcExpectation(service, method)` should be added next to `KafkaExpectation` and `AMQPExpectation`, and `validate_behavior` should accept a behavior when any supported matcher is present. This keeps inheritance, values, templates, and action ordering shared across all channels.

   Alternative considered: create a separate gRPC-only behavior list. That would duplicate inheritance and action validation rules already centralized in `load_behaviors` and `_validate_actions`.

1. Keep protobuf descriptor handling behind dedicated helpers.

   Add a small descriptor registry that loads comma-separated `HM_GRPC_DESCRIPTOR_SET_PATHS`, resolves relative paths from `HM_TEMPLATES_DIR`, and exposes decode/encode helpers keyed by `(service, method)`. The gRPC request path should depend on the helper API, not on descriptor internals.

   Alternative considered: store raw descriptor structures directly on `Behavior`. That makes validation and hot reload more complex and couples each behavior to transport parsing details.

1. Reuse the template context builder and merge channel-specific fields.

   Existing HTTP, Kafka, and AMQP paths already build a base context and then merge extra channel fields. gRPC should follow that pattern for `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`; evaluation should do the same for all simulated channel contexts.

   Alternative considered: create separate context builders for each channel. That increases drift in `.Values`, named template, and helper-function behavior.

1. Implement dry-run as a separate evaluator instead of calling `execute_behavior`.

   Add an `evaluate_mock_definition` style helper that validates the request, checks matchers first, renders the condition, then walks sorted actions and returns projected results only for `reply_http` and `publish_kafka`. It must never call Redis, broker clients, outbound HTTP, sleep, or gRPC send paths.

   Alternative considered: add a `dry_run=True` flag to `execute_behavior`. That risks accidental side effects because `execute_behavior` is built around performing actions.

1. Add `/api/v1/evaluate` to the existing admin server.

   `AdminHTTPRequestHandler` already owns JSON request parsing, 400 handling, and `/api/v1` APIs. The endpoint should parse a JSON object, call the evaluator, and return JSON. This avoids adding another HTTP server and keeps management APIs together.

   Alternative considered: add the endpoint to the mock HTTP server. That would mix control-plane evaluation with user mock routes and could conflict with mocked paths.

## Risks / Trade-offs

- [Descriptor dependency footprint] Adding protobuf/gRPC support may introduce new optional dependencies. → Keep imports localized to descriptor/gRPC helpers and raise clear `ValidationError` messages when support is unavailable.
- [Descriptor completeness] A descriptor set may omit the required service or message types. → Validate configured `(service, method)` pairs during startup when gRPC behaviors are loaded.
- [HTTP/2 serving complexity] The standard library HTTP server cannot serve real gRPC. → Use a proven HTTP/2/gRPC-capable dependency or a minimal cleartext h2 server isolated from existing HTTP routes.
- [Dry-run divergence] Evaluation can drift from real execution if rendering logic is duplicated. → Share action rendering helpers for HTTP replies and Kafka publish payloads where possible, with tests comparing projected defaults to real HTTP response defaults.
- [Template side effects through `redisDo`] Conditions or payload templates can invoke `redisDo`. → For dry-run, provide a guarded no-op or isolated in-memory store and document that evaluation does not touch configured external services.

## Migration Plan

1. Add config fields with defaults that keep gRPC disabled unless `HM_GRPC_ENABLED=true`.
2. Extend validation and tests for `expect.grpc`, `reply_grpc`, and descriptor configuration without changing existing mock definitions.
3. Add the evaluation endpoint to the admin server; existing admin endpoints remain unchanged.
4. Add gRPC server startup behind the feature flag. Rollback is setting `HM_GRPC_ENABLED=false` or reverting the change.

## Open Questions

- Which protobuf/gRPC dependency should be used in this Python-only project: `grpcio`/`grpcio-tools`, `betterproto`, `protobuf` dynamic messages plus an h2 server, or another already-available library?
- Should dry-run template `redisDo` use an empty in-memory store or fail with a validation/render error when invoked?
