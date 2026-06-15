## Why

The mock server currently supports HTTP and broker-driven workflows, but it cannot directly mock gRPC services or inspect how a mock would match and render without sending real traffic through side-effecting paths. Adding gRPC support and a dry-run evaluation API expands the same template-driven behavior model to protobuf services and gives users a safer way to debug definitions before activating them.

## What Changes

- Add opt-in cleartext HTTP/2 gRPC serving controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
- Add `expect.grpc` matching by fully-qualified protobuf service name and method name.
- Add gRPC protobuf descriptor-set loading, inbound request decoding to JSON, outbound JSON response encoding, and standard gRPC response framing.
- Add `reply_grpc` actions with templated JSON payloads, file-backed payloads, and metadata headers.
- Add gRPC template context values for service, method, decoded JSON payload, and metadata headers.
- Add `POST /api/v1/evaluate` to validate one mock definition, merge simulated channel contexts, evaluate matching/conditions/actions without side effects, and return dry-run render results.
- Extend mock definition validation to cover gRPC expectations, `reply_grpc`, and evaluation-specific matcher/context validation.

## Capabilities

### New Capabilities
- `grpc-mocking`: gRPC runtime configuration, descriptor loading, request matching, template context, protobuf request/response handling, and `reply_grpc` responses.
- `mock-evaluation`: Dry-run mock evaluation through the admin API without executing external side effects.

### Modified Capabilities
- `admin-http-api`: Add the `/api/v1/evaluate` admin endpoint.
- `mock-definition-loading`: Validate `expect.grpc` and `reply_grpc` fields for loaded behavior definitions.
- `template-rendering`: Expose gRPC-specific values in the render context.

## Impact

- Affects `hmock.py` runtime configuration, startup validation, mock definition loading, action execution, and template context construction.
- Adds an admin API endpoint and response schema for dry-run evaluation.
- Adds protobuf/gRPC dependencies for HTTP/2 cleartext serving and descriptor-driven message conversion.
- Requires tests for gRPC startup behavior, descriptor validation, matching, reply encoding, template context, and side-effect-free evaluation.
