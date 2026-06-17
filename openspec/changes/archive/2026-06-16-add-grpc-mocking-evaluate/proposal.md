## Why

Teams using HTTP mocks also need to validate gRPC clients and inspect mock behavior outcomes without triggering network, Redis, or messaging side effects. This change adds gRPC behavior support and a dry-run evaluation API so mock definitions can cover more integration paths and be tested safely.

## Related Work

### Related Changes

- `add-http-yaml-mock-server`: Established the lightweight YAML-driven HTTP mock server, request matching, condition evaluation, and action execution model. This change extends that model to gRPC service/method matching and reuses first-match behavior selection for a new transport.
- `add-template-helpers-file-backed-bodies`: Added richer request-derived template helpers and file-backed response bodies. This change applies the same request-context rendering approach to gRPC metadata, payloads, and file-backed gRPC replies.
- `add-hot-reload-cors-binary-admin-cli`: Expanded operational HTTP mock behavior and admin workflows. This change complements those admin-oriented improvements with an evaluation endpoint that reports what would happen without executing side effects.

### Related Specs

- `http-behavior-mocking/add-http-yaml-mock-server`: Defines HTTP method/path matching, condition routing, action ordering, and response defaults. This change adapts those matching and ordering rules for gRPC and dry-run evaluation.
- `template-rendering/add-reusable-templates-inheritance-values-action-ordering`: Defines the shared template context and rendering behavior. This change reuses that rendering model while adding gRPC-specific context variables.
- `http-behavior-mocking/add-stateful-actions`: Defines ordered action execution across side-effecting actions. This change builds on that ordering while evaluating only safe rendered results in dry-run mode.

## What Changes

- Add optional HTTP/2 cleartext gRPC serving controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
- Add `expect.grpc` matching by fully-qualified protobuf service name and method.
- Decode inbound gRPC protobuf frames into JSON template context and encode rendered `reply_grpc` JSON payloads into standard gRPC response frames.
- Add `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader` template context values.
- Add `reply_grpc` actions with inline or file-backed payloads, rendered metadata headers, and default successful gRPC response headers.
- Add `POST /api/v1/evaluate` to validate a single mock definition against simulated channel context and return matched/rendered results without side effects.
- Extend dry-run evaluation to support HTTP, Kafka, AMQP, and gRPC matchers, while only reporting rendered `reply_http` and `publish_kafka` action results.

## Capabilities

### New Capabilities

- `grpc-behavior-mocking`: gRPC server configuration, descriptor loading, gRPC request matching, protobuf decoding/encoding, template context, and `reply_grpc` behavior.
- `mock-evaluation`: Dry-run API for validating one mock definition against simulated channel context and returning match, condition, and rendered action results without side effects.

### Modified Capabilities

- `mock-definition-loading`: Add schema validation for `expect.grpc`, `reply_grpc`, gRPC descriptor configuration, and evaluate-request mock validation.
- `template-rendering`: Add gRPC request fields to the shared template context used by conditions and rendered action fields.
- `http-behavior-mocking`: Reuse action ordering and rendered HTTP reply defaults for dry-run evaluation output without executing actual actions.

## Impact

- Affected APIs: new gRPC listener, new `POST /api/v1/evaluate` HTTP endpoint, new `expect.grpc` matcher, and new `reply_grpc` action.
- Affected configuration: `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.
- Affected code: `hmock.py` server startup/configuration, mock schema validation/loading, template context construction, behavior matching, action rendering, and HTTP API routing.
- Dependencies may need protobuf/gRPC support capable of loading descriptor sets, decoding length-prefixed gRPC frames, and encoding response messages.
