## ADDED Requirements

> Extends: cors-response-policy/add-hot-reload-cors-binary-admin-cli
>
> Extends: http-yaml-mock-server/add-template-helpers-file-backed-bodies
>
> Extends: http-yaml-mock-server/add-admin-api-template-persistence

### Requirement: AMQP configuration
The system SHALL read `HM_AMQP_ENABLED` and `HM_AMQP_URL` from the environment, defaulting them to `false` and `amqp://guest:guest@rabbitmq:5672` respectively.

#### Scenario: AMQP is disabled by default
- **GIVEN** no AMQP environment variables are set
- **WHEN** configuration is loaded
- **THEN** AMQP consumption and publishing are disabled
- **AND** the AMQP URL uses the documented default

#### Scenario: Invalid AMQP enabled value
- **GIVEN** `HM_AMQP_ENABLED` contains a value that is not a supported boolean
- **WHEN** configuration is loaded
- **THEN** configuration loading fails and identifies `HM_AMQP_ENABLED`

### Requirement: AMQP expectation validation and queue defaulting
The system SHALL accept `expect.amqp.exchange`, `expect.amqp.routing_key`, and `expect.amqp.queue`. Exchange and routing key SHALL be non-empty strings, and an omitted or empty queue SHALL resolve to the routing key.

#### Scenario: Queue defaults to routing key
- **GIVEN** an AMQP expectation defines an exchange and routing key but no non-empty queue
- **WHEN** behaviors are compiled
- **THEN** the expectation's resolved queue equals its routing key

#### Scenario: Invalid AMQP expectation
- **GIVEN** an AMQP expectation omits its exchange or routing key
- **WHEN** behaviors are compiled
- **THEN** compilation fails with a validation error

### Requirement: AMQP topology setup
When AMQP is enabled, the system SHALL ensure the exchanges, resolved queues, and exchange-to-queue bindings required by loaded AMQP behaviors exist before consuming messages.

#### Scenario: Topology is created at startup
- **GIVEN** loaded AMQP behaviors reference exchanges, routing keys, and queues
- **WHEN** the AMQP worker starts
- **THEN** each required exchange and queue is declared
- **AND** each queue is bound to its exchange with the behavior's routing key

#### Scenario: Duplicate topology references
- **GIVEN** multiple behaviors require the same AMQP exchange, queue, and routing-key binding
- **WHEN** topology is prepared
- **THEN** the resource and binding are ensured without creating duplicate consumers for the queue

### Requirement: AMQP message context and matching
The system SHALL expose `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, and `.AMQPPayload` as strings while processing an AMQP message. It SHALL match behaviors by resolved exchange, routing key, and queue, evaluate `expect.condition` with the AMQP context and behavior values, and execute every matching behavior in loaded order.

#### Scenario: Multiple AMQP behaviors match
- **GIVEN** multiple loaded behaviors match the consumed message metadata and their conditions pass
- **WHEN** an AMQP message is consumed
- **THEN** every matching behavior executes
- **AND** execution follows loaded behavior order

#### Scenario: AMQP condition filters a behavior
- **GIVEN** a behavior matches the message metadata but its condition does not render exactly `true`
- **WHEN** the AMQP message is processed
- **THEN** that behavior's actions are not executed
- **AND** later matching behaviors are still evaluated

#### Scenario: AMQP templates receive message values
- **GIVEN** an action template references the AMQP context fields
- **WHEN** an AMQP message triggers the behavior
- **THEN** the action renders the consumed exchange, routing key, queue, and payload values

### Requirement: AMQP publishing action
The system SHALL support a `publish_amqp` action with required non-empty `exchange` and `routing_key` fields and either a non-empty `payload` or `payload_from_file`. Exchange, routing key, and selected payload content SHALL be template-rendered with the triggering context before publishing.

#### Scenario: Inline AMQP payload
- **GIVEN** a `publish_amqp` action has an exchange, routing key, and non-empty inline payload
- **WHEN** the action executes
- **THEN** the rendered payload is published to the rendered exchange with the rendered routing key

#### Scenario: File-backed AMQP payload
- **GIVEN** a `publish_amqp` action has an empty or absent inline payload and a valid `payload_from_file`
- **WHEN** definitions are loaded and the action later executes
- **THEN** the file is snapshotted from inside `HM_TEMPLATES_DIR`
- **AND** its contents are template-rendered and published

#### Scenario: Inline AMQP payload takes precedence
- **GIVEN** a `publish_amqp` action provides both a non-empty inline payload and `payload_from_file`
- **WHEN** the action executes
- **THEN** the inline payload is rendered and published

#### Scenario: Invalid AMQP publish action
- **GIVEN** a `publish_amqp` action omits its exchange, routing key, or both payload sources
- **WHEN** behaviors are compiled
- **THEN** compilation fails with a validation error

### Requirement: AMQP reconnect and lifecycle
The system SHALL create AMQP resources only when AMQP is enabled, SHALL automatically restore topology and consumption after a transient disconnect, and SHALL stop reconnecting and close AMQP resources during server shutdown.

#### Scenario: AMQP remains inactive
- **GIVEN** AMQP is disabled
- **WHEN** the mock server starts
- **THEN** no AMQP connection is created

#### Scenario: Transient AMQP disconnect
- **GIVEN** AMQP consumption is active
- **WHEN** the broker connection is lost transiently
- **THEN** the worker reconnects
- **AND** it restores required topology and queue consumption

#### Scenario: AMQP shutdown
- **GIVEN** an AMQP worker is running
- **WHEN** the mock server shuts down
- **THEN** reconnect attempts stop
- **AND** the AMQP connection is closed
