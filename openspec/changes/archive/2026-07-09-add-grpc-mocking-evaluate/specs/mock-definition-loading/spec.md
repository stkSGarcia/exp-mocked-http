## ADDED Requirements

> Extends: mock-definition-loading/add-http-yaml-mock-server

### Requirement: gRPC Behavior Schema Validation
The system SHALL validate loaded mock definitions containing `expect.grpc` and `reply_grpc` before serving requests. (adapts mock-definition-loading/add-http-yaml-mock-server/behavior-schema-validation)

#### Scenario: gRPC expectation requires service and method
- **GIVEN** a loaded mock definition includes `expect.grpc`
- **WHEN** `expect.grpc.service` or `expect.grpc.method` is empty
- **THEN** behavior validation fails before serving requests

#### Scenario: gRPC reply requires payload source
- **GIVEN** a loaded mock definition includes `reply_grpc`
- **WHEN** both `reply_grpc.payload` and `reply_grpc.payload_from_file` are absent or empty
- **THEN** behavior validation fails before serving requests

#### Scenario: gRPC schema preserves existing matchers
- **GIVEN** a loaded mock definition includes HTTP, Kafka, or AMQP expectations
- **WHEN** behavior validation runs
- **THEN** existing supported matcher validation continues to apply unchanged
