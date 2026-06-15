## ADDED Requirements

### Requirement: gRPC Expectation Validation
The system SHALL validate gRPC expectations in loaded behavior definitions.

#### Scenario: gRPC behavior accepts service and method
- **WHEN** a loaded concrete behavior defines `expect.grpc.service` and `expect.grpc.method` as non-empty strings
- **THEN** the system SHALL accept the behavior as eligible for gRPC request matching

#### Scenario: gRPC behavior rejects missing service
- **WHEN** a loaded concrete behavior defines `expect.grpc` without a non-empty string `service`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC behavior rejects missing method
- **WHEN** a loaded concrete behavior defines `expect.grpc` without a non-empty string `method`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC participates in exactly-one trigger validation
- **WHEN** a loaded concrete behavior defines `expect.grpc` together with another concrete trigger such as `expect.http`, `expect.kafka`, or `expect.amqp`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: gRPC Reply Action Validation
The system SHALL validate `reply_grpc` action payloads before serving requests.

#### Scenario: gRPC reply accepts inline payload
- **WHEN** a loaded behavior contains `reply_grpc` with string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: gRPC reply accepts file payload
- **WHEN** a loaded behavior contains `reply_grpc` with `payload_from_file` and no non-empty `payload`
- **THEN** the system SHALL resolve and snapshot the file content relative to `HM_TEMPLATES_DIR`

#### Scenario: gRPC reply requires payload source
- **WHEN** a loaded behavior contains `reply_grpc` without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC reply validates headers
- **WHEN** a loaded behavior contains `reply_grpc.headers`
- **THEN** the system SHALL require `headers` to be a string map

#### Scenario: gRPC reply file path outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_grpc.payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
