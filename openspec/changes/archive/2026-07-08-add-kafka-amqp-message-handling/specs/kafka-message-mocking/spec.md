## ADDED Requirements

> Extends: mock-definition-loading/add-http-yaml-mock-server

### Requirement: Kafka Runtime Configuration
The system SHALL read Kafka runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Kafka disabled by default
- **WHEN** `HM_KAFKA_ENABLED` is absent
- **THEN** Kafka consumption and publishing SHALL remain disabled

#### Scenario: Shared Kafka defaults
- **WHEN** Kafka is enabled and no producer or consumer overrides are set
- **THEN** the system SHALL use `HM_KAFKA_CLIENT_ID` defaulting to `hmock`, `HM_KAFKA_SEED_BROKERS` defaulting to `kafka:9092`, shared SASL credentials, and shared TLS configuration for Kafka clients

### Requirement: Kafka Producer and Consumer Overrides
The system SHALL resolve Kafka producer and consumer connection settings independently, using side-specific environment variables when set and falling back to shared Kafka defaults otherwise.

#### Scenario: Producer override
- **WHEN** `HM_KAFKA_PRODUCER_SEED_BROKERS` is set
- **THEN** the Kafka producer SHALL use that broker list without changing the consumer broker list

#### Scenario: Consumer override
- **WHEN** `HM_KAFKA_CONSUMER_SEED_BROKERS` is set
- **THEN** the Kafka consumer SHALL use that broker list without changing the producer broker list

#### Scenario: Side-specific SASL enablement
- **WHEN** a Kafka producer or consumer resolves its SASL username and password after applying side-specific overrides and shared fallback values
- **THEN** that client SHALL enable SASL only when both resolved values are non-empty

#### Scenario: Side-specific TLS enablement
- **WHEN** `HM_KAFKA_TLS_PRODUCER_ENABLED` or `HM_KAFKA_TLS_CONSUMER_ENABLED` is set
- **THEN** the matching Kafka client SHALL use the side-specific TLS toggle and the other client SHALL continue using its own resolved TLS value

> Extends: http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering

### Requirement: Kafka Expectation Matching
The system SHALL consume messages from Kafka topics referenced by loaded `expect.kafka` mocks and evaluate matching against the consumed topic plus the mock behavior condition.

#### Scenario: Topic referenced by loaded mock
- **GIVEN** Kafka is enabled
- **WHEN** loaded mocks include an `expect.kafka` topic
- **THEN** the system SHALL consume messages published to that topic

#### Scenario: Kafka condition context
- **WHEN** a Kafka message is evaluated against an `expect.kafka` behavior condition
- **THEN** the condition SHALL have access to `.KafkaTopic` as the consumed topic and `.KafkaPayload` as the message payload

#### Scenario: Every Kafka match executes
- **WHEN** several Kafka behaviors match the same consumed message
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: Kafka Behavior Schema Validation (adapts mock-definition-loading/add-http-yaml-mock-server/behavior-schema-validation)
The system SHALL validate loaded Kafka mock behaviors before consuming messages.

#### Scenario: Missing Kafka topic is rejected
- **WHEN** a loaded behavior contains `expect.kafka` without a topic
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Missing Kafka payload source is rejected
- **WHEN** a loaded behavior contains `publish_kafka` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Kafka Publish Action
The system SHALL support `publish_kafka` actions that publish template-rendered payloads to Kafka topics.

#### Scenario: Inline Kafka payload
- **WHEN** a `publish_kafka` action defines `topic` and `payload`
- **THEN** the system SHALL render the payload as a template and publish it to the target Kafka topic

#### Scenario: File-backed Kafka payload
- **WHEN** a `publish_kafka` action defines `topic` and `payload_from_file`
- **THEN** the system SHALL load the file using the same file-backed payload rules as other `*_from_file` fields, render it as a template, and publish it to the target Kafka topic
