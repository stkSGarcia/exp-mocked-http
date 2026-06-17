## 1. Configuration And Validation

- [x] 1.1 Update `hmock.py` `Config` and `load_config` with `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`. [extends mock-definition-loading]
- [x] 1.2 Add `GrpcExpectation` to `hmock.py` and extend `Behavior`, `_validate_abstract_definition`, and `validate_behavior` to accept `expect.grpc.service` and `expect.grpc.method`. [extends grpc-behavior-mocking]
- [x] 1.3 Extend `_validate_actions` in `hmock.py` to validate `reply_grpc.payload`, `reply_grpc.payload_from_file`, and `reply_grpc.headers`.
- [x] 1.4 Reuse `_resolve_body_file` in `hmock.py` to snapshot `reply_grpc.payload_from_file` relative to `HM_TEMPLATES_DIR`.
- [x] 1.5 Add validation tests in `tests/test_hmock.py` for gRPC config defaults/overrides, `expect.grpc`, `reply_grpc`, and missing/invalid gRPC payload files.

## 2. Protobuf Descriptor And gRPC Runtime

- [x] 2.1 Decide and add the protobuf/gRPC dependency approach for this repo, or isolate optional imports with clear `ValidationError` failures when unavailable.
- [x] 2.2 Implement descriptor-set loading helpers in `hmock.py` that resolve relative paths from `HM_TEMPLATES_DIR`, parse comma-separated paths, and index request/response message descriptors by `(service, method)`. [extends grpc-behavior-mocking]
- [x] 2.3 Validate descriptor configuration at startup in `build_server` when gRPC is enabled and loaded behaviors use `expect.grpc` or `reply_grpc`.
- [x] 2.4 Implement gRPC request frame decode and response frame encode helpers in `hmock.py` for standard length-prefixed gRPC messages.
- [x] 2.5 Add an HTTP/2 cleartext gRPC server path in `hmock.py` that starts only when `HM_GRPC_ENABLED=true`, matches by service/method, renders conditions, and returns `reply_grpc` responses.
- [x] 2.6 Add gRPC runtime tests in `tests/test_hmock.py` for descriptor loading, missing descriptors, exact service/method matching, metadata context, reply headers, and response framing.

## 3. Template Context

- [x] 3.1 Extend template context construction in `hmock.py` to merge `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader` for gRPC requests. [extends template-rendering]
- [x] 3.2 Render `reply_grpc.payload`, `reply_grpc.payload_from_file`, and each `reply_grpc.headers` value with the existing `render_template` engine.
- [x] 3.3 Add tests in `tests/test_hmock.py` proving gRPC service, method, payload, and metadata values render in conditions, payloads, and headers.

## 4. Dry-Run Evaluation Endpoint

- [x] 4.1 Add an `evaluate_mock_definition` helper in `hmock.py` that validates one mock definition plus a single context object without loading it into server state. [extends mock-evaluation]
- [x] 4.2 Implement channel-specific dry-run matching in `hmock.py` for HTTP, Kafka, AMQP, and gRPC, including AMQP queue defaulting to `routing_key`.
- [x] 4.3 Build a merged dry-run template context from `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects without accepting array contexts.
- [x] 4.4 Render conditions after matcher success and return `expect_passed`, `condition_passed`, `condition_rendered`, and an empty `actions_performed` on condition failure.
- [x] 4.5 Project sorted `reply_http` actions into `reply_http_action_performed` results with string `status_code`, `content_type`, generated `Content-Type`, and generated `Content-Length`. [extends http-behavior-mocking]
- [x] 4.6 Project sorted `publish_kafka` actions into `publish_kafka_action_performed` results and omit all other action types without side effects.
- [x] 4.7 Add `POST /api/v1/evaluate` to `AdminHTTPRequestHandler` in `hmock.py` and return `400 Bad Request` for validation, JSON, or encoding failures.
- [x] 4.8 Add endpoint tests in `tests/test_hmock.py` covering valid evaluation, matcher failure, condition failure, validation failure, HTTP reply projection, Kafka publish projection, AMQP queue defaulting, gRPC context, and skipped side-effect actions.

## 5. Regression Verification

- [x] 5.1 Run the full existing test suite with `pytest` and fix regressions in `hmock.py` or `tests/test_hmock.py`.
- [x] 5.2 Add focused regression tests ensuring existing HTTP, Kafka, AMQP, admin template, and hot-reload behavior remain unchanged.
- [x] 5.3 Run `openspec status --change "add-grpc-mocking-evaluate"` and ensure all proposal artifacts remain complete before applying implementation.
