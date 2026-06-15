## ADDED Requirements

### Requirement: gRPC Template Context
The system SHALL render gRPC behavior conditions and gRPC reply fields using the current gRPC request context, behavior values, named templates, and template functions.

#### Scenario: gRPC service context is available
- **WHEN** a gRPC-triggered template uses `.GRPCService`
- **THEN** the system SHALL provide the matched fully-qualified protobuf service name as a string

#### Scenario: gRPC method context is available
- **WHEN** a gRPC-triggered template uses `.GRPCMethod`
- **THEN** the system SHALL provide the matched protobuf method name as a string

#### Scenario: gRPC payload context is available
- **WHEN** a gRPC-triggered template uses `.GRPCPayload`
- **THEN** the system SHALL provide the decoded protobuf request body as a JSON string

#### Scenario: gRPC metadata context is available
- **WHEN** a gRPC-triggered template uses `.GRPCHeader.Get "key"`
- **THEN** the system SHALL provide the matching HTTP/2 header or gRPC metadata value

#### Scenario: Behavior values are available to gRPC templates
- **WHEN** a gRPC-triggered behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: Named templates are available to gRPC templates
- **WHEN** a gRPC-triggered behavior uses a registered named template
- **THEN** the system SHALL render the named template with the current gRPC template context
