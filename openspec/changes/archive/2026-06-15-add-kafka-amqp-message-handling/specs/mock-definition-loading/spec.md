## MODIFIED Requirements

### Requirement: Server Configuration
The system SHALL read its runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Default configuration is used
- **WHEN** the server starts without `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, `HM_ADMIN_HTTP_HOST`, `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`, `HM_AMQP_ENABLED`, or `HM_AMQP_URL`
- **THEN** it SHALL scan `./templates`, listen on port `9999`, bind to `0.0.0.0`, use log level `info`, use Redis backend type `memory`, use Redis URL `redis://redis:6379`, enable the admin HTTP server, use admin port `9998`, use admin host `0.0.0.0`, disable Kafka, use Kafka client ID `hmock`, use Kafka seed brokers `kafka:9092`, use empty shared Kafka SASL credentials, disable shared Kafka TLS, disable AMQP, and use AMQP URL `amqp://guest:guest@rabbitmq:5672`

#### Scenario: Environment overrides configuration
- **WHEN** the server starts with `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, `HM_ADMIN_HTTP_HOST`, `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`, `HM_AMQP_ENABLED`, and `HM_AMQP_URL` set
- **THEN** it SHALL use those values for template discovery, HTTP bind address, HTTP port, log filtering, Redis backend type, external Redis URL, admin server enablement, admin bind address, admin port, Kafka enablement, Kafka client ID, shared Kafka broker list, shared Kafka SASL credentials, shared Kafka TLS enablement, AMQP enablement, and AMQP connection URL

#### Scenario: In-memory Redis backend is selected
- **WHEN** `HM_REDIS_TYPE` is `memory`
- **THEN** the system SHALL use an embedded in-memory Redis-compatible store

#### Scenario: External Redis backend is selected
- **WHEN** `HM_REDIS_TYPE` is `redis`
- **THEN** the system SHALL use `HM_REDIS_URL` to connect to an external Redis server

#### Scenario: Kafka producer overrides fall back to shared defaults
- **WHEN** producer-specific Kafka variables are absent
- **THEN** the Kafka producer SHALL use the shared Kafka seed brokers, SASL username, SASL password, and TLS setting

#### Scenario: Kafka consumer overrides fall back to shared defaults
- **WHEN** consumer-specific Kafka variables are absent
- **THEN** the Kafka consumer SHALL use the shared Kafka seed brokers, SASL username, SASL password, and TLS setting

#### Scenario: Kafka producer override values are used
- **WHEN** `HM_KAFKA_PRODUCER_SEED_BROKERS`, `HM_KAFKA_SASL_PRODUCER_USERNAME`, `HM_KAFKA_SASL_PRODUCER_PASSWORD`, or `HM_KAFKA_TLS_PRODUCER_ENABLED` are set
- **THEN** the Kafka producer SHALL use those values instead of the corresponding shared defaults

#### Scenario: Kafka consumer override values are used
- **WHEN** `HM_KAFKA_CONSUMER_SEED_BROKERS`, `HM_KAFKA_SASL_CONSUMER_USERNAME`, `HM_KAFKA_SASL_CONSUMER_PASSWORD`, or `HM_KAFKA_TLS_CONSUMER_ENABLED` are set
- **THEN** the Kafka consumer SHALL use those values instead of the corresponding shared defaults

#### Scenario: Kafka SASL requires username and password
- **WHEN** resolving Kafka producer or consumer settings
- **THEN** SASL SHALL be enabled for that side only when its resolved username and resolved password are both non-empty

## ADDED Requirements

### Requirement: Kafka Expectation Validation
The system SHALL validate `expect.kafka` payloads before serving or consuming messages.

#### Scenario: Kafka expectation accepts topic
- **WHEN** a loaded behavior contains `expect.kafka.topic` as a non-empty string
- **THEN** the system SHALL accept the Kafka expectation as valid

#### Scenario: Kafka expectation rejects missing topic
- **WHEN** a loaded behavior contains `expect.kafka` without `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Kafka expectation rejects non-string topic
- **WHEN** a loaded behavior contains `expect.kafka.topic` that is not a non-empty string
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: AMQP Expectation Validation
The system SHALL validate `expect.amqp` payloads before serving or consuming messages.

#### Scenario: AMQP expectation accepts required fields
- **WHEN** a loaded behavior contains `expect.amqp.exchange` and `expect.amqp.routing_key` as non-empty strings
- **THEN** the system SHALL accept the AMQP expectation as valid

#### Scenario: AMQP expectation defaults queue to routing key
- **WHEN** a loaded behavior contains `expect.amqp.routing_key` and omits `expect.amqp.queue` or sets it to an empty value
- **THEN** the system SHALL store the routing key as the effective queue name

#### Scenario: AMQP expectation accepts explicit queue
- **WHEN** a loaded behavior contains `expect.amqp.queue` as a non-empty string
- **THEN** the system SHALL use that value as the effective queue name

#### Scenario: AMQP expectation rejects missing exchange
- **WHEN** a loaded behavior contains `expect.amqp` without `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation rejects missing routing key
- **WHEN** a loaded behavior contains `expect.amqp` without `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation rejects non-string queue
- **WHEN** a loaded behavior contains `expect.amqp.queue` that is not a string
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker Publish Action Validation
The system SHALL validate `publish_kafka` and `publish_amqp` action payloads before serving or consuming messages.

#### Scenario: Kafka publish action accepts inline payload
- **WHEN** a loaded behavior contains `publish_kafka` with non-empty string `topic` and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action accepts file payload
- **WHEN** a loaded behavior contains `publish_kafka` with non-empty string `topic` and non-empty string `payload_from_file`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action rejects missing payload source
- **WHEN** a loaded behavior contains `publish_kafka` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action accepts inline payload
- **WHEN** a loaded behavior contains `publish_amqp` with non-empty string `exchange`, non-empty string `routing_key`, and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action accepts file payload
- **WHEN** a loaded behavior contains `publish_amqp` with non-empty string `exchange`, non-empty string `routing_key`, and non-empty string `payload_from_file`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action rejects missing payload source
- **WHEN** a loaded behavior contains `publish_amqp` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: File-Backed Broker Payload Loading
The system SHALL load `payload_from_file` content for broker publish actions during mock definition loading.

#### Scenario: Broker payload file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Broker payload file is snapshotted at load time
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing broker payload file is rejected
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker payload file outside templates directory is rejected
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
