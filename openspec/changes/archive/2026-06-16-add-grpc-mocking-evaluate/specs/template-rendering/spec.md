## ADDED Requirements

> Extends: template-rendering/add-reusable-templates-inheritance-values-action-ordering

### Requirement: gRPC Template Context
The system SHALL expose gRPC request fields to conditions, `reply_grpc.payload`, `reply_grpc.payload_from_file`, and `reply_grpc.headers` through the shared template rendering context.

#### Scenario: gRPC service context is available
- **GIVEN** a gRPC behavior matches a request
- **WHEN** a template uses `.GRPCService`
- **THEN** the system SHALL render the matched fully-qualified protobuf service name

#### Scenario: gRPC method context is available
- **GIVEN** a gRPC behavior matches a request
- **WHEN** a template uses `.GRPCMethod`
- **THEN** the system SHALL render the matched protobuf method name

#### Scenario: gRPC payload context is available
- **GIVEN** a gRPC behavior matches a request
- **WHEN** a template uses `.GRPCPayload`
- **THEN** the system SHALL render the request protobuf message converted to a JSON string

#### Scenario: gRPC header context is available
- **GIVEN** a gRPC behavior matches a request with metadata
- **WHEN** a template uses `.GRPCHeader.Get "key"`
- **THEN** the system SHALL render the matching HTTP/2 header or gRPC metadata value

#### Scenario: gRPC headers render as templates
- **GIVEN** a selected behavior executes `reply_grpc` with configured headers
- **WHEN** the response headers are prepared
- **THEN** every configured `reply_grpc.headers` value SHALL render as a template using the gRPC request context
