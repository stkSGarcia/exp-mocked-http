## ADDED Requirements

### Requirement: gRPC Template Context
The system SHALL render gRPC behavior conditions and `reply_grpc` fields using the gRPC request and behavior template context.

#### Scenario: gRPC service context is available
- **WHEN** a gRPC-triggered template uses `.GRPCService`
- **THEN** the system SHALL provide the matched gRPC service name

#### Scenario: gRPC method context is available
- **WHEN** a gRPC-triggered template uses `.GRPCMethod`
- **THEN** the system SHALL provide the matched gRPC method name

#### Scenario: gRPC payload context is available
- **WHEN** a gRPC-triggered template uses `.GRPCPayload`
- **THEN** the system SHALL provide the decoded request payload JSON string

#### Scenario: gRPC metadata context is available
- **WHEN** a gRPC-triggered template uses `.GRPCHeader.Get "key"`
- **THEN** the system SHALL provide the matching HTTP/2 header or gRPC metadata value

#### Scenario: gRPC values context is available
- **WHEN** a selected gRPC behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: gRPC template functions are available
- **WHEN** a gRPC behavior condition or `reply_grpc` field uses an existing supported template function
- **THEN** the system SHALL evaluate that function using the same function semantics as HTTP-triggered templates

### Requirement: gRPC Publish Payload Rendering
The system SHALL render broker publish action payloads with the current gRPC trigger context.

#### Scenario: gRPC-triggered Kafka publish uses gRPC context
- **WHEN** a gRPC-selected behavior executes `publish_kafka`
- **THEN** the system SHALL render the publish fields with the gRPC request context

#### Scenario: gRPC-triggered AMQP publish uses gRPC context
- **WHEN** a gRPC-selected behavior executes `publish_amqp`
- **THEN** the system SHALL render the publish fields with the gRPC request context
