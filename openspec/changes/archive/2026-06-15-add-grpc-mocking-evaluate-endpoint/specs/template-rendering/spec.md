## ADDED Requirements

### Requirement: gRPC Template Context
The system SHALL expose matched gRPC request fields to condition and action template rendering.

#### Scenario: gRPC service context is available
- **WHEN** a gRPC behavior template uses `.GRPCService`
- **THEN** the system SHALL provide the matched fully-qualified protobuf service name

#### Scenario: gRPC method context is available
- **WHEN** a gRPC behavior template uses `.GRPCMethod`
- **THEN** the system SHALL provide the matched protobuf method name

#### Scenario: gRPC payload context is available
- **WHEN** a gRPC behavior template uses `.GRPCPayload`
- **THEN** the system SHALL provide the request body converted from protobuf to a JSON string

#### Scenario: gRPC metadata header context is available
- **WHEN** a gRPC behavior template uses `.GRPCHeader.Get "key"`
- **THEN** the system SHALL provide the matching HTTP/2 header or gRPC metadata value
