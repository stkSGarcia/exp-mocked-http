## ADDED Requirements

> Extends: http-yaml-mock-server/add-http-yaml-mock-server

### Requirement: gRPC server configuration
The system SHALL support an optional gRPC server configured by `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`. `HM_GRPC_ENABLED` SHALL default to `false`, `HM_GRPC_HOST` to `0.0.0.0`, `HM_GRPC_PORT` to `50051`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` to an empty value.

#### Scenario: gRPC disabled by default
- **GIVEN** `HM_GRPC_ENABLED` is not set
- **WHEN** the mock server starts
- **THEN** it does not start a gRPC listener

#### Scenario: Enabled cleartext listener
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **WHEN** the mock server starts successfully
- **THEN** it listens on the configured host and port using HTTP/2 cleartext without TLS

### Requirement: Conditional descriptor loading
The system SHALL load the comma-separated protobuf descriptor-set files in `HM_GRPC_DESCRIPTOR_SET_PATHS` when enabled gRPC behaviors require protobuf decoding or encoding. Relative descriptor-set paths SHALL resolve from `HM_TEMPLATES_DIR`.

#### Scenario: Relative descriptor path
- **GIVEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` contains a relative path
- **WHEN** descriptors are loaded
- **THEN** the system resolves that path relative to `HM_TEMPLATES_DIR`

#### Scenario: Missing required descriptor configuration
- **GIVEN** gRPC is enabled and a loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** descriptor-set configuration is empty, unreadable, or invalid
- **THEN** server startup fails with a configuration error

#### Scenario: Descriptors not required
- **GIVEN** gRPC is enabled and no loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** descriptor-set configuration is empty
- **THEN** server startup succeeds

### Requirement: gRPC behavior matching
The system SHALL match concrete gRPC behaviors by the fully-qualified `expect.grpc.service` and `expect.grpc.method` pair, using first-match wins in active load order. (adapts http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering/http-request-matching)

#### Scenario: First matching behavior
- **GIVEN** multiple concrete behaviors match the same gRPC service and method
- **WHEN** a request for that pair is received
- **THEN** the system selects the first matching behavior in active load order

#### Scenario: Service or method differs
- **GIVEN** a concrete behavior whose configured service or method differs from the request
- **WHEN** the request is matched
- **THEN** that behavior is skipped

### Requirement: gRPC template context
The system SHALL expose the matched service as `.GRPCService`, method as `.GRPCMethod`, decoded request JSON as `.GRPCPayload`, and HTTP/2 headers and gRPC metadata as `.GRPCHeader`.

#### Scenario: Render from request context
- **GIVEN** a matched gRPC request with protobuf payload and metadata
- **WHEN** the behavior condition or action template is rendered
- **THEN** the template can read the service, method, decoded JSON payload, and metadata through the gRPC context fields
- **AND** `.GRPCHeader.Get "key"` returns the value for the requested header or metadata key

### Requirement: Protobuf request decoding
The system SHALL resolve configured service methods from loaded descriptors, decode inbound standard gRPC length-prefixed message framing, and convert the request protobuf message to JSON for `.GRPCPayload`.

#### Scenario: Decode framed unary request
- **GIVEN** a gRPC request for a descriptor-resolved service method with one valid framed protobuf message
- **WHEN** the request is processed
- **THEN** the message is decoded using the method input descriptor
- **AND** `.GRPCPayload` contains its JSON representation

### Requirement: gRPC response rendering and encoding
The system SHALL support `reply_grpc` with either a required templated `payload` or `payload_from_file`, plus optional templated metadata `headers`. The rendered JSON SHALL be encoded with the configured method output descriptor and returned using standard gRPC length-prefixed framing.

#### Scenario: Inline response payload
- **GIVEN** a matched behavior has `reply_grpc.payload`
- **WHEN** the action is rendered
- **THEN** the rendered JSON is encoded as the configured protobuf response type and returned as one framed gRPC message

#### Scenario: File-backed response payload
- **GIVEN** a matched behavior has `reply_grpc.payload_from_file`
- **WHEN** the action is rendered
- **THEN** the file-backed content is rendered as JSON and encoded as the configured protobuf response type

#### Scenario: Missing response payload
- **GIVEN** a `reply_grpc` action has neither `payload` nor `payload_from_file`
- **WHEN** the behavior is loaded or validated
- **THEN** the system rejects the action

### Requirement: gRPC response metadata
The system SHALL include `grpc-status: 0`, `grpc-message: OK`, and `Content-Type: application/grpc` on successful `reply_grpc` responses, together with all rendered custom headers.

#### Scenario: Successful response headers
- **GIVEN** a `reply_grpc` action defines custom metadata headers
- **WHEN** a successful response is returned
- **THEN** the response contains the required status, message, and content type headers
- **AND** it contains each rendered custom header
