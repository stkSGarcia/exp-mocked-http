## 1. Dependencies and Config

- [x] 1.1 Add `grpcio` and `protobuf` to `pyproject.toml` dependencies
- [x] 1.2 Add gRPC config constants to `hmock.py`: `GRPC_ENABLED`, `GRPC_PORT`, `GRPC_HOST`, `GRPC_DESCRIPTOR_SET_PATHS` (parsed from comma-separated env var)

## 2. Descriptor-Set Registry

- [x] 2.1 Implement `_load_descriptor_registry(paths: list[str]) -> dict` that loads each `.pb` file as a `FileDescriptorSet`, registers all descriptors into a `DescriptorPool`, and returns a mapping of `"service/method"` → `(input_message_class, output_message_class)` using `MessageFactory` (or `GetMessageClass` in newer protobuf)
- [x] 2.2 Implement `_check_grpc_descriptor_requirements(behaviors: list, registry: dict)` that raises `ValueError` at startup if any behavior's `expect.grpc` or `reply_grpc` references a `(service, method)` pair not in the registry
- [x] 2.3 Resolve relative descriptor-set paths from `TEMPLATES_DIR` in `_load_descriptor_registry`

## 3. Schema and Validation

- [x] 3.1 Extend `_validate_behavior` to accept `expect.grpc` with required fields `service` and `method`
- [x] 3.2 Extend `_validate_behavior` to accept `reply_grpc` action with required field `payload` (or `payload_from_file`) and optional `headers` map
- [x] 3.3 Add validation that a behavior with `reply_grpc` also has `expect.grpc` (gRPC reply only valid for gRPC behaviors)

## 4. gRPC Request Matching and Context

- [x] 4.1 Implement `find_behavior_for_grpc(behaviors: list, service: str, method: str, context: dict) -> dict | None` using first-match wins, checking `expect.grpc.service` and `expect.grpc.method`, then evaluating `expect.condition`
- [x] 4.2 Implement `build_grpc_context(service: str, method: str, payload_json: str, headers: dict) -> dict` that returns a context dict with `GRPCService`, `GRPCMethod`, `GRPCPayload`, and `GRPCHeader` (a `HeaderMap` instance)

## 5. Protobuf Encode/Decode

- [x] 5.1 Implement `_grpc_decode_request(raw_body: bytes, msg_class) -> str` that strips the 5-byte gRPC length-prefix framing, parses the protobuf bytes into `msg_class`, and returns the JSON string via `MessageToJson`
- [x] 5.2 Implement `_grpc_encode_response(payload_json: str, msg_class) -> bytes` that parses the JSON into a `msg_class` instance via `Parse` and prepends the 5-byte gRPC length-prefix framing

## 6. gRPC Reply Execution

- [x] 6.1 Implement `execute_reply_grpc(cfg: dict, context: dict, output_msg_class) -> bytes` that renders `payload` (or reads `payload_from_file`) as a Jinja2 template, encodes it via `_grpc_encode_response`, and returns the encoded bytes along with rendered `headers`

## 7. gRPC Server

- [x] 7.1 Implement `_GrpcHandler` (a `grpc.GenericRpcHandler` subclass) with `service_name()` returning `None` (intercepts all services) and `service(handler_call_details)` returning a `grpc.RpcMethodHandler` that calls `_handle_grpc_call`
- [x] 7.2 Implement `_handle_grpc_call(request_bytes: bytes, context) -> bytes` that extracts service and method from `context.invocation_metadata()` / `handler_call_details.method` (format: `/service/method`), decodes the request, builds the template context, calls `find_behavior_for_grpc`, executes `execute_reply_grpc`, and sets trailing metadata headers; returns UNIMPLEMENTED if no behavior matches
- [x] 7.3 Implement `_grpc_start()` that lazy-imports `grpcio`, creates the server with `_GrpcHandler`, calls `_load_descriptor_registry`, calls `_check_grpc_descriptor_requirements`, starts the server on `GRPC_HOST:GRPC_PORT`, and runs in a daemon thread
- [x] 7.4 Call `_grpc_start()` in `main()` when `GRPC_ENABLED=true`, placed after the messaging loop setup and before the HTTP server starts

## 8. Evaluate Endpoint — Request Validation

- [x] 8.1 Add route `POST /api/v1/evaluate` in `AdminRequestHandler.do_POST`, dispatching to `_handle_evaluate`
- [x] 8.2 Implement request parsing in `_handle_evaluate`: read JSON body, extract `mock` and `context`, return 400 if body is malformed
- [x] 8.3 Validate `mock.key` is non-empty; return 400 if missing
- [x] 8.4 Validate `mock.expect` contains at least one of `http`, `kafka`, `amqp`, or `grpc`; return 400 if none present
- [x] 8.5 Validate required fields for each declared matcher (`http` requires at least `method` or `path`; `kafka` requires `topic`; `amqp` requires `exchange` and `routing_key`; `grpc` requires `service` and `method`); return 400 on failure
- [x] 8.6 Validate that `context` includes the sub-object matching the declared matcher (e.g., `http_context` for `http`); return 400 if missing
- [x] 8.7 Apply AMQP queue defaulting: when `mock.expect.amqp.queue` is absent or empty, treat it as equal to `routing_key` during evaluation

## 9. Evaluate Endpoint — Evaluation Logic

- [x] 9.1 Implement `_build_eval_context(context_obj: dict) -> dict` that merges `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects into a single template context dict using the same field names as the live channel context builders
- [x] 9.2 Implement channel-specific match check in `_handle_evaluate`: for `http`, compare `method` and `path` pattern; for `kafka`, compare `topic`; for `amqp`, compare `exchange`, `routing_key`, and effective `queue`; for `grpc`, compare `service` and `method`; return `{"expect_passed": false, "actions_performed": []}` on mismatch
- [x] 9.3 Implement condition evaluation: render `mock.expect.condition` with the merged context; treat empty condition as passing; return `{expect_passed: true, condition_passed: false, condition_rendered: <rendered>, actions_performed: []}` when condition is non-empty and renders to anything other than `"true"`
- [x] 9.4 Implement `_dry_run_actions(actions: list, context: dict) -> list` that iterates actions sorted by `order`, renders `reply_http` into a `reply_http_action_performed` dict (fields: `status_code` as string, `content_type` defaulting to `application/json`, `body`, `headers` including `Content-Type` and `Content-Length`), renders `publish_kafka` into a `publish_kafka_action_performed` dict (fields: `topic`, `payload`), and skips all other action types without executing them
- [x] 9.5 Return full success response from `_handle_evaluate`: `{expect_passed: true, condition_passed: true, condition_rendered: <rendered>, actions_performed: [...]}`

## 10. Tests

- [x] 10.1 Add unit tests for `_grpc_decode_request` and `_grpc_encode_response` using a simple compiled test proto descriptor
- [x] 10.2 Add unit tests for `find_behavior_for_grpc` covering match, no-match, first-match-wins, and condition filtering
- [x] 10.3 Add unit tests for `build_grpc_context` verifying all four context variables are set correctly
- [x] 10.4 Add unit tests for `_handle_evaluate` covering: all validation failure cases (missing key, missing matcher, missing context sub-object, invalid AMQP fields), expect_passed false path, condition_passed false path, full match with reply_http result, full match with publish_kafka result, and omission of non-rendered action types
- [x] 10.5 Add integration test for the gRPC server: start server, send a unary call for a behavior loaded from a test descriptor-set file, and verify the protobuf response matches the expected reply_grpc payload
