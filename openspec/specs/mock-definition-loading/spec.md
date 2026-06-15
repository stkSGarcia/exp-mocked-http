## Purpose

Define how YAML mock definitions are discovered, validated, ordered, and merged before serving requests.

## Requirements

### Requirement: Server Configuration
The system SHALL read its runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Default configuration is used
- **WHEN** the server starts without `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, or `HM_REDIS_URL`
- **THEN** it SHALL scan `./templates`, listen on port `9999`, bind to `0.0.0.0`, use log level `info`, use Redis backend type `memory`, and use Redis URL `redis://redis:6379`

#### Scenario: Environment overrides configuration
- **WHEN** the server starts with `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, and `HM_REDIS_URL` set
- **THEN** it SHALL use those values for template discovery, HTTP bind address, HTTP port, log filtering, Redis backend type, and external Redis URL

#### Scenario: In-memory Redis backend is selected
- **WHEN** `HM_REDIS_TYPE` is `memory`
- **THEN** the system SHALL use an embedded in-memory Redis-compatible store

#### Scenario: External Redis backend is selected
- **WHEN** `HM_REDIS_TYPE` is `redis`
- **THEN** the system SHALL use `HM_REDIS_URL` to connect to an external Redis server

### Requirement: Templates Directory Hot Reload Configuration
The system SHALL control filesystem template hot reload through `HM_TEMPLATES_DIR_HOT_RELOAD`, defaulting to enabled.

#### Scenario: Hot reload default is enabled
- **WHEN** the server starts without `HM_TEMPLATES_DIR_HOT_RELOAD`
- **THEN** filesystem creations, edits, and deletions under `HM_TEMPLATES_DIR` SHALL become visible to mock-server request handling without restarting the process

#### Scenario: Hot reload enabled explicitly
- **WHEN** the server starts with `HM_TEMPLATES_DIR_HOT_RELOAD=true`
- **THEN** filesystem creations, edits, and deletions under `HM_TEMPLATES_DIR` SHALL become visible to mock-server request handling without restarting the process

#### Scenario: Hot reload disabled
- **WHEN** the server starts with `HM_TEMPLATES_DIR_HOT_RELOAD=false`
- **THEN** filesystem creations, edits, and deletions under `HM_TEMPLATES_DIR` SHALL NOT affect mock-server request handling until a later reload boundary

#### Scenario: Admin mutations still reload when filesystem hot reload is disabled
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=false` and a successful admin API mutation changes persisted mock definitions
- **THEN** later mock-server requests SHALL observe the admin mutation within the normal admin reload window

### Requirement: Recursive YAML Discovery
The system SHALL recursively scan `HM_TEMPLATES_DIR` and load every file ending in `.yaml` or `.yml`.

#### Scenario: Nested YAML files are loaded
- **WHEN** the templates directory contains YAML files at multiple directory depths
- **THEN** the system SHALL load each `.yaml` and `.yml` file into the mock definition stream

#### Scenario: Non-YAML files are ignored
- **WHEN** the templates directory contains files without `.yaml` or `.yml` extensions
- **THEN** the system SHALL ignore those files during mock loading

### Requirement: Behavior Schema Validation
The system SHALL validate loaded mock definitions before serving requests.

#### Scenario: Missing key is rejected
- **WHEN** a loaded definition omits `key`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Empty key is rejected
- **WHEN** a loaded definition has `key` set to an empty string or non-string value
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Kind defaults to Behavior
- **WHEN** a loaded definition omits `kind`
- **THEN** the system SHALL treat `kind` as `Behavior`

#### Scenario: Valid kinds are accepted
- **WHEN** a loaded definition has `kind` set to `Behavior`, `Template`, or `AbstractBehavior`
- **THEN** the system SHALL validate that definition using the field rules for that kind

#### Scenario: Invalid kind is rejected
- **WHEN** a loaded definition has `kind` set to any value other than `Behavior`, `Template`, or `AbstractBehavior`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Behavior allowed fields are enforced
- **WHEN** a loaded `Behavior` definition includes fields outside `key`, `kind`, `extend`, `expect`, `actions`, or `values`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Behavior template field is rejected
- **WHEN** a loaded `Behavior` definition includes `template`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Template allowed fields are enforced
- **WHEN** a loaded `Template` definition includes fields outside `key`, `kind`, or `template`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Abstract behavior allowed fields are enforced
- **WHEN** a loaded `AbstractBehavior` definition includes fields outside `key`, `kind`, `expect`, `actions`, or `values`
- **THEN** the system SHALL reject that definition as invalid

