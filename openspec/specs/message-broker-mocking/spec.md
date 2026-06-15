## Purpose

Define Kafka and AMQP consumption, matching, template context, resource setup, and broker publish action behavior for `hmock.py`.

## Requirements

### Requirement: Kafka Runtime Configuration
The system SHALL start Kafka consumption and publishing only when Kafka support is enabled and SHALL resolve shared defaults and producer/consumer overrides from environment configuration.

#### Scenario: Kafka disabled by default
- **WHEN** the server starts without `HM_KAFKA_ENABLED`
- **THEN** the system SHALL NOT start Kafka consumers or create Kafka producer clients

#### Scenario: Kafka shared defaults are used
- **WHEN** `HM_KAFKA_ENABLED=true` and no Kafka override variables are set
- **THEN** the system SHALL use client ID `hmock`, seed brokers `kafka:9092`, no SASL credentials, and TLS disabled for both producer and consumer clients

#### Scenario: Kafka shared configuration is applied
- **WHEN** `HM_KAFKA_ENABLED=true` with `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, and `HM_KAFKA_TLS_ENABLED` set
- **THEN** the system SHALL use those values as the shared Kafka client defaults

#### Scenario: Kafka producer overrides shared defaults
- **WHEN** `HM_KAFKA_ENABLED=true` and producer-specific broker, SASL, or TLS variables are set
- **THEN** the Kafka producer configuration SHALL use the producer-specific values for those settings and the shared defaults for unset settings

#### Scenario: Kafka consumer overrides shared defaults
- **WHEN** `HM_KAFKA_ENABLED=true` and consumer-specific broker, SASL, or TLS variables are set
- **THEN** the Kafka consumer configuration SHALL use the consumer-specific values for those settings and the shared defaults for unset settings

#### Scenario: Kafka SASL enablement requires complete credentials
- **WHEN** Kafka producer or consumer configuration is resolved
- **THEN** each resolved client configuration SHALL enable SASL only when its resolved username and password are both non-empty

### Requirement: Kafka Message Consumption
The system SHALL consume Kafka messages from every topic referenced by loaded `expect.kafka` behaviors when Kafka support is enabled.

#### Scenario: Referenced Kafka topics are consumed
- **WHEN** Kafka support is enabled and loaded behaviors reference topics through `expect.kafka.topic`
- **THEN** the system SHALL subscribe consumers to every referenced Kafka topic

#### Scenario: Kafka topic match is required
- **WHEN** a Kafka message is consumed from a topic that does not equal a behavior's `expect.kafka.topic`
- **THEN** that behavior SHALL NOT match the Kafka message

#### Scenario: Kafka condition uses Kafka context
- **WHEN** a Kafka message topic matches `expect.kafka.topic` and the behavior defines `expect.condition`
- **THEN** the system SHALL evaluate the condition with `.KafkaTopic` set to the consumed topic and `.KafkaPayload` set to the message payload

#### Scenario: Kafka condition render failure skips behavior
- **WHEN** a Kafka behavior topic matches but condition rendering fails
- **THEN** that behavior SHALL NOT execute and later loaded behaviors SHALL still be evaluated for the same Kafka message

#### Scenario: Every matching Kafka behavior executes
- **WHEN** several loaded behaviors match the same consumed Kafka message
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: Kafka Publish Action
The system SHALL publish Kafka messages from `publish_kafka` actions.

#### Scenario: Kafka publish sends rendered payload
- **WHEN** a matching behavior executes `publish_kafka` with `topic` and `payload`
- **THEN** the system SHALL render the topic and payload with the active template context and publish the rendered payload to the rendered topic

#### Scenario: Kafka publish file payload renders
- **WHEN** a matching behavior executes `publish_kafka` with `payload_from_file` and no non-empty `payload`
- **THEN** the system SHALL render the loaded file content with the active template context and publish the rendered payload

#### Scenario: Kafka inline payload takes precedence
- **WHEN** a `publish_kafka` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and publish the inline `payload`

#### Scenario: Kafka publish failure does not stop action execution
- **WHEN** a `publish_kafka` action fails to publish
- **THEN** the system SHALL log the failure and continue executing later actions for the behavior

### Requirement: AMQP Runtime Configuration
The system SHALL start AMQP consumption and publishing only when AMQP support is enabled and SHALL resolve AMQP connection configuration from environment configuration.

#### Scenario: AMQP disabled by default
- **WHEN** the server starts without `HM_AMQP_ENABLED`
- **THEN** the system SHALL NOT start AMQP consumers or create AMQP publisher clients

#### Scenario: AMQP default URL is used
- **WHEN** `HM_AMQP_ENABLED=true` and `HM_AMQP_URL` is not set
- **THEN** the system SHALL use `amqp://guest:guest@rabbitmq:5672` as the AMQP connection URL

#### Scenario: AMQP URL override is used
- **WHEN** `HM_AMQP_ENABLED=true` and `HM_AMQP_URL` is set
- **THEN** the system SHALL use that URL for AMQP consumption and publishing

### Requirement: AMQP Resource Setup And Consumption
The system SHALL ensure AMQP resources exist for loaded `expect.amqp` behaviors and consume matching messages when AMQP support is enabled.

#### Scenario: AMQP queue defaults to routing key
- **WHEN** a loaded behavior defines `expect.amqp.routing_key` and omits `expect.amqp.queue` or sets it to an empty value
- **THEN** the system SHALL use the routing key as the effective queue name

#### Scenario: AMQP resources are declared on startup
- **WHEN** AMQP support is enabled and loaded behaviors define `expect.amqp`
- **THEN** the system SHALL ensure each referenced exchange, effective queue, and exchange-to-queue binding exists before consuming messages

#### Scenario: AMQP exchange and routing key match are required
- **WHEN** an AMQP message is consumed for a behavior's effective queue
- **THEN** the behavior SHALL match only when the consumed exchange equals `expect.amqp.exchange` and the consumed routing key equals `expect.amqp.routing_key`

#### Scenario: AMQP condition uses AMQP context
- **WHEN** an AMQP message matches exchange and routing key and the behavior defines `expect.condition`
- **THEN** the system SHALL evaluate the condition with `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, and `.AMQPPayload` populated from the consumed message

#### Scenario: Every matching AMQP behavior executes
- **WHEN** several loaded behaviors match the same consumed AMQP message
- **THEN** the system SHALL execute every matching behavior in loaded order

#### Scenario: AMQP consumption recovers after disconnect
- **WHEN** an AMQP consumer connection is interrupted transiently
- **THEN** the system SHALL reconnect and resume consumption for the loaded AMQP bindings

### Requirement: AMQP Publish Action
The system SHALL publish AMQP messages from `publish_amqp` actions.

#### Scenario: AMQP publish sends rendered payload
- **WHEN** a matching behavior executes `publish_amqp` with `exchange`, `routing_key`, and `payload`
- **THEN** the system SHALL render the exchange, routing key, and payload with the active template context and publish the rendered payload

#### Scenario: AMQP publish file payload renders
- **WHEN** a matching behavior executes `publish_amqp` with `payload_from_file` and no non-empty `payload`
- **THEN** the system SHALL render the loaded file content with the active template context and publish the rendered payload

#### Scenario: AMQP inline payload takes precedence
- **WHEN** a `publish_amqp` action defines both a non-empty `payload` and `payload_from_file`
- **THEN** the system SHALL render and publish the inline `payload`

#### Scenario: AMQP publish failure does not stop action execution
- **WHEN** a `publish_amqp` action fails to publish
- **THEN** the system SHALL log the failure and continue executing later actions for the behavior
