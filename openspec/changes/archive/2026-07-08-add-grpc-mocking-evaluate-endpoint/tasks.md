## 1. Schema, Config, and Validation

- [x] 1.1 Update `hmock.py` `Config` with `GrpcConfig` fields for `enabled`, `host`, `port`, and `descriptor_set_paths`. [extends grpc-behavior-mocking]
- [x] 1.2 Parse `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` in `hmock.py::load_config`. [extends grpc-behavior-mocking]
- [x] 1.3 Extend `hmock.py::Behavior` and `hmock.py::validate_behavior` to support exactly one of `expect.http`, `expect.kafka`, `expect.amqp`, or `expect.grpc`. [extends grpc-behavior-mocking]
- [x] 1.4 Add validation for `expect.grpc.service`, `expect.grpc.method`, and `reply_grpc` payload/header fields in `hmock.py::_validate_actions`. [extends grpc-behavior-mocking]
- [x] 1.5 Preserve the existing AMQP queue default behavior in `hmock.py::validate_behavior` for both normal validation and evaluation validation. [extends mock-evaluation-api]

## 2. gRPC Descriptor and Runtime Support

- [x] 2.1 Add descriptor path resolution helpers in `hmock.py` that resolve relative `HM_GRPC_DESCRIPTOR_SET_PATHS` entries from `HM_TEMPLATES_DIR`. [extends grpc-behavior-mocking]
- [x] 2.2 Add descriptor loading and service/method lookup helpers in `hmock.py`, returning clear `ValidationError` messages for missing, unreadable, or invalid descriptor sets. [extends grpc-behavior-mocking]
- [x] 2.3 Add gRPC frame decode/encode helpers in `hmock.py` for standard unary length-prefixed request and response bodies. [extends grpc-behavior-mocking]
- [x] 2.4 Add protobuf JSON conversion helpers in `hmock.py` for inbound request payloads and rendered `reply_grpc` response payloads. [extends grpc-behavior-mocking]

## 3. gRPC Matching and Reply Rendering

- [x] 3.1 Add `hmock.py::build_grpc_template_context` with `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, `.GRPCHeader`, `.Values`, named templates, and allowed helper functions. [extends grpc-behavior-mocking]
- [x] 3.2 Add `hmock.py::find_grpc_behavior` or equivalent first-match helper for `(service, method)`. [extends grpc-behavior-mocking]
- [x] 3.3 Add `reply_grpc` rendering helpers in `hmock.py` that support inline payloads, `payload_from_file`, templated metadata headers, required gRPC headers, and framed response bytes. [extends grpc-behavior-mocking]
- [x] 3.4 Add a `HMockGRPCServer` service in `hmock.py` and wire it into `main()` startup/shutdown only when gRPC is enabled. [extends grpc-behavior-mocking]
- [x] 3.5 Validate at startup that gRPC descriptors are required only when enabled loaded behaviors use `expect.grpc` or `reply_grpc`. [extends grpc-behavior-mocking]

## 4. Evaluate Endpoint

- [x] 4.1 Add a side-effect-free evaluation request parser in `hmock.py` for `mock` plus object-shaped `context`. [extends mock-evaluation-api]
- [x] 4.2 Add matcher-specific simulated context builders in `hmock.py` for `http_context`, `kafka_context`, `amqp_context`, and `grpc_context`. [extends mock-evaluation-api]
- [x] 4.3 Implement evaluation flow in `hmock.py`: channel match first, condition render second, empty condition passes, failed match returns `expect_passed: false`, and failed condition returns `condition_rendered`. [extends mock-evaluation-api]
- [x] 4.4 Add dry-run render helpers in `hmock.py` for `reply_http_action_performed` and `publish_kafka_action_performed` without calling publishers, Redis mutations, sleep, webhook, or gRPC reply execution. [extends mock-evaluation-api]
- [x] 4.5 Add `POST /api/v1/evaluate` handling to `hmock.py::AdminHTTPRequestHandler` with `400 Bad Request` validation failures and JSON response bodies. [extends mock-evaluation-api]

## 5. Tests and Documentation

- [x] 5.1 Add config and validation tests in `tests/test_hmock.py` for gRPC defaults, environment overrides, `expect.grpc`, `reply_grpc`, descriptor requirements, and invalid matcher combinations. [extends grpc-behavior-mocking]
- [x] 5.2 Add gRPC helper tests in `tests/test_hmock.py` for descriptor path resolution, context fields, first-match behavior, payload file rendering, and required response headers. [extends grpc-behavior-mocking]
- [x] 5.3 Add evaluate endpoint tests in `tests/test_hmock.py` for HTTP, Kafka, AMQP, and gRPC contexts; validation errors; match failure; condition failure; empty condition; action ordering; and dry-run side-effect suppression. [extends mock-evaluation-api]
- [x] 5.4 Add or update user-facing configuration/docs in the existing project documentation location if one is present during implementation; otherwise keep examples in `tests/test_hmock.py`. [extends grpc-behavior-mocking]
- [x] 5.5 Run `uv run pytest` and fix regressions before marking the implementation complete.
