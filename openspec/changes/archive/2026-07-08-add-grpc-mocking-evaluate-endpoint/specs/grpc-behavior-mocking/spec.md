## ADDED Requirements

> Extends: template-rendering/add-http-yaml-mock-server
> Extends: http-behavior-mocking/add-template-helpers-file-backed-bodies

### Requirement: gRPC Server Configuration
The system SHALL expose an optional gRPC server over HTTP/2 cleartext without TLS when `HM_GRPC_ENABLED` is `true`.

#### Scenario: Disabled by default
- **GIVEN** `HM_GRPC_ENABLED` is unset or `false`
- **WHEN** the mock server starts
- **THEN** no gRPC listener is started

#### Scenario: Enabled server binds configured address
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **AND** `HM_GRPC_HOST` and `HM_GRPC_PORT` are configured
- **WHEN** the mock server starts
- **THEN** the gRPC server listens on the configured host and port using HTTP/2 cleartext
- **AND** TLS is not required or negotiated

### Requirement: gRPC Descriptor Loading
The system SHALL load protobuf descriptor-set files from `HM_GRPC_DESCRIPTOR_SET_PATHS` for configured gRPC behaviors that need protobuf request or response encoding.

#### Scenario: Relative descriptor paths
- **GIVEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains a relative path
- **WHEN** the gRPC descriptor configuration is loaded
- **THEN** the path is resolved relative to `HM_TEMPLATES_DIR`

#### Scenario: Descriptor configuration required
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **AND** at least one loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` is missing, unreadable, or invalid
- **THEN** startup fails with a validation error

#### Scenario: Descriptor configuration not required
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **AND** no loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` is unset
- **THEN** startup succeeds

### Requirement: gRPC Behavior Matching
The system SHALL support `expect.grpc` matchers with `service` and `method` fields and select matching gRPC behaviors by fully-qualified protobuf service name and method name.

#### Scenario: Service and method match
- **GIVEN** a gRPC request for a configured protobuf service and method
- **AND** a behavior declares the same `expect.grpc.service` and `expect.grpc.method`
- **WHEN** gRPC behaviors are evaluated
- **THEN** the behavior matches

#### Scenario: First match wins
- **GIVEN** multiple loaded behaviors match the same gRPC service and method
- **WHEN** the gRPC request is evaluated
- **THEN** the first matching behavior is selected

### Requirement: gRPC Template Context
The system SHALL render gRPC conditions, `reply_grpc` payloads, and `reply_grpc` headers using a gRPC template context containing `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`. (adapts template-rendering/add-http-yaml-mock-server/template-context)

#### Scenario: Request context is available
- **GIVEN** a matching gRPC request with HTTP/2 metadata
- **AND** the protobuf request body decodes successfully
- **WHEN** a condition or `reply_grpc` field is rendered
- **THEN** `.GRPCService` contains the matched service name
- **AND** `.GRPCMethod` contains the matched method name
- **AND** `.GRPCPayload` contains the request body converted from protobuf to JSON
- **AND** `.GRPCHeader.Get "key"` returns matching HTTP/2 headers and gRPC metadata

### Requirement: gRPC Reply Rendering
The system SHALL render `reply_grpc` actions from JSON into the configured protobuf response message and return standard gRPC length-prefixed response frames.

#### Scenario: Inline payload response
- **GIVEN** a selected behavior has a `reply_grpc.payload` template
- **WHEN** the gRPC reply is rendered
- **THEN** the rendered JSON payload is encoded as the configured protobuf response message
- **AND** the response body uses standard gRPC length-prefixed framing

#### Scenario: File-backed payload response
- **GIVEN** a selected behavior has `reply_grpc.payload_from_file`
- **WHEN** the gRPC reply is rendered
- **THEN** the file content is loaded and rendered as the response JSON payload
- **AND** `reply_grpc.payload` is not required

#### Scenario: Required gRPC response headers
- **GIVEN** a selected behavior has a `reply_grpc` action
- **WHEN** the gRPC response is returned
- **THEN** the response includes `grpc-status: 0`
- **AND** the response includes `grpc-message: OK`
- **AND** the response includes `Content-Type: application/grpc`
- **AND** each custom `reply_grpc.headers` value is rendered and included as gRPC metadata
