## ADDED Requirements

> Extends: mock-definition-loading/add-http-yaml-mock-server

### Requirement: AMQP Runtime Configuration (adapts mock-definition-loading/add-http-yaml-mock-server/server-configuration)
The system SHALL read AMQP runtime configuration from environment variables using documented defaults when variables are absent.

#### Scenario: AMQP disabled by default
- **WHEN** `HM_AMQP_ENABLED` is absent
- **THEN** AMQP consume and publish support SHALL be disabled

#### Scenario: AMQP URL default
- **WHEN** `HM_AMQP_ENABLED` is `true` and `HM_AMQP_URL` is absent
- **THEN** the system SHALL connect to `amqp://guest:guest@rabbitmq:5672`

### Requirement: AMQP Mock Schema (adapts mock-definition-loading/add-http-yaml-mock-server/behavior-schema-validation)
The system SHALL validate AMQP expectations and publish actions in loaded mock definitions before consuming or publishing AMQP messages.

#### Scenario: AMQP expectation requires routing details
- **WHEN** a loaded behavior contains `expect.amqp`
- **THEN** the system SHALL require `expect.amqp.exchange` to be a non-empty string
- **AND** the system SHALL require `expect.amqp.routing_key` to be a non-empty string

#### Scenario: AMQP queue defaults to routing key
- **WHEN** a loaded `expect.amqp` omits `queue` or sets it to an empty value
- **THEN** the system SHALL treat `queue` as the value of `routing_key`

#### Scenario: AMQP publish requires payload source
- **WHEN** a loaded behavior contains `publish_amqp`
- **THEN** the system SHALL require `publish_amqp.exchange` and `publish_amqp.routing_key` to be non-empty strings
- **AND** the system SHALL require either `publish_amqp.payload` or `publish_amqp.payload_from_file`

### Requirement: AMQP Resource Setup
The system SHALL ensure AMQP broker resources and bindings exist for each loaded AMQP mock before consuming messages.

#### Scenario: AMQP resources are declared at startup
- **WHEN** AMQP is enabled and loaded mocks include `expect.amqp`
- **THEN** the system SHALL ensure each configured exchange exists
- **AND** the system SHALL ensure each configured queue exists
- **AND** the system SHALL bind each queue to its exchange with the configured routing key

### Requirement: AMQP Expectation Matching
The system SHALL consume AMQP messages, evaluate matching conditions with an AMQP template context, and execute every matching behavior in loaded order.

#### Scenario: AMQP template context
- **WHEN** an AMQP message is evaluated
- **THEN** the template context SHALL expose `.AMQPExchange` as the receiving exchange
- **AND** the template context SHALL expose `.AMQPRoutingKey` as the routing key
- **AND** the template context SHALL expose `.AMQPQueue` as the consumed queue
- **AND** the template context SHALL expose `.AMQPPayload` as the message payload string

#### Scenario: Every matching AMQP behavior executes
- **WHEN** an AMQP message matches multiple loaded behaviors for its exchange, routing key, queue, and conditions
- **THEN** the system SHALL execute every matching behavior
- **AND** the system SHALL execute those behaviors in loaded order

### Requirement: AMQP Reconnect Recovery
The system SHALL recover AMQP consumption automatically after a transient disconnect.

#### Scenario: AMQP consumption resumes after disconnect
- **WHEN** an established AMQP consumer loses its connection transiently
- **THEN** the system SHALL reconnect
- **AND** the system SHALL restore the required exchange, queue, and binding setup
- **AND** the system SHALL resume consuming messages for loaded AMQP mocks

### Requirement: AMQP Publish Action
The system SHALL publish AMQP messages to the configured exchange and routing key using template-rendered payloads.

#### Scenario: Inline AMQP payload renders
- **WHEN** a matching behavior executes a `publish_amqp` action with `exchange`, `routing_key`, and `payload`
- **THEN** the system SHALL render `payload` with the active template context
- **AND** the system SHALL publish the rendered payload to `exchange` with `routing_key`

#### Scenario: File-backed AMQP payload renders
- **WHEN** a matching behavior executes a `publish_amqp` action with `payload_from_file`
- **THEN** the system SHALL load the file using the same resolution rules as other `*_from_file` fields
- **AND** the system SHALL render the loaded content with the active template context before publishing
