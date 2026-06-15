## ADDED Requirements

### Requirement: Broker Runtime Configuration
The system SHALL read Kafka and AMQP runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Kafka and AMQP defaults are disabled
- **WHEN** the server starts without Kafka or AMQP environment variables
- **THEN** `HM_KAFKA_ENABLED` SHALL default to `false` and `HM_AMQP_ENABLED` SHALL default to `false`

#### Scenario: Kafka environment variables are loaded
- **WHEN** the server starts with Kafka environment variables set
- **THEN** the system SHALL load `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`, `HM_KAFKA_PRODUCER_SEED_BROKERS`, `HM_KAFKA_CONSUMER_SEED_BROKERS`, `HM_KAFKA_SASL_PRODUCER_USERNAME`, `HM_KAFKA_SASL_PRODUCER_PASSWORD`, `HM_KAFKA_SASL_CONSUMER_USERNAME`, `HM_KAFKA_SASL_CONSUMER_PASSWORD`, `HM_KAFKA_TLS_PRODUCER_ENABLED`, and `HM_KAFKA_TLS_CONSUMER_ENABLED`

#### Scenario: AMQP environment variables are loaded
- **WHEN** the server starts with AMQP environment variables set
- **THEN** the system SHALL load `HM_AMQP_ENABLED` and `HM_AMQP_URL`

### Requirement: Broker Expectation Validation
The system SHALL validate Kafka and AMQP expectation fields before serving requests or consuming messages.

#### Scenario: Kafka expectation accepts topic
- **WHEN** a loaded behavior defines `expect.kafka.topic` as a non-empty string
- **THEN** the system SHALL accept the Kafka expectation

#### Scenario: Kafka expectation rejects missing topic
- **WHEN** a loaded behavior defines `expect.kafka` without a non-empty string `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation accepts required fields
- **WHEN** a loaded behavior defines `expect.amqp.exchange` and `expect.amqp.routing_key` as strings
- **THEN** the system SHALL accept the AMQP expectation

#### Scenario: AMQP expectation rejects missing exchange
- **WHEN** a loaded behavior defines `expect.amqp` without a string `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation rejects missing routing key
- **WHEN** a loaded behavior defines `expect.amqp` without a string `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP queue must be string when present
- **WHEN** a loaded behavior defines `expect.amqp.queue`
- **THEN** the system SHALL reject that behavior unless the queue value is a string

#### Scenario: Broker-only behavior is accepted
- **WHEN** a loaded behavior defines `expect.kafka` or `expect.amqp` and omits `expect.http`
- **THEN** the system SHALL accept the behavior when the broker expectation and actions are otherwise valid

### Requirement: Broker Publish Action Validation
The system SHALL validate `publish_kafka` and `publish_amqp` action payloads before serving requests or consuming messages.

#### Scenario: Kafka publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic` and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic` and string `payload_from_file`
- **THEN** the system SHALL accept the action as valid without requiring `payload`

#### Scenario: Kafka publish action rejects missing topic
- **WHEN** a loaded behavior contains a `publish_kafka` action without a non-empty string `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Kafka publish action requires payload source
- **WHEN** a loaded behavior contains a `publish_kafka` action without a non-empty `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, and string `payload_from_file`
- **THEN** the system SHALL accept the action as valid without requiring `payload`

#### Scenario: AMQP publish action rejects missing exchange
- **WHEN** a loaded behavior contains a `publish_amqp` action without a string `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action rejects missing routing key
- **WHEN** a loaded behavior contains a `publish_amqp` action without a string `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action requires payload source
- **WHEN** a loaded behavior contains a `publish_amqp` action without a non-empty `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker File-Backed Payload Loading
The system SHALL load file-backed Kafka and AMQP publish payloads during mock definition loading.

#### Scenario: Kafka publish payload file resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: AMQP publish payload file resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_amqp.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Broker payload file is snapshotted at load time
- **WHEN** a loaded behavior defines `payload_from_file` for `publish_kafka` or `publish_amqp`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing broker payload file is rejected
- **WHEN** a loaded behavior defines broker `payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker payload file outside templates directory is rejected
- **WHEN** a loaded behavior defines broker `payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
