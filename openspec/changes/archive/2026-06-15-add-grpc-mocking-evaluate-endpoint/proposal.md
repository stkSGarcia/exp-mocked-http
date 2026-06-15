## Why

The mock server currently supports HTTP, Kafka, and AMQP workflows, but teams that depend on gRPC services cannot mock protobuf-framed requests or produce gRPC-compatible responses. A dry-run evaluation endpoint is also needed so users can validate a single mock definition and simulated channel context without triggering outbound effects.

## What Changes

- Add optional gRPC server support over HTTP/2 cleartext, controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and descriptor-set configuration.
- Add `expect.grpc` matching by fully-qualified protobuf service and method.
- Add gRPC template context fields for service, method, decoded JSON payload, and metadata headers.
- Add `reply_grpc` action support that renders JSON, encodes the configured protobuf response message, and returns standard gRPC framing and headers.
- Add `POST /api/v1/evaluate` to validate a supplied mock plus simulated channel context, evaluate matching and conditions, and return rendered dry-run results without executing side effects.
- Extend mock schema validation for gRPC expectations, gRPC replies, and evaluate-specific validation requirements.

## Capabilities

### New Capabilities
- `grpc-behavior-mocking`: gRPC runtime configuration, protobuf descriptor loading, service/method matching, request decoding, template context, and gRPC response encoding.

### Modified Capabilities
- `mock-definition-loading`: Add schema validation and startup descriptor validation for `expect.grpc` and `reply_grpc`.
- `template-rendering`: Expose gRPC request fields in template context.
- `admin-http-api`: Add the dry-run evaluation endpoint and its request, validation, and response behavior.

## Impact

- Affects `hmock.py` runtime configuration, mock loading, action models, template context construction, and server startup.
- Adds an admin HTTP endpoint at `POST /api/v1/evaluate`.
- Introduces optional gRPC/protobuf dependencies for HTTP/2 cleartext serving, descriptor-set parsing, protobuf JSON conversion, and gRPC message framing.
- Does not change existing HTTP, Kafka, or AMQP runtime behavior except through shared dry-run evaluation logic.
