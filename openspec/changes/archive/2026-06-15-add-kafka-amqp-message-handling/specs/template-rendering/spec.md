## ADDED Requirements

### Requirement: Kafka Template Context
The system SHALL render Kafka behavior conditions and Kafka publish action fields using the Kafka message and behavior template context.

#### Scenario: Kafka topic context is available
- **WHEN** a Kafka-triggered template uses `.KafkaTopic`
- **THEN** the system SHALL provide the consumed Kafka topic

#### Scenario: Kafka payload context is available
- **WHEN** a Kafka-triggered template uses `.KafkaPayload`
- **THEN** the system SHALL provide the consumed Kafka message payload as a string

#### Scenario: Kafka values context is available
- **WHEN** a selected Kafka behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: Kafka template functions are available
- **WHEN** a Kafka behavior condition or Kafka publish action field uses an existing supported template function
- **THEN** the system SHALL evaluate that function using the same function semantics as HTTP-triggered templates

### Requirement: AMQP Template Context
The system SHALL render AMQP behavior conditions and AMQP publish action fields using the AMQP message and behavior template context.

#### Scenario: AMQP exchange context is available
- **WHEN** an AMQP-triggered template uses `.AMQPExchange`
- **THEN** the system SHALL provide the exchange that received the message

#### Scenario: AMQP routing key context is available
- **WHEN** an AMQP-triggered template uses `.AMQPRoutingKey`
- **THEN** the system SHALL provide the consumed AMQP routing key

#### Scenario: AMQP queue context is available
- **WHEN** an AMQP-triggered template uses `.AMQPQueue`
- **THEN** the system SHALL provide the consumed AMQP queue

#### Scenario: AMQP payload context is available
- **WHEN** an AMQP-triggered template uses `.AMQPPayload`
- **THEN** the system SHALL provide the consumed AMQP message payload as a string

#### Scenario: AMQP values context is available
- **WHEN** a selected AMQP behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: AMQP template functions are available
- **WHEN** an AMQP behavior condition or AMQP publish action field uses an existing supported template function
- **THEN** the system SHALL evaluate that function using the same function semantics as HTTP-triggered templates

### Requirement: Broker Publish Payload Rendering
The system SHALL render broker publish action payloads with the current trigger context.

#### Scenario: HTTP-triggered Kafka publish uses HTTP context
- **WHEN** an HTTP-selected behavior executes `publish_kafka`
- **THEN** the system SHALL render the publish fields with the same HTTP request context available to other HTTP behavior actions

#### Scenario: HTTP-triggered AMQP publish uses HTTP context
- **WHEN** an HTTP-selected behavior executes `publish_amqp`
- **THEN** the system SHALL render the publish fields with the same HTTP request context available to other HTTP behavior actions

#### Scenario: Kafka-triggered publish uses Kafka context
- **WHEN** a Kafka-selected behavior executes `publish_kafka` or `publish_amqp`
- **THEN** the system SHALL render the publish fields with the Kafka context for the consumed message

#### Scenario: AMQP-triggered publish uses AMQP context
- **WHEN** an AMQP-selected behavior executes `publish_kafka` or `publish_amqp`
- **THEN** the system SHALL render the publish fields with the AMQP context for the consumed message
