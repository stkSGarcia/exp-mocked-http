## ADDED Requirements

### Requirement: Broker Template Context
The system SHALL render Kafka and AMQP behavior conditions and broker publish action fields using the current broker message context, behavior values, named templates, and template functions.

#### Scenario: Kafka topic context is available
- **WHEN** a Kafka-triggered template uses `.KafkaTopic`
- **THEN** the system SHALL provide the consumed Kafka topic as a string

#### Scenario: Kafka payload context is available
- **WHEN** a Kafka-triggered template uses `.KafkaPayload`
- **THEN** the system SHALL provide the consumed Kafka message payload as a string

#### Scenario: AMQP exchange context is available
- **WHEN** an AMQP-triggered template uses `.AMQPExchange`
- **THEN** the system SHALL provide the exchange that received the message as a string

#### Scenario: AMQP routing key context is available
- **WHEN** an AMQP-triggered template uses `.AMQPRoutingKey`
- **THEN** the system SHALL provide the consumed AMQP routing key as a string

#### Scenario: AMQP queue context is available
- **WHEN** an AMQP-triggered template uses `.AMQPQueue`
- **THEN** the system SHALL provide the consumed AMQP queue as a string

#### Scenario: AMQP payload context is available
- **WHEN** an AMQP-triggered template uses `.AMQPPayload`
- **THEN** the system SHALL provide the consumed AMQP message payload as a string

#### Scenario: Behavior values are available to broker templates
- **WHEN** a Kafka-triggered or AMQP-triggered behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: Broker publish action fields render
- **WHEN** a behavior executes `publish_kafka` or `publish_amqp`
- **THEN** the system SHALL render the publish destination fields and payload source using the current trigger's template context
