## ADDED Requirements

### Requirement: AMQP environment configuration
The server SHALL read AMQP configuration from environment variables at startup: `HM_AMQP_ENABLED` (default `false`) and `HM_AMQP_URL` (default `amqp://guest:guest@rabbitmq:5672`). AMQP consumer and producer SHALL start only when `HM_AMQP_ENABLED=true`.

#### Scenario: AMQP disabled by default
- **WHEN** `HM_AMQP_ENABLED` is not set
- **THEN** no AMQP connection is made and no queues are declared

#### Scenario: AMQP enabled with custom URL
- **WHEN** `HM_AMQP_ENABLED=true` and `HM_AMQP_URL=amqp://user:pass@broker:5672`
- **THEN** the server connects to `amqp://user:pass@broker:5672`

### Requirement: expect.amqp mock section
A behavior MAY include `expect.amqp` with fields `exchange` (string, exchange name), `routing_key` (string, binding routing key), and `queue` (string, optional — defaults to `routing_key` when omitted or empty). The server SHALL match an incoming AMQP message to a behavior when the consumed queue, exchange, and routing key match. For AMQP messages, the server SHALL execute every matching behavior in loaded order; all matching behaviors SHALL run, not just the first.

#### Scenario: AMQP behavior matched by queue
- **WHEN** a message is consumed from the queue matching `expect.amqp.queue`
- **THEN** the behavior's actions are executed

#### Scenario: queue defaults to routing_key
- **WHEN** `expect.amqp.queue` is absent and `expect.amqp.routing_key: orders.created`
- **THEN** the server uses `orders.created` as the queue name

#### Scenario: All matching behaviors executed
- **WHEN** two behaviors both declare identical `expect.amqp` fields
- **THEN** both behaviors' actions are executed in loaded order

### Requirement: AMQP auto-setup of broker resources
On startup the server SHALL declare and bind all exchanges, queues, and bindings required by loaded `expect.amqp` behaviors. Each exchange SHALL be declared as a topic exchange. Each queue SHALL be declared and bound to its exchange with its routing key. This SHALL happen before consuming begins.

#### Scenario: Exchange and queue declared on startup
- **WHEN** a mock declares `expect.amqp: {exchange: my-exchange, routing_key: my.key}`
- **THEN** the server declares exchange `my-exchange`, queue `my.key`, and binds them with routing key `my.key` before consuming

#### Scenario: Multiple mocks share an exchange
- **WHEN** two mocks reference the same `exchange` with different `routing_key` values
- **THEN** the exchange is declared once and both queues are bound with their respective routing keys

### Requirement: AMQP template context variables
When executing behaviors triggered by an AMQP message, the server SHALL populate the template context with `.AMQPExchange` (string), `.AMQPRoutingKey` (string), `.AMQPQueue` (string), and `.AMQPPayload` (string, raw message body). These variables SHALL be available in `expect.condition` and all action templates.

#### Scenario: AMQPPayload available in action
- **WHEN** a behavior matches an AMQP message and an action template uses `.AMQPPayload`
- **THEN** the template renders with the raw message payload

#### Scenario: AMQPRoutingKey available in condition
- **WHEN** a condition uses `.AMQPRoutingKey | eq "orders.created"`
- **THEN** it evaluates against the actual message routing key

### Requirement: AMQP automatic reconnection
The server SHALL recover AMQP consumption automatically after a transient disconnect without manual intervention or restart.

#### Scenario: Consumer reconnects after broker disconnect
- **WHEN** the broker connection drops and the broker becomes available again
- **THEN** the server reconnects and resumes consuming messages without restart

### Requirement: publish_amqp action
The `publish_amqp` action SHALL publish a message to an AMQP exchange. Required fields: `exchange` (string), `routing_key` (string), and either `payload` (template-rendered string) or `payload_from_file` (path relative to `HM_TEMPLATES_DIR`, snapshotted at load time, rendered at execution time). When both payload fields are absent, the server SHALL reject the behavior at load time. The payload SHALL be rendered with the same template context and functions as other action templates.

#### Scenario: AMQP message published
- **WHEN** a `publish_amqp` action specifies `exchange: my-exchange`, `routing_key: orders.created`, and `payload: '{"id":"1"}'`
- **THEN** a message is published to exchange `my-exchange` with routing key `orders.created` and that payload

#### Scenario: publish_amqp with payload_from_file
- **WHEN** `payload_from_file: amqp/order.json` points to a valid file
- **THEN** the file is snapshotted at load time and its rendered contents are published at execution time

#### Scenario: Missing exchange rejected at load time
- **WHEN** a `publish_amqp` action omits the `exchange` field
- **THEN** the server rejects the behavior at startup

#### Scenario: Missing payload and payload_from_file rejected
- **WHEN** a `publish_amqp` action omits both `payload` and `payload_from_file`
- **THEN** the server rejects the behavior at startup