#### Scenario: Multiple HTTP replies are rejected
- **WHEN** an effective concrete behavior contains more than one `reply_http` action after inheritance is resolved
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Reusable Template Definitions
The system SHALL load `Template` definitions as named reusable template fragments.

#### Scenario: Template is registered by key
- **WHEN** a loaded definition has `kind` set to `Template` with a non-empty `key` and string `template`
- **THEN** the system SHALL register the template source under that key for later template rendering

#### Scenario: Template is not included in behavior matching
- **WHEN** a loaded definition has `kind` set to `Template`
- **THEN** the system SHALL NOT include that definition in the effective behavior list used for HTTP request matching

#### Scenario: Template rejects behavior fields
- **WHEN** a loaded `Template` definition includes `expect`, `actions`, `values`, or `extend`
- **THEN** the system SHALL reject that definition as invalid

### Requirement: Abstract Behavior Definitions
The system SHALL load `AbstractBehavior` definitions as reusable behavior bases that never trigger directly.

#### Scenario: Abstract behavior accepts reusable behavior fields
- **WHEN** a loaded definition has `kind` set to `AbstractBehavior` with `expect`, `actions`, or `values`
- **THEN** the system SHALL accept those fields for inheritance by concrete behaviors

#### Scenario: Abstract behavior is not matched directly
- **WHEN** a loaded definition has `kind` set to `AbstractBehavior`
- **THEN** the system SHALL NOT include that definition in the effective behavior list used for HTTP request matching

#### Scenario: Abstract behavior rejects unsupported fields
- **WHEN** a loaded `AbstractBehavior` definition includes `extend` or `template`
- **THEN** the system SHALL reject that definition as invalid

### Requirement: Behavior Inheritance
The system SHALL allow a concrete `Behavior` to extend another `Behavior` or an `AbstractBehavior`.

#### Scenario: Parent is resolved regardless of definition order
- **WHEN** a `Behavior` extends a parent key that is defined later in the discovered YAML stream
- **THEN** the system SHALL resolve the parent and load the child using inherited fields

#### Scenario: Missing parent extension is skipped
- **WHEN** a `Behavior` extends a parent key that is not present
- **THEN** the system SHALL validate and load the child using only its own fields

#### Scenario: Missing inherited requirements still fail
- **WHEN** a `Behavior` extends a missing parent and the child does not define required concrete behavior fields
- **THEN** the system SHALL reject the child as invalid

#### Scenario: Values maps are merged with child override
- **WHEN** a child behavior extends a parent and both define `values`
- **THEN** the effective behavior SHALL contain the merged values map with child keys overriding matching parent keys

#### Scenario: Parent actions precede child actions before ordering
- **WHEN** a child behavior extends a parent and both define `actions`
- **THEN** the effective behavior SHALL include the parent's actions before the child's actions before action order sorting is applied

#### Scenario: Expect maps are merged recursively
- **WHEN** a child behavior extends a parent and both define nested `expect` fields
- **THEN** the effective behavior SHALL inherit missing child fields and override matching parent fields with child values

#### Scenario: Other fields prefer child non-zero values
- **WHEN** a child behavior extends a parent and both define scalar fields such as `kind` or `key`
- **THEN** the effective behavior SHALL use the child value when it is present and non-zero, otherwise the parent value

#### Scenario: Inheritance cycles are rejected
- **WHEN** resolving a behavior extension would revisit the same definition key in the parent chain
- **THEN** the system SHALL reject the definition as invalid

### Requirement: Definition Values
The system SHALL allow concrete and abstract behavior definitions to define arbitrary `values` maps.

#### Scenario: Behavior values map is accepted
- **WHEN** a `Behavior` definition includes `values` as a mapping
- **THEN** the system SHALL store that mapping on the effective behavior

#### Scenario: Abstract behavior values map is accepted
- **WHEN** an `AbstractBehavior` definition includes `values` as a mapping
- **THEN** the system SHALL make that mapping available to child behaviors through inheritance

#### Scenario: Non-map values are rejected
- **WHEN** a `Behavior` or `AbstractBehavior` definition includes `values` that is not a mapping
- **THEN** the system SHALL reject that definition as invalid

### Requirement: File-Backed Response Body Loading
The system SHALL load `reply_http.body_from_file` content during mock definition loading.

