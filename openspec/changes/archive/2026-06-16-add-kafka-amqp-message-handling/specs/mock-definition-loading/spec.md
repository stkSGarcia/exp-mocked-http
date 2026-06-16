## ADDED Requirements

> Extends: mock-definition-loading

### Requirement: Broker Expectation Validation
The system SHALL validate `expect.kafka` and `expect.amqp` payloads before serving or consuming messages.

#### Scenario: Kafka expectation accepts required topic
- **WHEN** a loaded behavior contains `expect.kafka.topic` as a non-empty string
- **THEN** the system SHALL accept the Kafka expectation as valid

#### Scenario: Kafka expectation rejects missing topic
- **WHEN** a loaded behavior contains `expect.kafka` without `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation accepts required fields
- **WHEN** a loaded behavior contains `expect.amqp.exchange` and `expect.amqp.routing_key` as non-empty strings
- **THEN** the system SHALL accept the AMQP expectation as valid

#### Scenario: AMQP expectation rejects missing exchange
- **WHEN** a loaded behavior contains `expect.amqp` without `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation rejects missing routing key
- **WHEN** a loaded behavior contains `expect.amqp` without `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker Publish Action Validation
The system SHALL validate `publish_kafka` and `publish_amqp` action payloads before serving or consuming messages.

#### Scenario: Kafka publish action accepts inline payload
- **WHEN** a loaded behavior contains `publish_kafka.topic` and `publish_kafka.payload` as strings
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action requires a payload source
- **WHEN** a loaded behavior contains `publish_kafka.topic` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action accepts inline payload
- **WHEN** a loaded behavior contains `publish_amqp.exchange`, `publish_amqp.routing_key`, and `publish_amqp.payload` as strings
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action requires a payload source
- **WHEN** a loaded behavior contains `publish_amqp.exchange` and `publish_amqp.routing_key` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker File-Backed Payload Loading
The system SHALL load `publish_kafka.payload_from_file` and `publish_amqp.payload_from_file` content during mock definition loading. (adapts mock-definition-loading/add-template-helpers-file-backed-bodies/file-backed-response-body-loading)

#### Scenario: Broker payload file path resolves relative to templates directory
- **WHEN** a loaded behavior defines a broker publish action with `payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Broker payload file is snapshotted at load time
- **WHEN** a loaded behavior defines a broker publish action with `payload_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing broker payload file is rejected
- **WHEN** a loaded behavior defines a broker publish action with `payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker payload file outside templates directory is rejected
- **WHEN** a loaded behavior defines a broker publish action with `payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
