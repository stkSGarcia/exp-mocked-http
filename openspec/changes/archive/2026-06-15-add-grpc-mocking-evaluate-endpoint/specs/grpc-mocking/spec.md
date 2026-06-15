## ADDED Requirements

### Requirement: gRPC Runtime Configuration
The system SHALL support opt-in cleartext HTTP/2 gRPC serving using environment-driven configuration.

#### Scenario: gRPC is disabled by default
- **WHEN** the server starts without `HM_GRPC_ENABLED`
- **THEN** the system SHALL NOT start the gRPC server

#### Scenario: gRPC defaults are used when enabled
- **WHEN** the server starts with `HM_GRPC_ENABLED` set to `true` and no gRPC host or port variables set
- **THEN** the system SHALL bind the gRPC server to `0.0.0.0` and listen on port `50051`

#### Scenario: gRPC configuration overrides are used
- **WHEN** the server starts with `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, and `HM_GRPC_PORT` set
- **THEN** the system SHALL use those values for gRPC enablement, bind address, and listen port

#### Scenario: gRPC uses cleartext HTTP/2
- **WHEN** the gRPC server is enabled
- **THEN** the system SHALL serve gRPC over HTTP/2 cleartext without TLS

### Requirement: gRPC Descriptor Loading
The system SHALL load configured protobuf descriptor-set files for gRPC request decoding and response encoding when loaded gRPC behavior requires descriptors.

#### Scenario: Descriptor paths resolve relative to templates directory
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains a relative path
- **THEN** the system SHALL resolve that path relative to `HM_TEMPLATES_DIR`

#### Scenario: Descriptor paths accept comma-separated files
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains multiple comma-separated paths
- **THEN** the system SHALL load descriptors from each listed file

#### Scenario: Missing required descriptor config fails startup
- **WHEN** gRPC is enabled and a loaded behavior defines `expect.grpc` or `reply_grpc` but `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty
- **THEN** startup SHALL fail with a validation error

#### Scenario: Invalid required descriptor config fails startup
- **WHEN** gRPC is enabled and a loaded behavior defines `expect.grpc` or `reply_grpc` but a configured descriptor-set file is missing, unreadable, invalid, or lacks the configured service and method messages
- **THEN** startup SHALL fail with a validation error

#### Scenario: Descriptor config is optional when no gRPC behavior is loaded
- **WHEN** gRPC is enabled and no loaded behavior defines `expect.grpc` or `reply_grpc`
- **THEN** startup SHALL succeed without `HM_GRPC_DESCRIPTOR_SET_PATHS`

### Requirement: gRPC Request Matching
The system SHALL match gRPC requests against behaviors by `expect.grpc.service` and `expect.grpc.method` using first-match wins.

#### Scenario: Service and method match
- **WHEN** a gRPC request service and method exactly match a behavior's `expect.grpc.service` and `expect.grpc.method`
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Service mismatch is ignored
- **WHEN** a gRPC request method matches but the service differs from `expect.grpc.service`
- **THEN** the behavior SHALL NOT match the request

#### Scenario: Method mismatch is ignored
- **WHEN** a gRPC request service matches but the method differs from `expect.grpc.method`
- **THEN** the behavior SHALL NOT match the request

#### Scenario: First matching gRPC behavior wins
- **WHEN** multiple loaded gRPC behaviors match the same service and method and pass condition evaluation
- **THEN** the system SHALL execute only the first matching behavior in load order

### Requirement: gRPC Protobuf Handling
The system SHALL decode inbound gRPC request messages to JSON and encode rendered JSON responses using configured protobuf descriptors and standard gRPC length-prefixed framing.

#### Scenario: Request frame is decoded to JSON
- **WHEN** a unary gRPC request is received for a configured service and method
- **THEN** the system SHALL decode the standard gRPC length-prefixed protobuf request body and expose the protobuf JSON representation to templates

#### Scenario: Response JSON is encoded to protobuf
- **WHEN** a selected gRPC behavior executes `reply_grpc`
- **THEN** the system SHALL render the response JSON and encode it as the protobuf response message for the matched service and method

#### Scenario: Response frame is length-prefixed
- **WHEN** a selected gRPC behavior returns a response message
- **THEN** the system SHALL send the protobuf bytes using standard gRPC length-prefixed framing

### Requirement: gRPC Reply Action
The system SHALL render and return gRPC responses from `reply_grpc` actions.

#### Scenario: Inline gRPC payload renders
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `payload`
- **THEN** the system SHALL render `payload` as a template before protobuf response encoding

#### Scenario: File-backed gRPC payload renders
- **WHEN** a selected gRPC behavior executes `reply_grpc` with `payload_from_file` and no non-empty `payload`
- **THEN** the system SHALL render the loaded file content as the response JSON before protobuf response encoding

#### Scenario: Inline gRPC payload takes precedence
- **WHEN** a `reply_grpc` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and encode the inline `payload`

#### Scenario: gRPC response headers are included
- **WHEN** a selected gRPC behavior executes `reply_grpc` with metadata headers
- **THEN** the system SHALL render each configured header value and include the custom metadata in the gRPC response

#### Scenario: Successful gRPC response includes required headers
- **WHEN** a selected gRPC behavior executes `reply_grpc`
- **THEN** the response SHALL include `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc`
