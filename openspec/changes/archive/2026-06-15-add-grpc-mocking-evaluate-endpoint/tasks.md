## 1. Configuration And Schema

- [x] 1.1 Extend `Config` and `load_config` with `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` defaults.
- [x] 1.2 Extend `Behavior` with gRPC service and method fields, and include `grpc` in exactly-one trigger detection.
- [x] 1.3 Validate `expect.grpc.service` and `expect.grpc.method` as non-empty strings for concrete behaviors.
- [x] 1.4 Validate `reply_grpc` action payloads, metadata headers, inline/file-backed payload precedence, and templates-directory file safety.
- [x] 1.5 Add unit tests for gRPC config defaults/overrides, trigger validation, `reply_grpc` validation, and file-backed payload loading failures.

## 2. gRPC Context And Matching

- [x] 2.1 Add `build_grpc_template_context` with `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, `.GRPCHeader`, `.Values`, named templates, and optional guarded Redis function support.
- [x] 2.2 Add gRPC behavior matching by service and method with condition rendering and first-match wins.
- [x] 2.3 Add gRPC execution helpers that render `reply_grpc` payloads and metadata using the gRPC template context.
- [x] 2.4 Add unit tests for gRPC template context, condition handling, service/method mismatch, and first-match behavior.

## 3. Descriptor And Protobuf Handling

- [x] 3.1 Add descriptor-set path parsing that resolves relative paths from `HM_TEMPLATES_DIR` and supports comma-separated files.
- [x] 3.2 Implement descriptor loading and lookup for configured gRPC service/method request and response message types.
- [x] 3.3 Implement gRPC length-prefixed request frame decoding to protobuf JSON.
- [x] 3.4 Implement rendered JSON response encoding to protobuf bytes and standard gRPC length-prefixed response framing.
- [x] 3.5 Add tests with a descriptor fixture for valid decoding/encoding and for missing, unreadable, invalid, or incomplete descriptor sets.

## 4. gRPC Server Runtime

- [x] 4.1 Add an opt-in cleartext HTTP/2 gRPC server path that dispatches unary requests to gRPC behavior matching and execution.
- [x] 4.2 Gate gRPC server construction and descriptor validation behind `HM_GRPC_ENABLED`.
- [x] 4.3 Fail startup when gRPC is enabled and loaded gRPC behaviors require missing or invalid descriptor configuration.
- [x] 4.4 Allow startup when gRPC is enabled but no loaded behavior uses `expect.grpc` or `reply_grpc`.
- [x] 4.5 Return successful gRPC responses with `grpc-status: 0`, `grpc-message: OK`, `Content-Type: application/grpc`, rendered custom metadata, and framed protobuf payload.
- [x] 4.6 Add integration-style tests for disabled-by-default startup, enabled startup behavior, descriptor failure cases, and one successful unary gRPC request/response.

## 5. Dry-Run Evaluation Core

- [x] 5.1 Add evaluation request parsing for one `mock` object plus one non-array `context` object.
- [x] 5.2 Validate evaluation `mock.key`, supported matchers, required matcher fields, and required matching channel context.
- [x] 5.3 Build merged template context from provided `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects.
- [x] 5.4 Evaluate channel matching before condition rendering and return `expect_passed`, `condition_passed`, `condition_rendered`, and `actions_performed`.
- [x] 5.5 Treat empty conditions as passing and preserve raw rendered condition output for non-empty conditions.
- [x] 5.6 Sort actions by existing stable order rules and render only `reply_http_action_performed` and `publish_kafka_action_performed` results.
- [x] 5.7 Ensure evaluation skips Redis, sleep, outbound HTTP, broker publish, AMQP publish, and gRPC reply side effects.
- [x] 5.8 Add unit tests for validation failures, match failures, condition pass/fail, AMQP queue defaulting, action ordering, rendered result shapes, and side-effect isolation.

## 6. Admin Endpoint

- [x] 6.1 Add `POST /api/v1/evaluate` to `AdminHTTPRequestHandler` without reusing template upsert persistence paths.
- [x] 6.2 Return `200 OK` JSON for valid evaluation requests and `400 Bad Request` for validation or JSON parse failures.
- [x] 6.3 Ensure evaluation does not mutate base templates, template sets, filesystem mock snapshots, active mock state, or Redis.
- [x] 6.4 Add admin API tests for successful evaluation, validation errors, non-persistence, and no side effects.

## 7. Verification

- [x] 7.1 Run the targeted gRPC validation/matching/evaluation/admin tests.
- [x] 7.2 Run the full test suite with `uv run pytest` or the repository's established pytest command.
- [x] 7.3 Run `openspec status --change "add-grpc-mocking-evaluate-endpoint"` and confirm the change remains apply-ready.
