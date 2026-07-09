## ADDED Requirements

> Extends: mock-definition-loading/add-http-yaml-mock-server

### Requirement: Kafka Runtime Configuration (adapts mock-definition-loading/add-http-yaml-mock-server/server-configuration)
The system SHALL read Kafka runtime configuration from environment variables using documented defaults when variables are absent.

#### Scenario: Kafka disabled by default
- **WHEN** `HM_KAFKA_ENABLED` is absent
- **THEN** Kafka consume and publish support SHALL be disabled

#### Scenario: Shared Kafka defaults
- **WHEN** `HM_KAFKA_ENABLED` is `true` and no other Kafka variables are set
- **THEN** the system SHALL use `hmock` as the Kafka client ID
- **AND** the system SHALL use `kafka:9092` as the shared seed broker list
- **AND** the system SHALL leave shared TLS disabled
- **AND** the system SHALL leave shared SASL disabled

#### Scenario: Producer and consumer overrides
- **WHEN** producer- or consumer-specific Kafka variables are set
- **THEN** the producer SHALL use `HM_KAFKA_PRODUCER_SEED_BROKERS`, `HM_KAFKA_SASL_PRODUCER_USERNAME`, `HM_KAFKA_SASL_PRODUCER_PASSWORD`, and `HM_KAFKA_TLS_PRODUCER_ENABLED` when present
- **AND** the consumer SHALL use `HM_KAFKA_CONSUMER_SEED_BROKERS`, `HM_KAFKA_SASL_CONSUMER_USERNAME`, `HM_KAFKA_SASL_CONSUMER_PASSWORD`, and `HM_KAFKA_TLS_CONSUMER_ENABLED` when present
- **AND** each missing producer or consumer setting SHALL fall back to the corresponding shared setting

#### Scenario: SASL enablement after override resolution
- **WHEN** Kafka producer or consumer credentials are resolved from specific overrides and shared defaults
- **THEN** that client SHALL enable SASL only when its resolved username and password are both non-empty

### Requirement: Kafka Mock Schema (adapts mock-definition-loading/add-http-yaml-mock-server/behavior-schema-validation)
The system SHALL validate Kafka expectations and publish actions in loaded mock definitions before consuming or publishing Kafka messages.

#### Scenario: Kafka expectation requires topic
- **WHEN** a loaded behavior contains `expect.kafka`
- **THEN** the system SHALL require `expect.kafka.topic` to be a non-empty string

#### Scenario: Kafka publish requires payload source
- **WHEN** a loaded behavior contains `publish_kafka`
- **THEN** the system SHALL require `publish_kafka.topic` to be a non-empty string
- **AND** the system SHALL require either `publish_kafka.payload` or `publish_kafka.payload_from_file`

### Requirement: Kafka Expectation Matching
The system SHALL consume messages from Kafka topics referenced by loaded mocks, match messages by topic, evaluate `condition` with a Kafka template context, and execute every matching behavior in loaded order.

#### Scenario: Referenced topics are consumed
- **WHEN** Kafka is enabled and mock definitions include `expect.kafka.topic` values
- **THEN** the system SHALL subscribe to each referenced Kafka topic

#### Scenario: Kafka template context
- **WHEN** a Kafka message is evaluated
- **THEN** the template context SHALL expose `.KafkaTopic` as the consumed topic
- **AND** the template context SHALL expose `.KafkaPayload` as the message payload string

#### Scenario: Every matching Kafka behavior executes
- **WHEN** a Kafka message matches multiple loaded behaviors for its topic and conditions
- **THEN** the system SHALL execute every matching behavior
- **AND** the system SHALL execute those behaviors in loaded order

### Requirement: Kafka Publish Action
The system SHALL publish Kafka messages to the configured producer using template-rendered payloads.

#### Scenario: Inline Kafka payload renders
- **WHEN** a matching behavior executes a `publish_kafka` action with `topic` and `payload`
- **THEN** the system SHALL render `payload` with the active template context
- **AND** the system SHALL publish the rendered payload to `topic`

#### Scenario: File-backed Kafka payload renders
- **WHEN** a matching behavior executes a `publish_kafka` action with `payload_from_file`
- **THEN** the system SHALL load the file using the same resolution rules as other `*_from_file` fields
- **AND** the system SHALL render the loaded content with the active template context before publishing
