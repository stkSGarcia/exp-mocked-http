## Why

The mock server currently supports HTTP, Kafka, and AMQP channels but cannot stub gRPC services, which are widely used in backend architectures. Additionally, there is no way to validate a mock definition and preview its rendered output without actually sending a real request, making it harder to debug template logic or verify routing before deploying mocks.

## What Changes

- Add a gRPC mock server that listens on a configurable port (HTTP/2 cleartext) and matches inbound unary calls by `(service, method)`.
- Introduce `expect.grpc` and `reply_grpc` fields in the mock definition schema so behaviors can be authored for gRPC channels.
- Decode inbound protobuf requests and encode protobuf responses using descriptor-set files, exposing the payload as `.GRPCPayload` in template context.
- Add `POST /api/v1/evaluate` to the admin API — a dry-run endpoint that accepts a mock definition plus simulated channel context and returns match/condition/action results without executing side effects.

## Capabilities

### New Capabilities
- `grpc-mocking`: gRPC server, `expect.grpc` / `reply_grpc` schema fields, descriptor-set loading, protobuf encode/decode, and gRPC template context variables.

### Modified Capabilities
- `admin-api`: Add the `POST /api/v1/evaluate` dry-run evaluation endpoint with its request/response schema, validation rules, and evaluation semantics.

## Impact

- **New dependency**: a protobuf / gRPC library for Python (e.g., `grpcio`, `protobuf`, `grpcio-reflection` or equivalent) to handle HTTP/2 framing and descriptor-set decoding.
- **Schema**: `expect` and `reply_*` schemas gain new optional fields (`grpc`, `reply_grpc`).
- **Admin API**: one new route added — no existing routes change.
- **Startup validation**: when `HM_GRPC_ENABLED=true` and any loaded behavior references `expect.grpc` or `reply_grpc`, the server validates descriptor-set paths at startup and fails fast if they are missing or invalid.
- **No breaking changes** to existing HTTP, Kafka, or AMQP behavior.
