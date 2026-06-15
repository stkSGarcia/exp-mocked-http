## 1. Configuration And Schema

- [x] 1.1 Add gRPC configuration fields to `Config` and `load_config` for enablement, host, port, and descriptor-set paths.
- [x] 1.2 Parse `HM_GRPC_DESCRIPTOR_SET_PATHS` as comma-separated paths and resolve relative paths from `HM_TEMPLATES_DIR`.
- [x] 1.3 Extend behavior validation to accept `expect.grpc.service` and `expect.grpc.method` and reject missing or invalid gRPC matcher fields.
- [x] 1.4 Extend action validation to accept one `reply_grpc` action, require `payload` or `payload_from_file`, validate headers, and load file-backed payload content.
- [x] 1.5 Add descriptor validation that fails startup only when gRPC is enabled and loaded behaviors use `expect.grpc` or `reply_grpc`.

## 2. gRPC Runtime

- [x] 2.1 Add a descriptor registry that loads protobuf descriptor sets and resolves service, method, input message, and output message descriptors.
- [x] 2.2 Add helpers for standard gRPC length-prefixed request decoding and response encoding.
- [x] 2.3 Add gRPC request info and template context support for `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`.
- [x] 2.4 Implement gRPC behavior matching by service and method with first-match-wins condition evaluation.
- [x] 2.5 Implement `reply_grpc` rendering, JSON-to-protobuf encoding, standard success headers, and rendered custom metadata.
- [x] 2.6 Wire optional gRPC server startup and shutdown into `build_servers` and `main` when `HM_GRPC_ENABLED=true`.

## 3. Dry-Run Evaluation Endpoint

- [x] 3.1 Add `POST /api/v1/evaluate` request parsing for one `mock` object and one merged `context` object.
- [x] 3.2 Validate evaluate requests for required mock key, supported matcher presence, matcher required fields, and matching channel context.
- [x] 3.3 Build simulated HTTP, Kafka, AMQP, and gRPC template contexts from the provided context sub-objects.
- [x] 3.4 Evaluate channel matcher before condition rendering and return `expect_passed: false` with no actions when matching fails.
- [x] 3.5 Render conditions, treating empty conditions as passing and returning `condition_rendered` on condition failure.
- [x] 3.6 Sort actions by effective order and render dry-run result objects only for `reply_http` and `publish_kafka`.
- [x] 3.7 Ensure evaluation never executes Redis, outbound HTTP, sleep, Kafka publish, AMQP publish, gRPC replies, or other side effects.

## 4. Tests And Verification

- [x] 4.1 Add config and validation tests for gRPC defaults, overrides, matcher validation, reply validation, and descriptor failure rules.
- [x] 4.2 Add gRPC descriptor/framing tests covering request decode, response encode, service/method matching, template context, and metadata headers.
- [x] 4.3 Add admin evaluate endpoint tests for validation failures, matcher failure, empty condition success, condition failure, action ordering, and supported dry-run results.
- [x] 4.4 Add regression tests proving evaluate does not execute side effects for Redis, outbound HTTP, AMQP, Kafka, sleep, or gRPC actions.
- [x] 4.5 Run the project test suite and the OpenSpec validation/status checks for this change.
