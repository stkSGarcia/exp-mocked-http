## ADDED Requirements

### Requirement: gRPC server configuration
The server SHALL read `HM_GRPC_ENABLED` (default `false`), `HM_GRPC_PORT` (default `50051`), `HM_GRPC_HOST` (default `0.0.0.0`), and `HM_GRPC_DESCRIPTOR_SET_PATHS` (default empty, comma-separated list of descriptor-set file paths) at startup. When `HM_GRPC_ENABLED=false`, no gRPC server SHALL start. When `HM_GRPC_ENABLED=true`, the server SHALL listen using HTTP/2 cleartext with no TLS.

#### Scenario: gRPC server disabled by default
- **WHEN** `HM_GRPC_ENABLED` is not set
- **THEN** no gRPC server starts and port 50051 is not bound

#### Scenario: gRPC server starts when enabled
- **WHEN** `HM_GRPC_ENABLED=true` and `HM_GRPC_PORT=50051`
- **THEN** the gRPC server listens on `0.0.0.0:50051` using HTTP/2 cleartext

#### Scenario: Custom gRPC port and host
- **WHEN** `HM_GRPC_ENABLED=true`, `HM_GRPC_PORT=9090`, and `HM_GRPC_HOST=127.0.0.1`
- **THEN** the gRPC server listens on `127.0.0.1:9090`

### Requirement: Descriptor-set startup validation
When `HM_GRPC_ENABLED=true` and at least one loaded behavior contains an `expect.grpc` or `reply_grpc` field, the server SHALL fail startup with an error if `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty, any listed file is unreadable, or any file is not a valid protobuf `FileDescriptorSet`. Relative paths SHALL be resolved from `HM_TEMPLATES_DIR`. When no loaded behavior references gRPC fields, the server SHALL start successfully even without descriptor-set config.

#### Scenario: Missing descriptor-set config fails startup when gRPC behavior exists
- **WHEN** `HM_GRPC_ENABLED=true`, `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty, and a loaded behavior has `expect.grpc`
- **THEN** the server exits with a non-zero status and logs an error

#### Scenario: Invalid descriptor-set file fails startup
- **WHEN** `HM_GRPC_ENABLED=true`, `HM_GRPC_DESCRIPTOR_SET_PATHS` points to a file that is not a valid `FileDescriptorSet`
- **THEN** the server exits with a non-zero status and logs an error

#### Scenario: No gRPC behaviors — startup succeeds without descriptor-set config
- **WHEN** `HM_GRPC_ENABLED=true`, `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty, and no loaded behavior references `expect.grpc` or `reply_grpc`
- **THEN** the server starts successfully

#### Scenario: Relative descriptor-set path resolved from templates dir
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS=service.pb` and `HM_TEMPLATES_DIR=/etc/templates`
- **THEN** the server attempts to load `/etc/templates/service.pb`

### Requirement: `expect.grpc` matcher field
A behavior MAY include an `expect.grpc` block with the fields `service` (fully-qualified protobuf service name) and `method` (method name within that service). When present, the behavior SHALL only match gRPC calls whose `(service, method)` pair equals the configured values. gRPC behaviors SHALL be matched using first-match wins.

#### Scenario: gRPC call matches correct service and method
- **WHEN** a gRPC call arrives for service `com.example.Greeter` and method `SayHello`
- **AND** a behavior has `expect.grpc.service: com.example.Greeter` and `expect.grpc.method: SayHello`
- **THEN** the behavior matches and its actions are executed

#### Scenario: gRPC call does not match different method
- **WHEN** a gRPC call arrives for service `com.example.Greeter` and method `SayBye`
- **AND** the only behavior has `expect.grpc.method: SayHello`
- **THEN** no behavior matches

#### Scenario: First-match wins for gRPC
- **WHEN** two behaviors match the same `(service, method)`
- **THEN** only the first behavior's actions are executed

### Requirement: gRPC template context variables
When a gRPC call is matched, the template context SHALL expose: `.GRPCService` (matched service name), `.GRPCMethod` (matched method name), `.GRPCPayload` (request body decoded from protobuf to a JSON string), and `.GRPCHeader` (a header map of HTTP/2 headers and gRPC metadata, accessible via `.GRPCHeader.Get "key"`).

#### Scenario: GRPCPayload contains decoded request JSON
- **WHEN** a gRPC call arrives with a protobuf-encoded request body for a known message type
- **THEN** `.GRPCPayload` contains the JSON representation of that request

#### Scenario: GRPCHeader exposes gRPC metadata
- **WHEN** a gRPC call arrives with metadata key `x-request-id: abc123`
- **THEN** `.GRPCHeader.Get "x-request-id"` returns `"abc123"`

### Requirement: Protobuf request decoding
Inbound gRPC requests SHALL be decoded using standard gRPC length-prefixed framing (5-byte prefix: 1 compression flag byte + 4 big-endian length bytes). The message type SHALL be resolved from the loaded descriptor-set registry using the matched `(service, method)` pair. The decoded protobuf message SHALL be converted to JSON and exposed as `.GRPCPayload`.

#### Scenario: Valid protobuf request decoded to JSON
- **WHEN** a gRPC call arrives with a valid length-prefixed protobuf body
- **THEN** the payload is decoded and `.GRPCPayload` is the JSON string of the decoded message

#### Scenario: Unrecognized service/method returns UNIMPLEMENTED
- **WHEN** a gRPC call arrives for a `(service, method)` with no matching behavior
- **THEN** the server returns gRPC status `12` (UNIMPLEMENTED)

### Requirement: `reply_grpc` action
A behavior MAY include a `reply_grpc` action block with the fields: `payload` (required unless `payload_from_file` is set) — a Jinja2 template string that renders to JSON; `payload_from_file` (optional) — a file path whose content is used as the payload template; `headers` (optional) — a string map of gRPC metadata headers, each value rendered as a Jinja2 template. The server SHALL encode the rendered JSON payload as a protobuf response using the matched method's output message descriptor, then send it with standard gRPC length-prefixed framing. The response SHALL always include `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc`. Custom headers from `headers` SHALL also be included.

#### Scenario: gRPC reply with payload
- **WHEN** a matched behavior has `reply_grpc.payload: '{"message": "hello"}'`
- **THEN** the response is protobuf-encoded from that JSON and sent with `grpc-status: 0` and `Content-Type: application/grpc`

#### Scenario: gRPC reply with custom headers
- **WHEN** a matched behavior has `reply_grpc.headers: {x-trace-id: "{{ .GRPCHeader.Get \"x-request-id\" }}"}`
- **THEN** the rendered `x-trace-id` header is included in the gRPC response metadata

#### Scenario: gRPC reply from file
- **WHEN** a matched behavior has `reply_grpc.payload_from_file: response.json`
- **THEN** the contents of `response.json` are used as the payload template and encoded as protobuf