#### Scenario: Body file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `reply_http.body_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Body file is snapshotted at load time
- **WHEN** a loaded behavior defines `reply_http.body_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing body file is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Body file path outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Binary File Payload Loading
The system SHALL load binary file payloads for `reply_http` and `send_http` actions during mock definition loading.

#### Scenario: Reply binary file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Send binary file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary file is snapshotted at load time
- **WHEN** a loaded behavior defines `body_from_binary_file` for `reply_http` or `send_http`
- **THEN** the system SHALL store a stable byte snapshot of the file contents for that loaded configuration

#### Scenario: Missing binary file is rejected
- **WHEN** a loaded behavior defines `body_from_binary_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary file path outside templates directory is rejected
- **WHEN** a loaded behavior defines `body_from_binary_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary filename metadata is accepted
- **WHEN** a loaded behavior defines `binary_file_name` as a string with `body_from_binary_file`
- **THEN** the system SHALL retain that filename metadata for binary response or outbound upload execution

### Requirement: Redis Action Validation
The system SHALL validate `redis` action payloads before serving requests.

#### Scenario: Redis action accepts string array
- **WHEN** a loaded behavior contains a `redis` action with an array of strings
- **THEN** the system SHALL accept the action as valid

#### Scenario: Redis action rejects non-array payload
- **WHEN** a loaded behavior contains a `redis` action whose payload is not an array
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Redis action rejects non-string item
- **WHEN** a loaded behavior contains a `redis` action with an item that is not a string
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Outbound HTTP Action Validation
The system SHALL validate `send_http` action payloads before serving requests.

#### Scenario: Outbound HTTP action accepts required fields
- **WHEN** a loaded behavior contains a `send_http` action with string `url` and string `method`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Outbound HTTP action rejects missing URL
- **WHEN** a loaded behavior contains a `send_http` action without `url`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Outbound HTTP action rejects missing method
- **WHEN** a loaded behavior contains a `send_http` action without `method`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Outbound HTTP action rejects non-string headers
- **WHEN** a loaded behavior contains a `send_http` action with a `headers` entry whose value is not a string
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Outbound HTTP file body path resolves relative to templates directory
- **WHEN** a loaded behavior defines `send_http.body_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Outbound HTTP file body is snapshotted at load time
- **WHEN** a loaded behavior defines `send_http.body_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing outbound HTTP file body is rejected
- **WHEN** a loaded behavior defines `send_http.body_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Outbound HTTP file body outside templates directory is rejected
- **WHEN** a loaded behavior defines `send_http.body_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker Runtime Configuration
The system SHALL read Kafka and AMQP runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Kafka and AMQP defaults are disabled
- **WHEN** the server starts without Kafka or AMQP environment variables
- **THEN** `HM_KAFKA_ENABLED` SHALL default to `false` and `HM_AMQP_ENABLED` SHALL default to `false`

#### Scenario: Kafka environment variables are loaded
- **WHEN** the server starts with Kafka environment variables set
- **THEN** the system SHALL load `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`, `HM_KAFKA_PRODUCER_SEED_BROKERS`, `HM_KAFKA_CONSUMER_SEED_BROKERS`, `HM_KAFKA_SASL_PRODUCER_USERNAME`, `HM_KAFKA_SASL_PRODUCER_PASSWORD`, `HM_KAFKA_SASL_CONSUMER_USERNAME`, `HM_KAFKA_SASL_CONSUMER_PASSWORD`, `HM_KAFKA_TLS_PRODUCER_ENABLED`, and `HM_KAFKA_TLS_CONSUMER_ENABLED`

#### Scenario: AMQP environment variables are loaded
- **WHEN** the server starts with AMQP environment variables set
- **THEN** the system SHALL load `HM_AMQP_ENABLED` and `HM_AMQP_URL`

### Requirement: Broker Expectation Validation
The system SHALL validate Kafka and AMQP expectation fields before serving requests or consuming messages.

#### Scenario: Kafka expectation accepts topic
- **WHEN** a loaded behavior defines `expect.kafka.topic` as a non-empty string
- **THEN** the system SHALL accept the Kafka expectation

#### Scenario: Kafka expectation rejects missing topic
- **WHEN** a loaded behavior defines `expect.kafka` without a non-empty string `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation accepts required fields
- **WHEN** a loaded behavior defines `expect.amqp.exchange` and `expect.amqp.routing_key` as strings
- **THEN** the system SHALL accept the AMQP expectation

#### Scenario: AMQP expectation rejects missing exchange
- **WHEN** a loaded behavior defines `expect.amqp` without a string `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP expectation rejects missing routing key
- **WHEN** a loaded behavior defines `expect.amqp` without a string `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP queue must be string when present
- **WHEN** a loaded behavior defines `expect.amqp.queue`
- **THEN** the system SHALL reject that behavior unless the queue value is a string

#### Scenario: Broker-only behavior is accepted
- **WHEN** a loaded behavior defines `expect.kafka` or `expect.amqp` and omits `expect.http`
- **THEN** the system SHALL accept the behavior when the broker expectation and actions are otherwise valid

