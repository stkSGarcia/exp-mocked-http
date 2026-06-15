## 1. Configuration And Schema

- [x] 1.1 Add gRPC fields to runtime configuration with defaults for enablement, host, port, and descriptor-set paths.
- [x] 1.2 Parse `HM_GRPC_DESCRIPTOR_SET_PATHS` as a comma-separated list and resolve relative paths from `HM_TEMPLATES_DIR`.
- [x] 1.3 Extend behavior validation to accept `expect.grpc.service` and `expect.grpc.method` as required non-empty strings.
- [x] 1.4 Extend action validation to accept `reply_grpc` with `payload` or `payload_from_file` and string metadata headers.
- [x] 1.5 Load and snapshot `reply_grpc.payload_from_file` content with the same templates-directory safety checks used by other file-backed payloads.
- [x] 1.6 Update configuration and schema tests for gRPC defaults, overrides, valid definitions, and invalid definitions.

## 2. gRPC Descriptor And Framing

- [x] 2.1 Add a descriptor registry helper that loads configured protobuf descriptor-set files and indexes unary methods by service and method.
- [x] 2.2 Validate configured gRPC behaviors against the descriptor registry when gRPC is enabled.
- [x] 2.3 Implement standard gRPC length-prefixed request frame decoding and response frame encoding helpers.
- [x] 2.4 Implement protobuf request decoding to JSON and rendered response JSON encoding to protobuf using the matched method descriptors.
- [x] 2.5 Add descriptor, framing, decode, and encode tests for success and validation failure cases.

## 3. gRPC Runtime

- [x] 3.1 Add an optional cleartext HTTP/2 gRPC server startup path controlled by `HM_GRPC_ENABLED`.
- [x] 3.2 Route unary gRPC requests to loaded behaviors by fully-qualified service and method.
- [x] 3.3 Build gRPC template context with `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, `.GRPCHeader`, and `.Values`.
- [x] 3.4 Evaluate gRPC conditions with first-match-wins behavior selection.
- [x] 3.5 Render `reply_grpc` payloads and metadata headers, then return `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc` on success.
- [x] 3.6 Add runtime tests for disabled startup, enabled startup, descriptor failure modes, matching, condition handling, metadata, and successful replies.

## 4. Shared Evaluation Engine

- [x] 4.1 Extract or add shared matcher helpers for HTTP, Kafka, AMQP, and gRPC simulated contexts.
- [x] 4.2 Add evaluation request parsing and validation for one mock definition plus a single context object with channel sub-objects.
- [x] 4.3 Build merged template context from provided `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects.
- [x] 4.4 Evaluate matcher result before condition rendering and return `expect_passed: false` with no actions when matching fails.
- [x] 4.5 Render conditions, preserving `condition_rendered`, and return no actions when the rendered condition is not exactly `true`.
- [x] 4.6 Sort actions by effective order while preserving declared order for ties.

## 5. Dry-Run Action Results

- [x] 5.1 Render `reply_http` action results with status code, body, content type defaulting, `Content-Type`, and `Content-Length`.
- [x] 5.2 Render `publish_kafka` action results with topic and payload, including file-backed payloads.
- [x] 5.3 Omit unsupported action types from `actions_performed` without executing Redis, outbound HTTP, AMQP publish, sleep, or gRPC side effects.
- [x] 5.4 Add tests that evaluation does not mutate persisted templates, call broker adapters, issue outbound HTTP, run Redis actions, or sleep.

## 6. Admin Endpoint

- [x] 6.1 Add `POST /api/v1/evaluate` to the admin HTTP router.
- [x] 6.2 Return `400 Bad Request` for malformed JSON, invalid mock definitions, invalid matcher fields, missing required channel context, or array-valued `context`.
- [x] 6.3 Return the dry-run response shape with `expect_passed`, `condition_passed`, `condition_rendered`, and `actions_performed`.
- [x] 6.4 Add admin endpoint tests for successful HTTP/Kafka/AMQP/gRPC evaluations and validation failures.

## 7. Documentation And Regression

- [x] 7.1 Update user-facing examples or README material for gRPC environment variables, `expect.grpc`, `reply_grpc`, and descriptor-set paths if documentation exists.
- [x] 7.2 Add evaluation endpoint examples showing request shape, response shape, and side-effect-free behavior if documentation exists.
- [x] 7.3 Run the full test suite and fix regressions.
- [x] 7.4 Run OpenSpec status validation and confirm the change is ready to apply.
