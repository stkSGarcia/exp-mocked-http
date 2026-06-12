## Why

The mock server cannot currently model gRPC interactions or preview how a mock would match and render without invoking runtime side effects. Adding descriptor-driven gRPC support and a dry-run evaluation endpoint makes protobuf services testable while giving users a safe way to validate mocks across all supported channels.

## What Changes

- Add an optional HTTP/2 cleartext gRPC server configured through `HM_GRPC_*` environment variables.
- Add `expect.grpc` matching, gRPC template context fields, descriptor-based protobuf decoding, and `reply_grpc` response rendering and framing.
- Add `POST /api/v1/evaluate` to validate and evaluate one mock against merged simulated HTTP, Kafka, AMQP, and/or gRPC context.
- Make evaluation side-effect-free while returning rendered `reply_http` and `publish_kafka` action results in action order.
- Add validation and startup-failure behavior for required, missing, unreadable, or invalid protobuf descriptor sets.

## Related Work

### Related Changes

- `add-http-yaml-mock-server` introduced the runnable declarative mock server and active-load-order HTTP matching. This change extends that server with a second request protocol and reuses its first-match behavior model.
- `add-template-helpers-file-backed-bodies` expanded response templating and file-backed bodies. This change applies the same rendering model to gRPC JSON payloads and dry-run action output.
- `add-stateful-actions-redis-http-side-effects` introduced ordered actions and runtime side-effect hooks. This change evaluates that action model without executing side effects and exposes only supported rendered results.

### Related Specs

- `http-yaml-mock-server/add-http-yaml-mock-server` implements server configuration and HTTP request matching; this change adapts its environment-driven startup and active-load-order matching for gRPC.
- `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering` defines concrete behavior selection and ordering; this change keeps non-concrete definitions out of matching and preserves first-match semantics.
- `http-yaml-mock-server/add-template-helpers-file-backed-bodies` implements template and file-backed response rendering; this change reuses those capabilities for `reply_grpc` and evaluation output.

## Capabilities

### New Capabilities

- `grpc-mocking`: Optional descriptor-driven gRPC request matching, template context, response rendering, protobuf encoding, and HTTP/2 cleartext serving.
- `mock-evaluation`: Validation and side-effect-free evaluation of a supplied mock against merged simulated channel contexts.

### Modified Capabilities

None.

## Impact

- Runtime and configuration in `hmock.py`.
- Automated coverage in `test_hmock.py`.
- Python dependencies and lock data in `pyproject.toml` and `uv.lock` for HTTP/2, gRPC, and protobuf support.
- Public mock schema gains `expect.grpc` and `reply_grpc`; the HTTP API gains `POST /api/v1/evaluate`.