### Requirement: Broker Publish Action Validation
The system SHALL validate `publish_kafka` and `publish_amqp` action payloads before serving requests or consuming messages.

#### Scenario: Kafka publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic` and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic` and string `payload_from_file`
- **THEN** the system SHALL accept the action as valid without requiring `payload`

#### Scenario: Kafka publish action rejects missing topic
- **WHEN** a loaded behavior contains a `publish_kafka` action without a non-empty string `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Kafka publish action requires payload source
- **WHEN** a loaded behavior contains a `publish_kafka` action without a non-empty `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, and string `payload_from_file`
- **THEN** the system SHALL accept the action as valid without requiring `payload`

#### Scenario: AMQP publish action rejects missing exchange
- **WHEN** a loaded behavior contains a `publish_amqp` action without a string `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action rejects missing routing key
- **WHEN** a loaded behavior contains a `publish_amqp` action without a string `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action requires payload source
- **WHEN** a loaded behavior contains a `publish_amqp` action without a non-empty `payload` or `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker File-Backed Payload Loading
The system SHALL load file-backed Kafka and AMQP publish payloads during mock definition loading.

#### Scenario: Kafka publish payload file resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: AMQP publish payload file resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_amqp.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Broker payload file is snapshotted at load time
- **WHEN** a loaded behavior defines `payload_from_file` for `publish_kafka` or `publish_amqp`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing broker payload file is rejected
- **WHEN** a loaded behavior defines broker `payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker payload file outside templates directory is rejected
- **WHEN** a loaded behavior defines broker `payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Ordered Behavior Merge
The system SHALL merge all loaded behavior objects into one ordered list for request evaluation.

#### Scenario: Behaviors preserve load order
- **WHEN** multiple valid behaviors are loaded from discovered YAML files
- **THEN** the system SHALL evaluate matching behaviors in the merged load order

#### Scenario: Duplicate key replacement
- **WHEN** multiple loaded behaviors use the same `key`
- **THEN** the system SHALL keep the last loaded behavior for that key and remove the earlier behavior from the effective list

#### Scenario: Duplicate key warning
- **WHEN** a later behavior replaces an earlier behavior with the same `key`
- **THEN** the system SHALL emit a warning log for the override

### Requirement: Persistent Admin Mock Loading
The system SHALL persist API-added mock definitions across process restarts and load them into the active mock definition stream.

#### Scenario: Persisted base API mocks load on startup
- **WHEN** the server starts and the persistent store contains base API-added mocks
- **THEN** the system SHALL load those mocks and include them in the active mock set

#### Scenario: Persisted template sets load on startup
- **WHEN** the server starts and the persistent store contains one or more template sets
- **THEN** the system SHALL load every persisted template set and include its mock definitions in the active mock set

#### Scenario: Persisted mocks merge with filesystem mocks
- **WHEN** filesystem mocks and persisted mocks are both available
- **THEN** the system SHALL merge them into one active mock set

#### Scenario: Duplicate keys use last loaded definition
- **WHEN** multiple filesystem or persisted mock definitions use the same `key`
- **THEN** the system SHALL keep the last loaded definition for that key and remove earlier definitions from the effective list

### Requirement: Persisted Mock Load Order
The system SHALL load persisted admin-managed mocks in a deterministic order after filesystem mocks.

#### Scenario: Base API mocks load after filesystem mocks
- **WHEN** a filesystem mock and a base API-added mock use the same `key`
- **THEN** the base API-added mock SHALL be the last loaded definition for that key

#### Scenario: Template sets load after base API mocks
- **WHEN** a base API-added mock and a template-set mock use the same `key`
- **THEN** the template-set mock SHALL be the last loaded definition for that key when its set is loaded after the base API mock collection

#### Scenario: Template sets load by set key
- **WHEN** multiple template sets are persisted
- **THEN** the system SHALL load template sets in lexicographic order by set key while preserving definition order within each set

### Requirement: Template Set Isolation
The system SHALL keep persisted template sets isolated by set key.

#### Scenario: Replacing one set preserves other sets
- **WHEN** a template set is created or replaced for one `{setKey}`
- **THEN** the system SHALL leave every other persisted template set unchanged

#### Scenario: Deleting one set preserves other sets
- **WHEN** a template set is deleted for one `{setKey}`
- **THEN** the system SHALL leave every other persisted template set unchanged

#### Scenario: Clearing base API mocks preserves template sets
- **WHEN** all base API-added mocks are deleted
- **THEN** the system SHALL leave every persisted template set unchanged
