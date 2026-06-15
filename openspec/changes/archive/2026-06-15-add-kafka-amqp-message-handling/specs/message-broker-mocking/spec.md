## ADDED Requirements

### Requirement: Kafka Runtime Configuration
The system SHALL support opt-in Kafka consumption and publishing using environment-driven configuration.

#### Scenario: Kafka is disabled by default
- **WHEN** the server starts without `HM_KAFKA_ENABLED`
- **THEN** the system SHALL NOT start Kafka consumers or Kafka producers

#### Scenario: Kafka defaults are used when enabled
- **WHEN** the server starts with `HM_KAFKA_ENABLED` set to `true` and no other Kafka variables set
- **THEN** the system SHALL use client ID `hmock`, seed brokers `kafka:9092`, no SASL credentials, and TLS disabled for both Kafka producer and Kafka consumer settings

#### Scenario: Shared Kafka settings are overridden
- **WHEN** the server starts with `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, and `HM_KAFKA_TLS_ENABLED` set
- **THEN** the system SHALL use those values as the shared Kafka defaults for producer and consumer settings

#### Scenario: Producer-specific Kafka settings override shared settings
- **WHEN** producer-specific Kafka broker, SASL, or TLS environment variables are set
- **THEN** the system SHALL use each producer-specific value for the Kafka producer and fall back to the corresponding shared Kafka default only for unset producer-specific values

#### Scenario: Consumer-specific Kafka settings override shared settings
- **WHEN** consumer-specific Kafka broker, SASL, or TLS environment variables are set
- **THEN** the system SHALL use each consumer-specific value for the Kafka consumer and fall back to the corresponding shared Kafka default only for unset consumer-specific values

#### Scenario: Kafka SASL enablement is resolved per endpoint
- **WHEN** the producer or consumer Kafka username and password are resolved after applying endpoint overrides
- **THEN** the system SHALL enable SASL separately for that endpoint only when both the resolved username and password are non-empty

### Requirement: Kafka Message Consumption
The system SHALL consume Kafka messages from topics referenced by loaded `expect.kafka` behaviors when Kafka is enabled.

#### Scenario: Referenced Kafka topics are consumed
- **WHEN** Kafka is enabled and loaded behaviors include `expect.kafka.topic` values
- **THEN** the system SHALL consume messages from those referenced topics

#### Scenario: Kafka topic matches behavior
- **WHEN** a consumed Kafka message topic equals a behavior's `expect.kafka.topic`
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Kafka topic mismatch is ignored
- **WHEN** a consumed Kafka message topic differs from a behavior's `expect.kafka.topic`
- **THEN** the behavior SHALL NOT match that Kafka message

#### Scenario: Kafka condition passes
- **WHEN** a Kafka behavior matches by topic and omits `expect.condition` or renders it exactly as `true` using the Kafka template context
- **THEN** the system SHALL execute that behavior's actions

#### Scenario: Kafka condition does not pass
- **WHEN** a Kafka behavior matches by topic and its `expect.condition` renders any value other than exactly `true` or rendering fails
- **THEN** the system SHALL NOT execute that behavior for that message

#### Scenario: Every matching Kafka behavior executes
- **WHEN** several loaded Kafka behaviors match the same consumed message
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: Kafka Publish Action
The system SHALL publish Kafka messages from `publish_kafka` actions.

#### Scenario: Kafka publish uses rendered inline payload
- **WHEN** an executed behavior contains `publish_kafka` with `topic` and non-empty `payload`
- **THEN** the system SHALL render the topic and payload with the current template context and publish the rendered payload to the rendered topic

#### Scenario: Kafka publish uses rendered file payload
- **WHEN** an executed behavior contains `publish_kafka` with `topic`, `payload_from_file`, and no non-empty `payload`
- **THEN** the system SHALL render the loaded file content with the current template context and publish it to the rendered topic

#### Scenario: Kafka inline payload takes precedence
- **WHEN** a `publish_kafka` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and publish the inline `payload`

### Requirement: AMQP Runtime Configuration
The system SHALL support opt-in AMQP consumption and publishing using environment-driven configuration.

#### Scenario: AMQP is disabled by default
- **WHEN** the server starts without `HM_AMQP_ENABLED`
- **THEN** the system SHALL NOT start AMQP consumers or AMQP publishers

#### Scenario: AMQP defaults are used when enabled
- **WHEN** the server starts with `HM_AMQP_ENABLED` set to `true` and no AMQP URL set
- **THEN** the system SHALL connect to `amqp://guest:guest@rabbitmq:5672`

#### Scenario: AMQP URL is overridden
- **WHEN** the server starts with `HM_AMQP_URL` set
- **THEN** the system SHALL use that URL for AMQP consumption, setup, and publishing

### Requirement: AMQP Resource Setup And Consumption
The system SHALL prepare AMQP broker resources for loaded AMQP mocks and consume matching messages when AMQP is enabled.

#### Scenario: AMQP resources are ensured on startup
- **WHEN** AMQP is enabled and loaded behaviors include `expect.amqp`
- **THEN** the system SHALL ensure the required exchanges, queues, and bindings exist before consuming messages

#### Scenario: AMQP queue defaults to routing key
- **WHEN** a loaded AMQP behavior omits `expect.amqp.queue` or sets it to an empty value
- **THEN** the system SHALL treat the queue name as the behavior's `expect.amqp.routing_key`

#### Scenario: AMQP message matches behavior
- **WHEN** a consumed AMQP message exchange, routing key, and queue match a behavior's resolved `expect.amqp` values
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: AMQP condition passes
- **WHEN** an AMQP behavior matches by exchange, routing key, and queue and omits `expect.condition` or renders it exactly as `true` using the AMQP template context
- **THEN** the system SHALL execute that behavior's actions

#### Scenario: Every matching AMQP behavior executes
- **WHEN** several loaded AMQP behaviors match the same consumed message
- **THEN** the system SHALL execute every matching behavior in loaded order

#### Scenario: AMQP consumption reconnects after transient disconnect
- **WHEN** AMQP consumption disconnects after startup due to a transient broker or network failure
- **THEN** the system SHALL recover consumption automatically without requiring a process restart

### Requirement: AMQP Publish Action
The system SHALL publish AMQP messages from `publish_amqp` actions.

#### Scenario: AMQP publish uses rendered inline payload
- **WHEN** an executed behavior contains `publish_amqp` with `exchange`, `routing_key`, and non-empty `payload`
- **THEN** the system SHALL render the exchange, routing key, and payload with the current template context and publish the rendered payload to the rendered exchange and routing key

#### Scenario: AMQP publish uses rendered file payload
- **WHEN** an executed behavior contains `publish_amqp` with `exchange`, `routing_key`, `payload_from_file`, and no non-empty `payload`
- **THEN** the system SHALL render the loaded file content with the current template context and publish it to the rendered exchange and routing key

#### Scenario: AMQP inline payload takes precedence
- **WHEN** a `publish_amqp` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and publish the inline `payload`
