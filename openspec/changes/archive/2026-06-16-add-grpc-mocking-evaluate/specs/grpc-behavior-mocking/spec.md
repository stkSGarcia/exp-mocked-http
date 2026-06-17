## ADDED Requirements

> Extends: http-behavior-mocking/add-http-yaml-mock-server

### Requirement: gRPC Server Configuration
The system SHALL provide an optional HTTP/2 cleartext gRPC server controlled by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`.

#### Scenario: gRPC disabled by default
- **GIVEN** `HM_GRPC_ENABLED` is absent or `false`
- **WHEN** the mock server starts
- **THEN** the system SHALL NOT start the gRPC listener
- **AND** startup SHALL NOT require gRPC descriptor-set configuration

#### Scenario: gRPC cleartext server starts
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **WHEN** the mock server starts with valid gRPC behavior configuration
- **THEN** the system SHALL start an HTTP/2 cleartext gRPC listener on `HM_GRPC_HOST` and `HM_GRPC_PORT`
- **AND** the system SHALL NOT require or configure TLS

#### Scenario: gRPC defaults are used
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **WHEN** `HM_GRPC_HOST` and `HM_GRPC_PORT` are absent
- **THEN** the system SHALL bind the gRPC listener to `0.0.0.0:50051`

### Requirement: gRPC Descriptor Loading
The system SHALL load protobuf descriptor-set files from `HM_GRPC_DESCRIPTOR_SET_PATHS` when loaded gRPC behaviors require protobuf request or response decoding.

#### Scenario: Relative descriptor paths resolve from templates directory
- **GIVEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains a relative path
- **WHEN** the system loads descriptor-set files
- **THEN** the system SHALL resolve the relative path from `HM_TEMPLATES_DIR`

#### Scenario: Missing descriptor config fails when required
- **GIVEN** gRPC is enabled and at least one loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty
- **THEN** startup SHALL fail with a validation error

#### Scenario: Invalid descriptor config fails when required
- **GIVEN** gRPC is enabled and at least one loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** any configured descriptor-set file is missing, unreadable, or invalid
- **THEN** startup SHALL fail with a validation error

#### Scenario: Descriptor config is optional without gRPC behaviors
- **GIVEN** gRPC is enabled and no loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty
- **THEN** startup SHALL succeed

### Requirement: gRPC Behavior Matching
The system SHALL match gRPC requests against behaviors by `expect.grpc.service` and `expect.grpc.method` using first-match wins (adapts http-behavior-mocking/add-http-yaml-mock-server/method-and-path-matching).

#### Scenario: Exact service and method match
- **GIVEN** a loaded behavior defines `expect.grpc.service` and `expect.grpc.method`
- **WHEN** a gRPC request has the same fully-qualified service name and method
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Service mismatch does not match
- **GIVEN** a loaded behavior defines `expect.grpc.service` and `expect.grpc.method`
- **WHEN** a gRPC request has a different service name
- **THEN** the behavior SHALL NOT match the request

#### Scenario: Method mismatch does not match
- **GIVEN** a loaded behavior defines `expect.grpc.service` and `expect.grpc.method`
- **WHEN** a gRPC request has the same service name and a different method
- **THEN** the behavior SHALL NOT match the request

#### Scenario: First matching behavior wins
- **GIVEN** multiple loaded gRPC behaviors match the same service and method
- **WHEN** the first matching behavior condition passes
- **THEN** the system SHALL select that behavior
- **AND** the system SHALL stop evaluating later gRPC behaviors

### Requirement: gRPC Request Template Context
The system SHALL decode inbound standard gRPC length-prefixed protobuf requests to JSON and expose matched request data as `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`.

#### Scenario: Request payload decodes to JSON
- **GIVEN** a loaded descriptor-set contains the request message for the matched service and method
- **WHEN** a gRPC request frame is received
- **THEN** the system SHALL decode the protobuf message to a JSON string
- **AND** `.GRPCPayload` SHALL contain that JSON string

#### Scenario: Service and method context are available
- **GIVEN** a gRPC behavior matches a request
- **WHEN** the system renders the behavior condition or action fields
- **THEN** `.GRPCService` SHALL contain the matched service name
- **AND** `.GRPCMethod` SHALL contain the matched method name

#### Scenario: Metadata context is available
- **GIVEN** a gRPC request includes HTTP/2 headers or gRPC metadata
- **WHEN** a template uses `.GRPCHeader.Get "key"`
- **THEN** the system SHALL provide the matching metadata value

### Requirement: gRPC Reply Action
The system SHALL render `reply_grpc.payload` or `reply_grpc.payload_from_file` as JSON and encode the result as the configured protobuf response message.

#### Scenario: Inline reply payload renders
- **GIVEN** a selected behavior contains `reply_grpc.payload`
- **WHEN** the system executes the `reply_grpc` action
- **THEN** the system SHALL render the payload as a template
- **AND** encode the rendered JSON as the protobuf response message

#### Scenario: File-backed reply payload renders
- **GIVEN** a selected behavior contains `reply_grpc.payload_from_file`
- **WHEN** the system executes the `reply_grpc` action
- **THEN** the system SHALL render the loaded file content as a template
- **AND** encode the rendered JSON as the protobuf response message

#### Scenario: Inline payload takes precedence
- **GIVEN** a selected behavior contains non-empty `reply_grpc.payload` and `reply_grpc.payload_from_file`
- **WHEN** the system executes the `reply_grpc` action
- **THEN** the system SHALL render and encode the inline payload

#### Scenario: Standard gRPC response framing
- **GIVEN** a selected behavior executes `reply_grpc`
- **WHEN** the response payload is encoded
- **THEN** the system SHALL return standard gRPC length-prefixed response framing

#### Scenario: Successful gRPC response headers
- **GIVEN** a selected behavior executes `reply_grpc`
- **WHEN** the system sends the response
- **THEN** the response SHALL include `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc`
- **AND** the response SHALL include rendered custom metadata from `reply_grpc.headers`
