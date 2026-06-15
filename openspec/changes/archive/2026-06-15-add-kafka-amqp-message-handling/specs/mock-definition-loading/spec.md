## ADDED Requirements

### Requirement: Broker Expectation Validation
The system SHALL validate Kafka and AMQP expectations in loaded behavior definitions.

#### Scenario: Kafka behavior accepts topic
- **WHEN** a loaded concrete behavior defines `expect.kafka.topic` as a non-empty string
- **THEN** the system SHALL accept the behavior as eligible for Kafka message matching

#### Scenario: Kafka behavior rejects missing topic
- **WHEN** a loaded concrete behavior defines `expect.kafka` without a non-empty string `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP behavior accepts exchange and routing key
- **WHEN** a loaded concrete behavior defines `expect.amqp.exchange` and `expect.amqp.routing_key` as non-empty strings
- **THEN** the system SHALL accept the behavior as eligible for AMQP message matching

#### Scenario: AMQP queue defaults during loading
- **WHEN** a loaded concrete behavior defines `expect.amqp` without `queue` or with an empty `queue`
- **THEN** the system SHALL store the effective AMQP queue as the behavior's `expect.amqp.routing_key`

#### Scenario: AMQP behavior rejects missing exchange
- **WHEN** a loaded concrete behavior defines `expect.amqp` without a non-empty string `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP behavior rejects missing routing key
- **WHEN** a loaded concrete behavior defines `expect.amqp` without a non-empty string `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker Publish Action Validation
The system SHALL validate `publish_kafka` and `publish_amqp` action payloads before serving requests or consuming broker messages.

#### Scenario: Kafka publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic` and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic`, string `payload_from_file`, and no `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action rejects missing payload source
- **WHEN** a loaded behavior contains a `publish_kafka` action without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, string `payload_from_file`, and no `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action rejects missing payload source
- **WHEN** a loaded behavior contains a `publish_amqp` action without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker publish file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Broker publish file payload is snapshotted at load time
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing broker publish file payload is rejected
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker publish file payload outside templates directory is rejected
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
