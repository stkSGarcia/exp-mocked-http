## ADDED Requirements

> Extends: mock-definition-loading

### Requirement: AMQP Runtime Configuration
The system SHALL enable AMQP consume and publish only when `HM_AMQP_ENABLED` is `true`.

#### Scenario: AMQP disabled by default
- **GIVEN** the server starts without `HM_AMQP_ENABLED`
- **WHEN** mock definitions include AMQP expectations or publish actions
- **THEN** the system SHALL NOT create AMQP connections

#### Scenario: Default AMQP URL is used
- **GIVEN** `HM_AMQP_ENABLED` is `true`
- **WHEN** `HM_AMQP_URL` is not set
- **THEN** the system SHALL connect using `amqp://guest:guest@rabbitmq:5672`

#### Scenario: AMQP URL override is used
- **GIVEN** `HM_AMQP_ENABLED` is `true`
- **WHEN** `HM_AMQP_URL` is set
- **THEN** the system SHALL connect using that URL

### Requirement: AMQP Resource Setup
The system SHALL ensure broker resources and bindings exist for each loaded `expect.amqp` mock before consuming messages.

#### Scenario: Queue defaults to routing key
- **GIVEN** a loaded behavior defines `expect.amqp.routing_key` and omits `expect.amqp.queue`
- **WHEN** AMQP resources are prepared
- **THEN** the system SHALL use the routing key as the queue name

#### Scenario: Explicit queue is used
- **GIVEN** a loaded behavior defines `expect.amqp.queue`
- **WHEN** AMQP resources are prepared
- **THEN** the system SHALL use that queue name

#### Scenario: Binding is ensured before consumption
- **GIVEN** AMQP is enabled and a loaded behavior defines `expect.amqp.exchange`, `expect.amqp.routing_key`, and an effective queue
- **WHEN** the server starts
- **THEN** the system SHALL ensure the exchange, queue, and binding exist before consuming from the queue

### Requirement: AMQP Message Matching
The system SHALL match consumed AMQP messages by exchange, routing key, and effective queue, then evaluate `expect.condition` with AMQP message context.

#### Scenario: Matching AMQP message is eligible
- **GIVEN** a loaded behavior defines `expect.amqp.exchange`, `expect.amqp.routing_key`, and an effective queue
- **WHEN** a message is consumed from the same exchange, routing key, and queue
- **THEN** the behavior SHALL be eligible for condition evaluation

#### Scenario: AMQP routing key mismatch is ignored
- **GIVEN** a loaded behavior defines `expect.amqp.routing_key`
- **WHEN** a message is consumed with a different routing key
- **THEN** the behavior SHALL NOT match that message

#### Scenario: AMQP condition can use message context
- **GIVEN** a loaded behavior defines `expect.amqp` and `expect.condition`
- **WHEN** an AMQP message is consumed for that expectation
- **THEN** the system SHALL render the condition with `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, and `.AMQPPayload`

#### Scenario: All AMQP matches execute in load order
- **GIVEN** multiple loaded behaviors match the same AMQP message
- **WHEN** their conditions pass
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: AMQP Template Context
The system SHALL expose AMQP message fields to condition and action template rendering.

#### Scenario: Exchange context is available
- **GIVEN** an AMQP-triggered behavior is executing
- **WHEN** a template uses `.AMQPExchange`
- **THEN** the system SHALL render the exchange that received the message

#### Scenario: Routing key context is available
- **GIVEN** an AMQP-triggered behavior is executing
- **WHEN** a template uses `.AMQPRoutingKey`
- **THEN** the system SHALL render the consumed routing key

#### Scenario: Queue context is available
- **GIVEN** an AMQP-triggered behavior is executing
- **WHEN** a template uses `.AMQPQueue`
- **THEN** the system SHALL render the consumed queue

#### Scenario: Payload context is available
- **GIVEN** an AMQP-triggered behavior is executing
- **WHEN** a template uses `.AMQPPayload`
- **THEN** the system SHALL render the consumed AMQP message payload

### Requirement: AMQP Publish Action
The system SHALL publish `publish_amqp` actions to the configured AMQP connection.

#### Scenario: Inline AMQP payload is published
- **GIVEN** a selected behavior contains `publish_amqp.exchange`, `publish_amqp.routing_key`, and `publish_amqp.payload`
- **WHEN** the action executes
- **THEN** the system SHALL render the payload and publish it to the exchange with the routing key

#### Scenario: AMQP file payload is published
- **GIVEN** a selected behavior contains `publish_amqp.exchange`, `publish_amqp.routing_key`, and `publish_amqp.payload_from_file`
- **WHEN** the action executes
- **THEN** the system SHALL render the loaded file content and publish it to the exchange with the routing key

#### Scenario: Inline AMQP payload takes precedence
- **GIVEN** a selected behavior contains non-empty `publish_amqp.payload` and `publish_amqp.payload_from_file`
- **WHEN** the action executes
- **THEN** the system SHALL render and publish the inline payload

### Requirement: AMQP Consumption Recovery
The system SHALL recover AMQP consumption after transient disconnects.

#### Scenario: Consumption resumes after reconnect
- **GIVEN** AMQP consumption is active
- **WHEN** the AMQP connection is transiently disconnected and then reconnects
- **THEN** the system SHALL restore consumption for loaded AMQP expectations
