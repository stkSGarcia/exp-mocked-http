## ADDED Requirements

> Extends: mock-definition-loading

### Requirement: Kafka Runtime Configuration
The system SHALL enable Kafka consume and publish only when `HM_KAFKA_ENABLED` is `true`.

#### Scenario: Kafka disabled by default
- **GIVEN** the server starts without `HM_KAFKA_ENABLED`
- **WHEN** mock definitions include Kafka expectations or publish actions
- **THEN** the system SHALL NOT create Kafka producer or consumer connections

#### Scenario: Shared Kafka defaults are used
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** no Kafka override variables are set
- **THEN** the system SHALL use client ID `hmock`, seed brokers `kafka:9092`, TLS disabled, and no SASL credentials

#### Scenario: Kafka client ID override is used
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** `HM_KAFKA_CLIENT_ID` is set
- **THEN** the system SHALL use that value as the Kafka client ID

### Requirement: Kafka Producer And Consumer Overrides
The system SHALL resolve Kafka producer and consumer settings from side-specific environment variables before falling back to shared Kafka defaults.

#### Scenario: Producer broker override is used
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** `HM_KAFKA_PRODUCER_SEED_BROKERS` is set
- **THEN** the Kafka producer SHALL connect with that broker list instead of `HM_KAFKA_SEED_BROKERS`

#### Scenario: Consumer broker override falls back
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** `HM_KAFKA_CONSUMER_SEED_BROKERS` is not set
- **THEN** the Kafka consumer SHALL connect with `HM_KAFKA_SEED_BROKERS`

#### Scenario: Producer SASL is enabled after override resolution
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** the resolved producer SASL username and password are both non-empty
- **THEN** the Kafka producer SHALL enable SASL with those credentials

#### Scenario: Consumer SASL requires both credentials
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** the resolved consumer SASL username or password is empty
- **THEN** the Kafka consumer SHALL NOT enable SASL

#### Scenario: Producer TLS override falls back
- **GIVEN** `HM_KAFKA_ENABLED` is `true`
- **WHEN** `HM_KAFKA_TLS_PRODUCER_ENABLED` is not set
- **THEN** the Kafka producer SHALL use `HM_KAFKA_TLS_ENABLED`

### Requirement: Kafka Expectation Consumption
The system SHALL consume messages published to topics referenced by loaded `expect.kafka.topic` values.

#### Scenario: Referenced topic is consumed
- **GIVEN** Kafka is enabled and a loaded behavior defines `expect.kafka.topic`
- **WHEN** the server starts
- **THEN** the system SHALL subscribe to consume messages from that topic

#### Scenario: Unreferenced topic is not consumed
- **GIVEN** Kafka is enabled and no loaded behavior references a Kafka topic
- **WHEN** the server starts
- **THEN** the system SHALL NOT start Kafka topic consumption for mock matching

### Requirement: Kafka Message Matching
The system SHALL match consumed Kafka messages by topic and evaluate `expect.condition` with Kafka message context.

#### Scenario: Matching topic is eligible
- **GIVEN** a loaded behavior defines `expect.kafka.topic`
- **WHEN** a Kafka message is consumed from that same topic
- **THEN** the behavior SHALL be eligible for condition evaluation

#### Scenario: Topic mismatch is ignored
- **GIVEN** a loaded behavior defines `expect.kafka.topic`
- **WHEN** a Kafka message is consumed from a different topic
- **THEN** the behavior SHALL NOT match that message

#### Scenario: Kafka condition can use message context
- **GIVEN** a loaded behavior defines `expect.kafka.topic` and `expect.condition`
- **WHEN** a Kafka message is consumed from that topic
- **THEN** the system SHALL render the condition with `.KafkaTopic` and `.KafkaPayload`

#### Scenario: All matching behaviors execute in load order
- **GIVEN** multiple loaded behaviors match the same Kafka message
- **WHEN** their conditions pass
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: Kafka Template Context
The system SHALL expose Kafka message fields to condition and action template rendering.

#### Scenario: Topic context is available
- **GIVEN** a Kafka-triggered behavior is executing
- **WHEN** a template uses `.KafkaTopic`
- **THEN** the system SHALL render the consumed Kafka topic

#### Scenario: Payload context is available
- **GIVEN** a Kafka-triggered behavior is executing
- **WHEN** a template uses `.KafkaPayload`
- **THEN** the system SHALL render the consumed Kafka message payload

### Requirement: Kafka Publish Action
The system SHALL publish `publish_kafka` actions to the configured Kafka producer.

#### Scenario: Inline Kafka payload is published
- **GIVEN** a selected behavior contains `publish_kafka.topic` and `publish_kafka.payload`
- **WHEN** the action executes
- **THEN** the system SHALL render the payload and publish it to the target topic

#### Scenario: Kafka file payload is published
- **GIVEN** a selected behavior contains `publish_kafka.topic` and `publish_kafka.payload_from_file`
- **WHEN** the action executes
- **THEN** the system SHALL render the loaded file content and publish it to the target topic

#### Scenario: Inline Kafka payload takes precedence
- **GIVEN** a selected behavior contains non-empty `publish_kafka.payload` and `publish_kafka.payload_from_file`
- **WHEN** the action executes
- **THEN** the system SHALL render and publish the inline payload
