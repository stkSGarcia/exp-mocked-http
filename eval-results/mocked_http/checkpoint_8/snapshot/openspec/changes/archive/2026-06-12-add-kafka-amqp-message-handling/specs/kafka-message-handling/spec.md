## ADDED Requirements

> Extends: cors-response-policy/add-hot-reload-cors-binary-admin-cli
>
> Extends: http-yaml-mock-server/add-template-helpers-file-backed-bodies
>
> Extends: http-yaml-mock-server/add-admin-api-template-persistence

### Requirement: Kafka configuration defaults
The system SHALL read Kafka runtime settings from the environment and SHALL default `HM_KAFKA_ENABLED` to `false`, `HM_KAFKA_CLIENT_ID` to `hmock`, `HM_KAFKA_SEED_BROKERS` to `kafka:9092`, both shared SASL credentials to empty strings, and `HM_KAFKA_TLS_ENABLED` to `false`.

#### Scenario: Kafka is disabled by default
- **GIVEN** no Kafka environment variables are set
- **WHEN** configuration is loaded
- **THEN** Kafka consumption and publishing are disabled
- **AND** the client ID and shared broker list use their documented defaults

#### Scenario: Invalid Kafka boolean
- **GIVEN** a Kafka enabled or TLS environment variable contains a value that is not a supported boolean
- **WHEN** configuration is loaded
- **THEN** configuration loading fails and identifies the invalid variable

### Requirement: Kafka role-specific configuration resolution
The system SHALL resolve producer and consumer brokers, SASL credentials, and TLS independently, using a non-empty role-specific environment value when present and otherwise falling back to the corresponding shared value. The system SHALL enable SASL for a role only when that role's resolved username and password are both non-empty.

#### Scenario: Producer override with consumer fallback
- **GIVEN** shared Kafka settings are configured and only producer-specific settings are provided
- **WHEN** Kafka role settings are resolved
- **THEN** the producer uses its specific values
- **AND** the consumer uses the shared values

#### Scenario: Partial role SASL credentials
- **GIVEN** a role resolves only a username or only a password
- **WHEN** Kafka authentication settings are resolved
- **THEN** SASL is disabled for that role

#### Scenario: Complete role SASL credentials
- **GIVEN** a role resolves both a non-empty username and a non-empty password
- **WHEN** Kafka authentication settings are resolved
- **THEN** SASL is enabled for that role with those credentials

### Requirement: Kafka expectation validation and subscriptions
The system SHALL accept `expect.kafka.topic` as the Kafka message selector and SHALL consume from the unique set of non-empty topics referenced by loaded concrete behaviors when Kafka is enabled.

#### Scenario: Referenced topics are subscribed
- **GIVEN** loaded concrete behaviors reference multiple Kafka topics, including duplicate topic names
- **WHEN** the Kafka consumer starts or the runtime behavior set changes
- **THEN** it subscribes to each referenced topic once
- **AND** it does not subscribe to unrelated topics

#### Scenario: Invalid Kafka expectation
- **GIVEN** a behavior defines `expect.kafka` without a non-empty topic
- **WHEN** behaviors are compiled
- **THEN** compilation fails with a validation error

### Requirement: Kafka message context and matching
The system SHALL expose `.KafkaTopic` and `.KafkaPayload` as strings while processing a Kafka message. It SHALL match behaviors by topic, evaluate `expect.condition` with the Kafka context and behavior values, and execute every matching behavior in loaded order.

#### Scenario: Multiple Kafka behaviors match
- **GIVEN** multiple loaded behaviors reference the consumed topic and their conditions pass
- **WHEN** a message is consumed from that topic
- **THEN** every matching behavior executes
- **AND** execution follows loaded behavior order

#### Scenario: Kafka condition filters a behavior
- **GIVEN** a behavior references the consumed topic but its condition does not render exactly `true`
- **WHEN** the Kafka message is processed
- **THEN** that behavior's actions are not executed
- **AND** later matching behaviors are still evaluated

#### Scenario: Kafka templates receive message values
- **GIVEN** an action template references `.KafkaTopic` and `.KafkaPayload`
- **WHEN** a Kafka message triggers the behavior
- **THEN** the action renders the consumed topic and payload values

### Requirement: Kafka publishing action
The system SHALL support a `publish_kafka` action with a required non-empty `topic` and either a non-empty `payload` or `payload_from_file`. Topic and selected payload content SHALL be template-rendered with the triggering context before publishing.

#### Scenario: Inline Kafka payload
- **GIVEN** a `publish_kafka` action has a topic and non-empty inline payload
- **WHEN** the action executes
- **THEN** the rendered payload is published to the rendered topic using the Kafka producer

#### Scenario: File-backed Kafka payload
- **GIVEN** a `publish_kafka` action has an empty or absent inline payload and a valid `payload_from_file`
- **WHEN** definitions are loaded and the action later executes
- **THEN** the file is snapshotted from inside `HM_TEMPLATES_DIR`
- **AND** its contents are template-rendered and published

#### Scenario: Inline Kafka payload takes precedence
- **GIVEN** a `publish_kafka` action provides both a non-empty inline payload and `payload_from_file`
- **WHEN** the action executes
- **THEN** the inline payload is rendered and published

#### Scenario: Invalid Kafka publish action
- **GIVEN** a `publish_kafka` action omits its topic or both payload sources
- **WHEN** behaviors are compiled
- **THEN** compilation fails with a validation error

### Requirement: Kafka runtime lifecycle
The system SHALL create Kafka producer and consumer resources only when Kafka is enabled and SHALL stop those resources during server shutdown.

#### Scenario: Kafka remains inactive
- **GIVEN** Kafka is disabled
- **WHEN** the mock server starts
- **THEN** no Kafka producer or consumer connection is created

#### Scenario: Kafka shutdown
- **GIVEN** Kafka resources are running
- **WHEN** the mock server shuts down
- **THEN** Kafka consumption stops
- **AND** producer and consumer resources are closed
