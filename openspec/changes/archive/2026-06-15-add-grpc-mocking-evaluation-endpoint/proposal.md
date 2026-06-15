## Why

The mock server currently covers HTTP, Kafka, and AMQP flows, but teams that expose gRPC services cannot exercise protobuf-backed request matching and responses through the same behavior model. A dry-run evaluation endpoint is also needed so users can validate matching, conditions, and rendered action output without sending real traffic or triggering side effects.

## What Changes

- Add optional cleartext HTTP/2 gRPC serving controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
- Add `expect.grpc` matching by fully-qualified protobuf service name and method name.
- Add protobuf descriptor loading, request frame decoding to JSON, response JSON encoding, and standard gRPC response framing.
- Add `reply_grpc` actions with inline or file-backed JSON payloads and rendered metadata headers.
- Add gRPC template context fields for service, method, decoded payload JSON, and request metadata.
- Add `POST /api/v1/evaluate` to evaluate one mock definition against simulated HTTP, Kafka, AMQP, or gRPC context without executing side effects.
- Return rendered dry-run results for `reply_http` and `publish_kafka` actions while omitting side-effecting or unsupported dry-run actions.
- Extend validation so both loaded mocks and evaluation requests reject missing required matcher/action fields.

## Capabilities

### New Capabilities
- `grpc-behavior-mocking`: gRPC server startup, descriptor-backed request/response conversion, `expect.grpc` matching, and `reply_grpc` responses.
- `dry-run-evaluation`: Admin evaluation endpoint for validating a single mock definition against simulated channel context without side effects.

### Modified Capabilities
- `mock-definition-loading`: add gRPC environment configuration, `expect.grpc` validation, `reply_grpc` validation, and file-backed gRPC payload loading.
- `template-rendering`: add gRPC template context fields and ensure gRPC-triggered renders use the existing template function semantics.
- `admin-http-api`: expose the dry-run evaluation endpoint through the admin HTTP API.

## Impact

- Affects server configuration, startup orchestration, mock schema validation, file-backed payload loading, template context construction, and admin API routing.
- Adds a gRPC network listener when explicitly enabled; HTTP, Kafka, AMQP, and admin defaults remain unchanged.
- Requires a protobuf descriptor parsing/encoding dependency or equivalent implementation for descriptor-set loading and dynamic message conversion.
- Adds test coverage for gRPC startup/configuration, descriptor failures, protobuf framing, gRPC matching/response rendering, and dry-run evaluation success and validation paths.
