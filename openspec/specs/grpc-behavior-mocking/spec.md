## Purpose

Define gRPC runtime configuration, protobuf descriptor loading, service and method matching, request decoding, template context, and response encoding behavior for `hmock.py`.

## Requirements

### Requirement: gRPC Runtime Configuration
The system SHALL start gRPC serving only when `HM_GRPC_ENABLED` is enabled and SHALL use configured host, port, and descriptor-set paths.

#### Scenario: gRPC disabled by default
- **WHEN** the server starts without `HM_GRPC_ENABLED`
- **THEN** the system SHALL NOT start a gRPC server

#### Scenario: gRPC server uses default address
- **WHEN** the server starts with `HM_GRPC_ENABLED=true` and no gRPC host or port overrides
- **THEN** the gRPC server SHALL listen on host `0.0.0.0` and port `50051`

#### Scenario: gRPC server uses configured address
- **WHEN** the server starts with `HM_GRPC_ENABLED=true`, `HM_GRPC_HOST`, and `HM_GRPC_PORT`
- **THEN** the gRPC server SHALL listen on the configured host and port

#### Scenario: gRPC uses cleartext HTTP/2
- **WHEN** the gRPC server accepts requests
- **THEN** it SHALL use HTTP/2 cleartext and SHALL NOT require TLS

#### Scenario: Relative descriptor-set path resolves from templates directory
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains a relative path
- **THEN** the system SHALL resolve that path relative to `HM_TEMPLATES_DIR`

#### Scenario: Descriptor config is not required without gRPC behaviors
- **WHEN** `HM_GRPC_ENABLED=true` and no loaded behavior uses `expect.grpc` or `reply_grpc`
- **THEN** startup SHALL succeed without `HM_GRPC_DESCRIPTOR_SET_PATHS`

#### Scenario: Descriptor config is required by gRPC behaviors
- **WHEN** `HM_GRPC_ENABLED=true` and a loaded behavior uses `expect.grpc` or `reply_grpc`
- **THEN** startup SHALL fail if `HM_GRPC_DESCRIPTOR_SET_PATHS` is missing, unreadable, or invalid

### Requirement: gRPC Service And Method Matching
The system SHALL match gRPC requests against behaviors by `expect.grpc.service` and `expect.grpc.method`.

#### Scenario: Exact service and method match
- **WHEN** a gRPC request service and method exactly match a behavior's `expect.grpc.service` and `expect.grpc.method`
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Service mismatch
- **WHEN** a gRPC request method matches but the service differs from `expect.grpc.service`
- **THEN** that behavior SHALL NOT match the gRPC request

#### Scenario: Method mismatch
- **WHEN** a gRPC request service matches but the method differs from `expect.grpc.method`
- **THEN** that behavior SHALL NOT match the gRPC request

#### Scenario: First matching gRPC behavior wins
- **WHEN** several loaded gRPC behaviors match the same service, method, and passing condition
- **THEN** the system SHALL execute the first matching behavior in loaded order and SHALL NOT evaluate later matching behaviors for that request

### Requirement: gRPC Protobuf Request Decoding
The system SHALL decode inbound gRPC protobuf request messages using the configured descriptor sets and expose the decoded request JSON to templates.

#### Scenario: Unary request frame is decoded
- **WHEN** a unary gRPC request is received for a configured service and method
- **THEN** the system SHALL decode the standard gRPC length-prefixed protobuf request body using the method input message descriptor

#### Scenario: Decoded request is exposed as JSON
- **WHEN** a gRPC request body is decoded successfully
- **THEN** the template context SHALL expose the decoded request as a JSON string in `.GRPCPayload`

#### Scenario: Unknown service or method fails
- **WHEN** a gRPC request targets a service or method not present in the loaded descriptor registry
- **THEN** the system SHALL return a gRPC error response instead of executing a behavior

### Requirement: gRPC Reply Action
The system SHALL render `reply_grpc` actions as JSON, encode them with the configured protobuf response descriptor, and return standard gRPC framing and metadata.

#### Scenario: Inline gRPC payload is rendered
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `payload`
- **THEN** the system SHALL render `payload` as a template using the gRPC request context

#### Scenario: File-backed gRPC payload is rendered
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `payload_from_file` and no non-empty `payload`
- **THEN** the system SHALL render the loaded file content as the gRPC response JSON

#### Scenario: Inline gRPC payload takes precedence
- **WHEN** a `reply_grpc` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and use the inline `payload`

#### Scenario: Rendered JSON is encoded as response protobuf
- **WHEN** a selected gRPC behavior renders a `reply_grpc` payload
- **THEN** the system SHALL encode the rendered JSON using the matched method output message descriptor

#### Scenario: gRPC response uses standard framing
- **WHEN** a selected gRPC behavior returns a response protobuf message
- **THEN** the system SHALL send standard gRPC length-prefixed response framing

#### Scenario: gRPC success headers are included
- **WHEN** a selected gRPC behavior returns successfully
- **THEN** the response SHALL include `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc`

#### Scenario: Custom gRPC metadata headers are rendered
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `headers`
- **THEN** each configured header value SHALL be rendered as a template and included with the gRPC response metadata
