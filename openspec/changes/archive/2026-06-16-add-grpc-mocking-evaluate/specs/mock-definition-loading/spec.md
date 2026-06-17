## ADDED Requirements

### Requirement: gRPC Definition Validation
The system SHALL validate `expect.grpc` and `reply_grpc` fields before serving requests.

#### Scenario: gRPC matcher accepts required fields
- **GIVEN** a loaded behavior contains `expect.grpc.service` and `expect.grpc.method` as non-empty strings
- **WHEN** mock definitions are validated
- **THEN** the system SHALL accept the gRPC matcher fields

#### Scenario: gRPC matcher rejects missing service
- **GIVEN** a loaded behavior contains `expect.grpc` without `service`
- **WHEN** mock definitions are validated
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC matcher rejects missing method
- **GIVEN** a loaded behavior contains `expect.grpc` without `method`
- **WHEN** mock definitions are validated
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC reply accepts inline payload
- **GIVEN** a loaded behavior contains `reply_grpc.payload` as a string
- **WHEN** mock definitions are validated
- **THEN** the system SHALL accept the gRPC reply action

#### Scenario: gRPC reply accepts file-backed payload
- **GIVEN** a loaded behavior contains `reply_grpc.payload_from_file` as a string
- **WHEN** mock definitions are validated
- **THEN** the system SHALL accept the gRPC reply action

#### Scenario: gRPC reply requires payload source
- **GIVEN** a loaded behavior contains `reply_grpc` without `payload` or `payload_from_file`
- **WHEN** mock definitions are validated
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: gRPC File-Backed Payload Loading
The system SHALL load `reply_grpc.payload_from_file` content during mock definition loading.

#### Scenario: gRPC payload file path resolves relative to templates directory
- **GIVEN** a loaded behavior defines `reply_grpc.payload_from_file`
- **WHEN** mock definitions are loaded
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: gRPC payload file is snapshotted
- **GIVEN** a loaded behavior defines `reply_grpc.payload_from_file`
- **WHEN** mock definitions are loaded
- **THEN** the system SHALL store a stable snapshot of the file contents

#### Scenario: Missing gRPC payload file is rejected
- **GIVEN** a loaded behavior defines `reply_grpc.payload_from_file`
- **WHEN** the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC payload file outside templates directory is rejected
- **GIVEN** a loaded behavior defines `reply_grpc.payload_from_file`
- **WHEN** the resolved path is outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: gRPC Runtime Configuration Validation
The system SHALL validate gRPC runtime configuration using environment defaults and fail startup only when invalid descriptor configuration is required.

#### Scenario: gRPC environment variables are read
- **GIVEN** `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` are set
- **WHEN** the server starts
- **THEN** the system SHALL include those values in runtime configuration

#### Scenario: gRPC defaults are applied
- **GIVEN** gRPC environment variables are absent
- **WHEN** the server starts
- **THEN** the system SHALL use `false` for `HM_GRPC_ENABLED`, `0.0.0.0` for `HM_GRPC_HOST`, `50051` for `HM_GRPC_PORT`, and no descriptor paths
