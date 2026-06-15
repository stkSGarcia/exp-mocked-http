## ADDED Requirements

### Requirement: gRPC Server Configuration
The system SHALL read gRPC runtime configuration from environment variables using documented defaults when variables are absent.

#### Scenario: gRPC configuration defaults are used
- **WHEN** the server starts without `HM_GRPC_ENABLED`, `HM_GRPC_PORT`, `HM_GRPC_HOST`, or `HM_GRPC_DESCRIPTOR_SET_PATHS`
- **THEN** the system SHALL treat gRPC as disabled, port as `50051`, host as `0.0.0.0`, and descriptor-set paths as empty

#### Scenario: gRPC configuration overrides are used
- **WHEN** the server starts with `HM_GRPC_ENABLED`, `HM_GRPC_PORT`, `HM_GRPC_HOST`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`
- **THEN** the system SHALL use those values for gRPC enablement, listen port, listen host, and descriptor-set loading

### Requirement: gRPC Expectation Validation
The system SHALL validate `expect.grpc` fields before serving requests.

#### Scenario: gRPC expectation accepts required fields
- **WHEN** a loaded behavior defines `expect.grpc` with string `service` and string `method`
- **THEN** the system SHALL accept the gRPC expectation as valid

#### Scenario: gRPC expectation rejects missing service
- **WHEN** a loaded behavior defines `expect.grpc` without `service`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC expectation rejects missing method
- **WHEN** a loaded behavior defines `expect.grpc` without `method`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC expectation rejects non-mapping value
- **WHEN** a loaded behavior defines `expect.grpc` as a non-mapping value
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: gRPC Reply Validation
The system SHALL validate `reply_grpc` action payloads before serving requests.

#### Scenario: gRPC reply accepts inline payload
- **WHEN** a loaded behavior contains a `reply_grpc` action with string `payload`
- **THEN** the system SHALL accept that action as valid

#### Scenario: gRPC reply accepts file-backed payload
- **WHEN** a loaded behavior contains a `reply_grpc` action with non-empty string `payload_from_file`
- **THEN** the system SHALL load the file content relative to `HM_TEMPLATES_DIR` and accept that action as valid

#### Scenario: gRPC reply requires payload source
- **WHEN** a loaded behavior contains a `reply_grpc` action without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC reply rejects non-string payload
- **WHEN** a loaded behavior contains a `reply_grpc` action with `payload` that is not a string
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC reply rejects non-string headers
- **WHEN** a loaded behavior contains a `reply_grpc` action with a `headers` entry whose value is not a string
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Multiple gRPC replies are rejected
- **WHEN** an effective concrete behavior contains more than one `reply_grpc` action after inheritance is resolved
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Descriptor Validation For Loaded gRPC Behaviors
The system SHALL validate configured descriptor sets against loaded gRPC behaviors when gRPC serving is enabled.

#### Scenario: Descriptor set must contain expected service and method
- **WHEN** `HM_GRPC_ENABLED=true` and a loaded behavior defines `expect.grpc`
- **THEN** startup SHALL fail if no configured descriptor set contains that service and method

#### Scenario: Descriptor set must contain request and response message types
- **WHEN** `HM_GRPC_ENABLED=true` and a loaded behavior defines `expect.grpc` or `reply_grpc`
- **THEN** startup SHALL fail if the matched method input or output message descriptor cannot be resolved
