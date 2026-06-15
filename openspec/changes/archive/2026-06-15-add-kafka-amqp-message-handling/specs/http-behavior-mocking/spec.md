## ADDED Requirements

### Requirement: HTTP Broker Publish Actions
The system SHALL execute broker publish actions from HTTP-selected behaviors using the existing ordered action execution model.

#### Scenario: HTTP behavior publishes Kafka message
- **WHEN** a selected HTTP behavior executes `publish_kafka`
- **THEN** the system SHALL render and publish the Kafka message without replacing the inbound HTTP response

#### Scenario: HTTP behavior publishes AMQP message
- **WHEN** a selected HTTP behavior executes `publish_amqp`
- **THEN** the system SHALL render and publish the AMQP message without replacing the inbound HTTP response

#### Scenario: Broker publish actions respect order
- **WHEN** a selected HTTP behavior mixes `publish_kafka`, `publish_amqp`, `redis`, `send_http`, `sleep`, and `reply_http` actions with different effective `order` values
- **THEN** the system SHALL execute lower order values before higher order values

#### Scenario: Broker publish actions preserve equal order
- **WHEN** a selected HTTP behavior mixes broker publish actions with other actions that have the same effective `order`
- **THEN** the system SHALL preserve those actions' original relative order

#### Scenario: Kafka publish failure preserves inbound response
- **WHEN** a selected HTTP behavior executes `publish_kafka` and the publish fails
- **THEN** the system SHALL continue mock action execution and preserve the inbound response produced by the behavior

#### Scenario: AMQP publish failure preserves inbound response
- **WHEN** a selected HTTP behavior executes `publish_amqp` and the publish fails
- **THEN** the system SHALL continue mock action execution and preserve the inbound response produced by the behavior
