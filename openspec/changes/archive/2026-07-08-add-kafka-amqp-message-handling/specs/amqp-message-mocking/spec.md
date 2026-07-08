## ADDED Requirements

> Extends: mock-definition-loading/add-http-yaml-mock-server

### Requirement: AMQP Runtime Configuration
The system SHALL read AMQP runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: AMQP disabled by default
- **WHEN** `HM_AMQP_ENABLED` is absent
- **THEN** AMQP consumption and publishing SHALL remain disabled

#### Scenario: Default AMQP URL
- **WHEN** AMQP is enabled and `HM_AMQP_URL` is absent
- **THEN** the system SHALL connect using `amqp://guest:guest@rabbitmq:5672`

### Requirement: AMQP Resource Setup
The system SHALL ensure broker resources and bindings exist for each loaded `expect.amqp` mock before consuming messages.

#### Scenario: Explicit AMQP queue
- **GIVEN** AMQP is enabled
- **WHEN** loaded mocks include `expect.amqp` with an exchange, routing key, and queue
- **THEN** the system SHALL ensure the exchange, queue, and binding exist before consumption starts

#### Scenario: Queue defaulting
- **WHEN** an `expect.amqp` mock omits `queue` or sets it to an empty value
- **THEN** the system SHALL default the consumed queue name to the `routing_key`

> Extends: http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering

### Requirement: AMQP Expectation Matching
The system SHALL consume AMQP messages for loaded `expect.amqp` mocks and evaluate matching against exchange, routing key, queue, and behavior condition.

#### Scenario: AMQP condition context
- **WHEN** an AMQP message is evaluated against an `expect.amqp` behavior condition
- **THEN** the condition SHALL have access to `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, and `.AMQPPayload`

#### Scenario: Every AMQP match executes
- **WHEN** several AMQP behaviors match the same consumed message
- **THEN** the system SHALL execute every matching behavior in loaded order

### Requirement: AMQP Behavior Schema Validation (adapts mock-definition-loading/add-http-yaml-mock-server/behavior-schema-validation)
The system SHALL validate loaded AMQP mock behaviors before consuming messages.

#### Scenario: Missing AMQP routing information is rejected
- **WHEN** a loaded behavior contains `expect.amqp` without an exchange or routing key
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Missing AMQP payload source is rejected
- **WHEN** a loaded behavior contains `publish_amqp` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: AMQP Reconnect Recovery
The system SHALL recover AMQP consumption automatically after transient disconnects.

#### Scenario: Transient AMQP disconnect
- **WHEN** an active AMQP consumer experiences a transient broker disconnect
- **THEN** the system SHALL reconnect, restore required resources and bindings, and resume consumption without requiring a process restart

### Requirement: AMQP Publish Action
The system SHALL support `publish_amqp` actions that publish template-rendered payloads to exchanges with routing keys.

#### Scenario: Inline AMQP payload
- **WHEN** a `publish_amqp` action defines `exchange`, `routing_key`, and `payload`
- **THEN** the system SHALL render the payload as a template and publish it to the target exchange with the target routing key

#### Scenario: File-backed AMQP payload
- **WHEN** a `publish_amqp` action defines `exchange`, `routing_key`, and `payload_from_file`
- **THEN** the system SHALL load the file-backed payload, render it as a template, and publish it to the target exchange with the target routing key
