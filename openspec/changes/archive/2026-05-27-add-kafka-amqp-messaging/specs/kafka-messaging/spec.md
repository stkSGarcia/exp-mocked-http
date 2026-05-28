## ADDED Requirements

### Requirement: Kafka environment configuration
The server SHALL read Kafka configuration from environment variables at startup: `HM_KAFKA_ENABLED` (default `false`), `HM_KAFKA_CLIENT_ID` (default `hmock`), `HM_KAFKA_SEED_BROKERS` (default `kafka:9092`, comma-separated), `HM_KAFKA_SASL_USERNAME` (shared default, empty), `HM_KAFKA_SASL_PASSWORD` (shared default, empty), `HM_KAFKA_TLS_ENABLED` (shared default, `false`). Kafka consumer and producer SHALL start only when `HM_KAFKA_ENABLED=true`.

#### Scenario: Kafka disabled by default
- **WHEN** `HM_KAFKA_ENABLED` is not set
- **THEN** no Kafka consumer or producer is started

#### Scenario: Kafka enabled
- **WHEN** `HM_KAFKA_ENABLED=true`
- **THEN** the server initializes a Kafka consumer and producer on startup

### Requirement: Kafka per-producer and per-consumer connection overrides
The server SHALL support per-role override environment variables: `HM_KAFKA_PRODUCER_SEED_BROKERS`, `HM_KAFKA_CONSUMER_SEED_BROKERS`, `HM_KAFKA_SASL_PRODUCER_USERNAME`, `HM_KAFKA_SASL_PRODUCER_PASSWORD`, `HM_KAFKA_SASL_CONSUMER_USERNAME`, `HM_KAFKA_SASL_CONSUMER_PASSWORD`, `HM_KAFKA_TLS_PRODUCER_ENABLED`, `HM_KAFKA_TLS_CONSUMER_ENABLED`. Each override SHALL be applied to its respective role; when an override is absent, the shared default value SHALL be used. SASL SHALL be enabled for a role only when its resolved username and password are both non-empty.

#### Scenario: Producer uses its own broker list
- **WHEN** `HM_KAFKA_SEED_BROKERS=kafka:9092` and `HM_KAFKA_PRODUCER_SEED_BROKERS=prod-kafka:9092`
- **THEN** the producer connects to `prod-kafka:9092` and the consumer connects to `kafka:9092`

#### Scenario: Producer SASL falls back to shared default
- **WHEN** `HM_KAFKA_SASL_PRODUCER_USERNAME` is not set and `HM_KAFKA_SASL_USERNAME=user` and `HM_KAFKA_SASL_PASSWORD=pass`
- **THEN** the producer uses SASL with username `user` and password `pass`

#### Scenario: SASL disabled when password is empty
- **WHEN** resolved username is non-empty but resolved password is empty for the consumer role
- **THEN** the consumer connects without SASL

#### Scenario: Consumer and producer TLS independently controlled
- **WHEN** `HM_KAFKA_TLS_PRODUCER_ENABLED=true` and `HM_KAFKA_TLS_CONSUMER_ENABLED=false`
- **THEN** the producer uses TLS and the consumer does not

### Requirement: expect.kafka mock section
A behavior MAY include `expect.kafka.topic` to match incoming Kafka messages. The server SHALL match a message to a behavior when the consumed topic equals `expect.kafka.topic` (exact string match) and any `expect.condition` renders to exactly `true`. For Kafka messages, the server SHALL execute every matching behavior in loaded order; all matching behaviors SHALL run, not just the first.

#### Scenario: Topic match dispatches behavior
- **WHEN** a message arrives on topic `events` and a behavior declares `expect.kafka.topic: events`
- **THEN** the behavior's actions are executed

#### Scenario: All matching behaviors executed
- **WHEN** two behaviors both declare `expect.kafka.topic: events` and both pass their conditions
- **THEN** both behaviors' actions are executed in loaded order

#### Scenario: No match on different topic
- **WHEN** a message arrives on topic `orders` and only a behavior with `expect.kafka.topic: events` is loaded
- **THEN** no behavior is dispatched

#### Scenario: Condition filters within topic match
- **WHEN** two behaviors share `expect.kafka.topic: events` but the second has a condition that renders to `false`
- **THEN** only the first behavior's actions are executed

### Requirement: Kafka template context variables
When executing behaviors triggered by a Kafka message, the server SHALL populate the template context with `.KafkaTopic` (string, consumed topic) and `.KafkaPayload` (string, raw message payload). These variables SHALL be available in `expect.condition` and all action templates.

#### Scenario: KafkaPayload available in action
- **WHEN** a behavior matches a Kafka message with payload `{"id":"1"}` and an action template uses `.KafkaPayload`
- **THEN** the template renders with the payload value `{"id":"1"}`

#### Scenario: KafkaTopic available in condition
- **WHEN** a condition template uses `.KafkaTopic | eq "events"`
- **THEN** it evaluates against the actual consumed topic

### Requirement: Kafka topic subscription from loaded mocks
The server SHALL subscribe to Kafka topics only for topics referenced by `expect.kafka.topic` in the currently loaded behaviors. When mocks are reloaded, the server SHALL update its active subscriptions to match the new set of referenced topics.

#### Scenario: Subscription based on loaded mocks
- **WHEN** mocks reference topics `events` and `commands`
- **THEN** the server consumes from both `events` and `commands`

#### Scenario: Subscription updated on reload
- **WHEN** a mock referencing topic `events` is removed and mocks are reloaded
- **THEN** the server stops consuming from `events` if no remaining behavior references it

### Requirement: publish_kafka action
The `publish_kafka` action SHALL publish a message to a Kafka topic. Required fields: `topic` (string, target topic) and either `payload` (template-rendered message string) or `payload_from_file` (path relative to `HM_TEMPLATES_DIR`, file read and snapshotted at load time, rendered at execution time). When both are absent, validation SHALL reject the behavior at load time. The payload SHALL be rendered with the same template context and functions as other action templates.

#### Scenario: Kafka message published with payload
- **WHEN** a `publish_kafka` action specifies `topic: events` and `payload: '{"id":"{{.KafkaPayload}}"}'`
- **THEN** a message is published to topic `events` with the rendered payload

#### Scenario: publish_kafka with payload_from_file
- **WHEN** `payload_from_file: kafka/event.json` points to a valid file
- **THEN** the file is read at load time and the rendered contents are published at execution time

#### Scenario: Missing topic rejected at load time
- **WHEN** a `publish_kafka` action omits the `topic` field
- **THEN** the server rejects the behavior at startup

#### Scenario: Missing payload and payload_from_file rejected
- **WHEN** a `publish_kafka` action omits both `payload` and `payload_from_file`
- **THEN** the server rejects the behavior at startup
