## ADDED Requirements

### Requirement: gRPC Server Entry Point
The system SHALL optionally serve gRPC mock requests over HTTP/2 cleartext using the configured gRPC host and port.

#### Scenario: gRPC server is disabled by default
- **WHEN** the server starts without `HM_GRPC_ENABLED`
- **THEN** the system SHALL NOT listen for gRPC requests

#### Scenario: gRPC server starts when enabled
- **WHEN** the server starts with `HM_GRPC_ENABLED=true`
- **THEN** the system SHALL start a cleartext HTTP/2 gRPC server on `HM_GRPC_HOST` and `HM_GRPC_PORT`

#### Scenario: gRPC server does not use TLS
- **WHEN** `HM_GRPC_ENABLED=true`
- **THEN** the gRPC server SHALL accept cleartext HTTP/2 requests and SHALL NOT require TLS configuration

### Requirement: gRPC Descriptor Loading
The system SHALL load protobuf descriptor-set files from `HM_GRPC_DESCRIPTOR_SET_PATHS` for configured gRPC behaviors that require protobuf request or response conversion.

#### Scenario: Relative descriptor path resolves from templates directory
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains a relative path
- **THEN** the system SHALL resolve that path relative to `HM_TEMPLATES_DIR`

#### Scenario: Missing descriptor config fails used gRPC startup
- **WHEN** `HM_GRPC_ENABLED=true`, a loaded behavior uses `expect.grpc` or `reply_grpc`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty
- **THEN** startup SHALL fail with a validation error

#### Scenario: Missing descriptor file fails startup
- **WHEN** `HM_GRPC_ENABLED=true`, a loaded behavior uses `expect.grpc` or `reply_grpc`, and a configured descriptor-set path is unreadable
- **THEN** startup SHALL fail with a validation error

#### Scenario: Invalid descriptor file fails startup
- **WHEN** `HM_GRPC_ENABLED=true`, a loaded behavior uses `expect.grpc` or `reply_grpc`, and a configured descriptor-set file cannot be parsed as a protobuf descriptor set
- **THEN** startup SHALL fail with a validation error

#### Scenario: Descriptor config is optional without gRPC behaviors
- **WHEN** `HM_GRPC_ENABLED=true` and no loaded behavior uses `expect.grpc` or `reply_grpc`
- **THEN** startup SHALL succeed without `HM_GRPC_DESCRIPTOR_SET_PATHS`

#### Scenario: Configured service method requires descriptors
- **WHEN** `HM_GRPC_ENABLED=true` and a loaded behavior uses `expect.grpc`
- **THEN** the descriptor registry SHALL contain that service and method before startup succeeds

### Requirement: gRPC Method Matching
The system SHALL match gRPC behaviors by fully-qualified protobuf service name and method name.

#### Scenario: Exact service and method match
- **WHEN** a gRPC request service and method exactly equal a behavior's `expect.grpc.service` and `expect.grpc.method`
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Service mismatch is ignored
- **WHEN** a gRPC request method matches but the service differs from `expect.grpc.service`
- **THEN** the behavior SHALL NOT match the request

#### Scenario: Method mismatch is ignored
- **WHEN** a gRPC request service matches but the method differs from `expect.grpc.method`
- **THEN** the behavior SHALL NOT match the request

#### Scenario: First matching gRPC behavior wins
- **WHEN** multiple loaded gRPC behaviors could match the same request and pass condition evaluation
- **THEN** the system SHALL execute the first matching behavior in loaded order and stop evaluating later gRPC behaviors

### Requirement: gRPC Protobuf Request Handling
The system SHALL decode inbound unary gRPC protobuf request messages using standard gRPC length-prefixed framing and expose the decoded message as JSON.

#### Scenario: Request payload is decoded to JSON
- **WHEN** a gRPC request targets a configured unary method and contains a valid framed protobuf request
- **THEN** the system SHALL decode the protobuf message using the method request descriptor and expose the JSON string as `.GRPCPayload`

#### Scenario: Invalid request frame is rejected
- **WHEN** a gRPC request contains an invalid gRPC length-prefixed frame
- **THEN** the system SHALL return a gRPC error response and SHALL NOT execute behavior actions

#### Scenario: Invalid protobuf payload is rejected
- **WHEN** a gRPC request frame cannot be decoded using the configured request message descriptor
- **THEN** the system SHALL return a gRPC error response and SHALL NOT execute behavior actions

### Requirement: gRPC Reply Action
The system SHALL render `reply_grpc` actions as JSON and encode the rendered JSON as the configured protobuf response message.

#### Scenario: Inline gRPC payload is rendered and encoded
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `payload`
- **THEN** the system SHALL render the payload as a template, parse it as JSON, encode it as the method response protobuf message, and return standard gRPC length-prefixed framing

#### Scenario: File-backed gRPC payload is rendered and encoded
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `payload_from_file` and no inline `payload`
- **THEN** the system SHALL render the loaded file content as JSON, encode it as the method response protobuf message, and return standard gRPC length-prefixed framing

#### Scenario: Inline gRPC payload takes precedence
- **WHEN** a `reply_grpc` action defines both non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and encode the inline `payload`

#### Scenario: gRPC response headers are included
- **WHEN** a selected gRPC behavior executes `reply_grpc` with custom `headers`
- **THEN** the system SHALL render each custom header value and include it with the response metadata

#### Scenario: Successful gRPC response includes required metadata
- **WHEN** a selected gRPC behavior returns a successful response
- **THEN** the response SHALL include `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc`

#### Scenario: Invalid rendered response JSON is rejected
- **WHEN** a selected gRPC behavior renders `reply_grpc.payload` to invalid JSON
- **THEN** the system SHALL return a gRPC error response and SHALL NOT send a successful protobuf response
