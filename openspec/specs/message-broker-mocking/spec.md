## Purpose

Define Kafka and AMQP message consumption, matching, broker-specific template contexts, publish actions, resource setup, and reconnect behavior.

## Requirements

### Requirement: Kafka Message Consumption
The system SHALL consume Kafka messages for topics referenced by loaded `expect.kafka.topic` behaviors when `HM_KAFKA_ENABLED` is true.

#### Scenario: Referenced Kafka topic is consumed
- **WHEN** Kafka support is enabled and a loaded behavior defines `expect.kafka.topic`
- **THEN** the system SHALL subscribe to that topic for message consumption

#### Scenario: Kafka topic match is eligible
- **WHEN** a consumed Kafka message topic equals a behavior's `expect.kafka.topic`
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Kafka topic mismatch is ignored
- **WHEN** a consumed Kafka message topic differs from a behavior's `expect.kafka.topic`
- **THEN** the system SHALL NOT execute that behavior for the message

#### Scenario: Missing Kafka condition passes
- **WHEN** a Kafka behavior matches the consumed topic and omits `expect.condition`
- **THEN** the behavior SHALL match the message

#### Scenario: Kafka condition must render true
- **WHEN** a Kafka behavior matches the consumed topic and its condition renders exactly `true`
- **THEN** the behavior SHALL match the message

#### Scenario: Kafka condition renders non-true
- **WHEN** a Kafka behavior matches the consumed topic and its condition renders any value other than exactly `true`
- **THEN** the behavior SHALL NOT match the message

#### Scenario: Kafka condition render failure is skipped
- **WHEN** a Kafka behavior matches the consumed topic but condition rendering fails
- **THEN** the behavior SHALL NOT match and later behaviors SHALL still be evaluated

#### Scenario: Every matching Kafka behavior executes
- **WHEN** several loaded Kafka behaviors match the same consumed message
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: Kafka Message Publishing
The system SHALL publish rendered Kafka messages for `publish_kafka` actions when Kafka support is enabled.

#### Scenario: Kafka publish sends rendered payload
- **WHEN** an executed behavior contains `publish_kafka` with `topic` and `payload`
- **THEN** the system SHALL render both fields and publish the rendered payload to the rendered topic

#### Scenario: Kafka publish file payload renders
- **WHEN** an executed behavior contains `publish_kafka` with `topic` and `payload_from_file`
- **THEN** the system SHALL render the snapshotted file content and publish it to the rendered topic

#### Scenario: Kafka inline payload takes precedence
- **WHEN** a `publish_kafka` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and publish the inline `payload`

#### Scenario: Kafka publish failure continues actions
- **WHEN** a `publish_kafka` action fails during publish
- **THEN** the system SHALL log the failure and continue executing later ordered actions

### Requirement: AMQP Resource Setup
The system SHALL ensure AMQP broker resources and bindings exist for loaded `expect.amqp` behaviors when `HM_AMQP_ENABLED` is true.

#### Scenario: AMQP queue defaults to routing key
- **WHEN** a loaded AMQP behavior defines `expect.amqp.routing_key` and omits `expect.amqp.queue` or sets it to an empty value
- **THEN** the system SHALL use the routing key as the effective queue name

#### Scenario: AMQP resources are created on startup
- **WHEN** AMQP support is enabled and loaded behaviors define AMQP expectations
- **THEN** the system SHALL ensure each exchange, effective queue, and queue binding exists before consuming messages

#### Scenario: AMQP resources are recreated after reconnect
- **WHEN** AMQP consumption reconnects after a transient disconnect
- **THEN** the system SHALL ensure the configured resources and bindings exist before resuming consumption

### Requirement: AMQP Message Consumption
The system SHALL consume AMQP messages for queues referenced by loaded `expect.amqp` behaviors when `HM_AMQP_ENABLED` is true.

#### Scenario: AMQP message match is eligible
- **WHEN** a consumed AMQP message exchange, routing key, and effective queue equal a behavior's AMQP expectation
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: AMQP message mismatch is ignored
- **WHEN** a consumed AMQP message differs from a behavior's exchange, routing key, or effective queue
- **THEN** the system SHALL NOT execute that behavior for the message

#### Scenario: Missing AMQP condition passes
- **WHEN** an AMQP behavior matches the consumed message and omits `expect.condition`
- **THEN** the behavior SHALL match the message

#### Scenario: AMQP condition must render true
- **WHEN** an AMQP behavior matches the consumed message and its condition renders exactly `true`
- **THEN** the behavior SHALL match the message

#### Scenario: AMQP condition renders non-true
- **WHEN** an AMQP behavior matches the consumed message and its condition renders any value other than exactly `true`
- **THEN** the behavior SHALL NOT match the message

#### Scenario: AMQP condition render failure is skipped
- **WHEN** an AMQP behavior matches the consumed message but condition rendering fails
- **THEN** the behavior SHALL NOT match and later behaviors SHALL still be evaluated

#### Scenario: Every matching AMQP behavior executes
- **WHEN** several loaded AMQP behaviors match the same consumed message
- **THEN** the system SHALL execute every matching behavior in loaded order

#### Scenario: AMQP consumption recovers after disconnect
- **WHEN** AMQP consumption loses a connection because of a transient disconnect
- **THEN** the system SHALL reconnect and resume consuming matching queues automatically

### Requirement: AMQP Message Publishing
The system SHALL publish rendered AMQP messages for `publish_amqp` actions when AMQP support is enabled.

#### Scenario: AMQP publish sends rendered payload
- **WHEN** an executed behavior contains `publish_amqp` with `exchange`, `routing_key`, and `payload`
- **THEN** the system SHALL render the fields and publish the rendered payload to the rendered exchange and routing key

#### Scenario: AMQP publish file payload renders
- **WHEN** an executed behavior contains `publish_amqp` with `exchange`, `routing_key`, and `payload_from_file`
- **THEN** the system SHALL render the snapshotted file content and publish it to the rendered exchange and routing key

#### Scenario: AMQP inline payload takes precedence
- **WHEN** a `publish_amqp` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and publish the inline `payload`

#### Scenario: AMQP publish failure continues actions
- **WHEN** a `publish_amqp` action fails during publish
- **THEN** the system SHALL log the failure and continue executing later ordered actions
