## MODIFIED Requirements

### Requirement: Server Configuration
The system SHALL read its runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Default configuration is used
- **WHEN** the server starts without `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, `HM_ADMIN_HTTP_HOST`, `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`, `HM_AMQP_ENABLED`, `HM_AMQP_URL`, `HM_GRPC_ENABLED`, `HM_GRPC_PORT`, `HM_GRPC_HOST`, or `HM_GRPC_DESCRIPTOR_SET_PATHS`
- **THEN** it SHALL scan `./templates`, listen on port `9999`, bind to `0.0.0.0`, use log level `info`, use Redis backend type `memory`, use Redis URL `redis://redis:6379`, enable the admin HTTP server, use admin port `9998`, use admin host `0.0.0.0`, disable Kafka, use Kafka client ID `hmock`, use Kafka seed brokers `kafka:9092`, use empty shared Kafka SASL credentials, disable shared Kafka TLS, disable AMQP, use AMQP URL `amqp://guest:guest@rabbitmq:5672`, disable gRPC, use gRPC port `50051`, use gRPC host `0.0.0.0`, and use an empty gRPC descriptor-set path list

#### Scenario: Environment overrides configuration
- **WHEN** the server starts with `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, `HM_ADMIN_HTTP_HOST`, `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`, `HM_AMQP_ENABLED`, `HM_AMQP_URL`, `HM_GRPC_ENABLED`, `HM_GRPC_PORT`, `HM_GRPC_HOST`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` set
- **THEN** it SHALL use those values for template discovery, HTTP bind address, HTTP port, log filtering, Redis backend type, external Redis URL, admin server enablement, admin bind address, admin port, Kafka enablement, Kafka client ID, shared Kafka broker list, shared Kafka SASL credentials, shared Kafka TLS enablement, AMQP enablement, AMQP connection URL, gRPC enablement, gRPC bind address, gRPC port, and gRPC descriptor-set paths

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

### Requirement: gRPC Expectation Validation
The system SHALL validate `expect.grpc` payloads before serving requests.

#### Scenario: gRPC expectation accepts required fields
- **WHEN** a loaded behavior contains `expect.grpc.service` and `expect.grpc.method` as non-empty strings
- **THEN** the system SHALL accept the gRPC expectation as valid

#### Scenario: gRPC expectation rejects missing service
- **WHEN** a loaded behavior contains `expect.grpc` without `service`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC expectation rejects missing method
- **WHEN** a loaded behavior contains `expect.grpc` without `method`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC expectation rejects non-string service
- **WHEN** a loaded behavior contains `expect.grpc.service` that is not a non-empty string
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC expectation rejects non-string method
- **WHEN** a loaded behavior contains `expect.grpc.method` that is not a non-empty string
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Behavior accepts gRPC as a supported matcher
- **WHEN** a loaded behavior contains a valid `expect.grpc`
- **THEN** the system SHALL NOT require `expect.http`, `expect.kafka`, or `expect.amqp` for that behavior

### Requirement: gRPC Reply Action Validation
The system SHALL validate `reply_grpc` action payloads before serving requests.

#### Scenario: gRPC reply action accepts inline payload
- **WHEN** a loaded behavior contains `reply_grpc` with string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: gRPC reply action accepts file payload
- **WHEN** a loaded behavior contains `reply_grpc` with non-empty string `payload_from_file`
- **THEN** the system SHALL accept the action as valid

#### Scenario: gRPC reply action rejects missing payload source
- **WHEN** a loaded behavior contains `reply_grpc` without `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC reply headers must be strings
- **WHEN** a loaded behavior contains `reply_grpc.headers`
- **THEN** every header key and value SHALL be a string

### Requirement: File-Backed gRPC Payload Loading
The system SHALL load `reply_grpc.payload_from_file` content during mock definition loading.

#### Scenario: gRPC payload file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `reply_grpc.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: gRPC payload file is snapshotted at load time
- **WHEN** a loaded behavior defines `reply_grpc.payload_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing gRPC payload file is rejected
- **WHEN** a loaded behavior defines `reply_grpc.payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC payload file outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_grpc.payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
