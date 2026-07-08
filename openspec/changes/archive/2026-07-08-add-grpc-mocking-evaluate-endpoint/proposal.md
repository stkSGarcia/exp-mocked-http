## Why

Mocked HTTP, Kafka, and AMQP workflows cover many local integration tests, but services that speak gRPC still need custom test doubles or a separate mocking stack. Developers also need a safe way to validate whether a mock definition matches and renders correctly without sending HTTP responses, publishing messages, or executing other side effects.

## What Changes

- Add an optional cleartext HTTP/2 gRPC server controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
- Add `expect.grpc` matching by fully-qualified protobuf service name and method name.
- Add protobuf descriptor-set loading so inbound gRPC requests can be decoded into JSON template context and `reply_grpc` JSON payloads can be encoded into standard gRPC length-prefixed responses.
- Add `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader` template context values.
- Add `reply_grpc` actions with templated payloads, optional file-backed payloads, templated metadata headers, and required gRPC response headers.
- Add `POST /api/v1/evaluate` to validate one mock definition against simulated channel context, run matching and template rendering as a dry run, and return the render result without side effects.
- Extend dry-run evaluation to HTTP, Kafka, AMQP, and gRPC matchers, while returning performed action details only for `reply_http` and `publish_kafka`.

## Capabilities

### New Capabilities

- `grpc-behavior-mocking`: Covers gRPC server startup, protobuf descriptor loading, `expect.grpc` matching, gRPC template context, and `reply_grpc` response rendering.
- `mock-evaluation-api`: Covers the dry-run evaluation API, request validation, simulated channel context merging, condition rendering, action ordering, and side-effect-free render results.

### Modified Capabilities

- None.

## Related Work

### Related Changes

- `add-template-helpers-file-backed-bodies`: Motivated richer request-derived template context and file-backed response bodies for HTTP mocks; this change extends that direction to gRPC payload rendering and `reply_grpc.payload_from_file`.
- `add-http-yaml-mock-server`: Established the baseline YAML-driven mock service and HTTP request/response behavior; this change adds a new gRPC channel and a validation endpoint for the same mock definition model.
- `add-kafka-amqp-message-handling`: Added event-channel matching beyond HTTP; this change complements it with gRPC matching and includes Kafka/AMQP contexts in the evaluate endpoint.

### Related Specs

- `template-rendering/add-admin-api-template-storage`: Documents template execution contexts and restrictions; this change reuses the same rendering model while ensuring evaluation stays dry-run.
- `http-behavior-mocking/add-stateful-actions`: Describes ordered action execution after behavior selection; this change uses that ordering for dry-run action rendering without executing side effects.
- `internal-keyspace-protection/add-admin-api-template-storage`: Captures boundaries around stateful template helpers; this change preserves those boundaries by not executing side effects during evaluation.
- `http-behavior-mocking/add-template-helpers-file-backed-bodies`: Adds file-backed response body behavior; this change adapts the same idea for `reply_grpc.payload_from_file`.
- `template-rendering/add-http-yaml-mock-server`: Defines request template context and HTTP rendering conventions; this change extends the context model with gRPC values and simulated contexts for evaluation.

## Impact

- Adds a new optional gRPC listener and protobuf descriptor dependency path.
- Expands mock schema validation with `expect.grpc` and `reply_grpc`.
- Adds a new Admin/API endpoint: `POST /api/v1/evaluate`.
- Affects matching, template context construction, action rendering, response encoding, startup validation, and configuration documentation.
