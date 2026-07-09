## Why

Developers need the mock server to cover service-to-service gRPC traffic in addition to HTTP, Kafka, and AMQP so local integration tests can exercise protobuf contracts without a custom fake service. They also need a side-effect-free evaluation API that explains whether a mock would match and what selected actions would render before deploying or triggering the mock at runtime.

## What Changes

- Add optional HTTP/2 cleartext gRPC serving controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
- Add `expect.grpc` matching by fully-qualified protobuf service name and method name.
- Add gRPC template context variables for the matched service, method, decoded JSON payload, and metadata headers.
- Add descriptor-set loading and protobuf request/response conversion for gRPC methods that appear in loaded behaviors.
- Add `reply_grpc` actions with rendered JSON payloads, optional file-backed payloads, rendered metadata headers, and standard successful gRPC response headers.
- Add `POST /api/v1/evaluate` to validate a single mock plus simulated channel context, perform matching and template rendering without side effects, and return dry-run action results for supported action types.
- Extend AMQP evaluation semantics so an omitted or empty queue is evaluated as the routing key.

## Capabilities

### New Capabilities
- `grpc-behavior-mocking`: Optional gRPC server runtime, protobuf descriptor configuration, `expect.grpc` matching, gRPC template context, protobuf frame decoding/encoding, and `reply_grpc` responses.
- `mock-evaluation-api`: Side-effect-free evaluation endpoint for validating and dry-running one mock definition against simulated HTTP, Kafka, AMQP, or gRPC context.

### Modified Capabilities
- `mock-definition-loading`: Mock definitions can declare `expect.grpc` and `reply_grpc` while preserving existing HTTP, Kafka, and AMQP behavior loading.
- `template-rendering`: Template context includes merged simulated contexts for evaluation and gRPC-specific variables during gRPC request handling.
- `kafka-message-handling`: Existing message-style matching conventions extend to gRPC as a first-match channel and inform AMQP dry-run fallback behavior.
- `http-behavior-mocking`: HTTP reply rendering conventions are reused by evaluation dry-run results for `reply_http`.

## Related Work

### Related Changes
- `add-http-yaml-mock-server`: Established the lightweight local mock server model and YAML-driven HTTP behavior; this change extends the same model to gRPC and adds an API for inspecting match/render outcomes.
- `add-template-helpers-file-backed-bodies`: Added richer request-derived template helpers and file-backed response bodies; this change applies the same file-backed payload and request-derived rendering approach to gRPC replies and dry-run evaluation.
- `add-admin-template-storage`: Added runtime management of mock definitions and template sets; this change complements that control surface with an evaluation endpoint that can validate and preview one mock without mutating runtime state.

### Related Specs
- `kafka-message-handling/add-kafka-amqp-message-handling`: Defines message-channel runtime configuration, matching, context, and action behavior for Kafka and AMQP; this change follows those channel patterns for gRPC matching and evaluation.
- `template-rendering/add-admin-template-storage`: Protects template rendering side effects in managed storage contexts; this change keeps evaluation side-effect-free while still rendering conditions and selected actions.
- `http-behavior-mocking/add-template-helpers-file-backed-bodies`: Defines file-backed HTTP response bodies and request-derived helpers; this change reuses the file-backed payload pattern for `reply_grpc.payload_from_file`.
- `template-rendering/add-reusable-templates-inheritance-values-action-ordering`: Defines named templates, inherited values, and ordered action rendering; this change relies on ordered actions during evaluation and shared template context construction.
- `template-rendering/add-http-yaml-mock-server`: Defines shared template context for conditions, response bodies, and headers; this change adds gRPC context fields and simulated evaluation contexts to that model.
- `mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`: Defines reusable template definitions and action ordering in loaded mocks; this change keeps evaluation action rendering sorted by `order`.
- `template-hot-reload/add-hot-reload-cors-binary-cli`: Defines environment-driven runtime configuration and startup behavior; this change adds gRPC server environment variables and descriptor validation startup rules.
- `mock-definition-loading/add-http-yaml-mock-server`: Defines base server configuration and YAML mock loading; this change extends the mock schema with gRPC expectations and replies.
- `mock-definition-loading/add-stateful-actions`: Defines stateful action extensions and config preservation; this change explicitly avoids executing any side effects in the evaluation endpoint.

## Impact

- Adds a new optional gRPC listener using HTTP/2 cleartext without TLS.
- Adds protobuf descriptor-set parsing and protobuf JSON conversion dependencies or internal helpers.
- Extends mock schema validation, behavior matching, template context construction, and action rendering.
- Adds `POST /api/v1/evaluate` to the admin/API surface.
- Requires tests for gRPC startup validation, first-match routing, protobuf framing, reply headers, evaluation validation, condition handling, action ordering, and side-effect omission.
