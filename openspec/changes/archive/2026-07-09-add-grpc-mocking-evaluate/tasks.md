## 1. Configuration and Schema

- [x] 1.1 Add `GRPCConfig` and `Config.grpc` in `hmock.py`, and update `load_config()` to read `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 1.2 Extend the `Behavior` model and `validate_behavior()` in `hmock.py` to accept `expect.grpc.service` and `expect.grpc.method` while preserving HTTP, Kafka, and AMQP validation. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 1.3 Extend `_validate_actions()` and payload-source helpers in `hmock.py` to validate `reply_grpc.payload`, `reply_grpc.payload_from_file`, and rendered metadata headers. [extends http-behavior-mocking/add-template-helpers-file-backed-bodies]
- [x] 1.4 Add schema/config regression tests in `tests/test_hmock.py` for gRPC defaults, environment overrides, invalid `expect.grpc`, invalid `reply_grpc`, and existing matcher compatibility.

## 2. gRPC Protobuf Support

- [x] 2.1 Add descriptor-set path resolution in `hmock.py`, resolving relative descriptor paths from `Config.templates_dir` and reporting unreadable or invalid files. [extends template-hot-reload/add-hot-reload-cors-binary-cli]
- [x] 2.2 Add a descriptor registry helper in `hmock.py` that maps `(service, method)` to protobuf request and response descriptors.
- [x] 2.3 Add unary gRPC frame decode/encode helpers in `hmock.py` for standard length-prefixed protobuf messages.
- [x] 2.4 Add tests in `tests/test_hmock.py` for descriptor config required when loaded gRPC behavior needs descriptors and optional when no loaded behavior uses `expect.grpc` or `reply_grpc`.

## 3. gRPC Runtime

- [x] 3.1 Implement gRPC request context construction in `hmock.py` with `GRPCService`, `GRPCMethod`, `GRPCPayload`, and `GRPCHeader`. [extends template-rendering/add-http-yaml-mock-server]
- [x] 3.2 Implement first-match gRPC behavior dispatch in `hmock.py` using loaded behavior order and condition rendering. [extends kafka-message-handling/add-kafka-amqp-message-handling]
- [x] 3.3 Implement `reply_grpc` rendering in `hmock.py`, including file-backed payloads, custom metadata headers, `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc`.
- [x] 3.4 Add optional gRPC server startup/shutdown wiring in `hmock.py` and CLI entry flow used by `omctl`, leaving gRPC disabled by default.
- [x] 3.5 Add tests in `tests/test_hmock.py` for gRPC matching, context variables, response headers, response framing, and nonmatching service/method behavior.

## 4. Evaluation Core

- [x] 4.1 Add pure evaluation request validation helpers in `hmock.py` for `mock.key`, supported matchers, required matcher fields, and required channel context. [extends mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering]
- [x] 4.2 Add channel-specific dry-run matching helpers in `hmock.py` for HTTP, Kafka, AMQP, and gRPC simulated contexts.
- [x] 4.3 Implement AMQP evaluation queue fallback in `hmock.py` so omitted or empty `mock.expect.amqp.queue` evaluates as `routing_key`. [extends kafka-message-handling/add-kafka-amqp-message-handling]
- [x] 4.4 Add merged evaluation template context construction in `hmock.py` for `http_context`, `kafka_context`, `amqp_context`, and `grpc_context`. [extends template-rendering/add-http-yaml-mock-server]
- [x] 4.5 Add tests in `tests/test_hmock.py` for validation failures, context array rejection, context merging, matcher failure short-circuiting, empty condition pass, and rendered condition failure.

## 5. Evaluation Actions and API

- [x] 5.1 Add dry-run action rendering in `hmock.py` that sorts actions by `order`, executes no side effects, and returns only `reply_http_action_performed` and `publish_kafka_action_performed`. [extends template-rendering/add-reusable-templates-inheritance-values-action-ordering]
- [x] 5.2 Reuse HTTP reply rendering logic in `hmock.py` so dry-run HTTP results include status code as a string, default `application/json` content type, rendered body, custom headers, generated `Content-Type`, and generated `Content-Length`. [extends http-behavior-mocking/add-template-helpers-file-backed-bodies]
- [x] 5.3 Add `POST /api/v1/evaluate` handling to `AdminHTTPRequestHandler` in `hmock.py`, returning `400 Bad Request` on validation errors and JSON evaluation results on success.
- [x] 5.4 Add endpoint tests in `tests/test_hmock.py` for successful HTTP and Kafka dry-runs, unsupported action omission, no broker/Redis/send_http side effects, and JSON response shape.

## 6. Verification

- [x] 6.1 Run `uv run pytest tests/test_hmock.py` and fix failures.
- [x] 6.2 Run a manual smoke check with `omctl` or direct `hmock.py` startup to confirm existing HTTP/admin behavior still starts with default gRPC disabled.
- [x] 6.3 Update any user-facing examples or inline help in `hmock.py` or `omctl` if they enumerate supported matchers or actions.
