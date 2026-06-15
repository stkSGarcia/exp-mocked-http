## Purpose

Define how YAML mock definitions are discovered, validated, ordered, and merged before serving requests.
## Requirements
### Requirement: Server Configuration
The system SHALL read its runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Default configuration is used
- **WHEN** the server starts without `HM_TEMPLATES_DIR`, `HM_TEMPLATES_DIR_HOT_RELOAD`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, or `HM_CORS_ENABLED`
- **THEN** it SHALL scan `./templates`, enable templates-directory hot reload, listen on port `9999`, bind to `0.0.0.0`, use log level `info`, use Redis backend type `memory`, use Redis URL `redis://redis:6379`, and disable mock-server CORS

#### Scenario: Environment overrides configuration
- **WHEN** the server starts with `HM_TEMPLATES_DIR`, `HM_TEMPLATES_DIR_HOT_RELOAD`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, and `HM_CORS_ENABLED` set
- **THEN** it SHALL use those values for template discovery, templates-directory hot reload, HTTP bind address, HTTP port, log filtering, Redis backend type, external Redis URL, and mock-server CORS enablement

#### Scenario: In-memory Redis backend is selected
- **WHEN** `HM_REDIS_TYPE` is `memory`
- **THEN** the system SHALL use an embedded in-memory Redis-compatible store

#### Scenario: External Redis backend is selected
- **WHEN** `HM_REDIS_TYPE` is `redis`
- **THEN** the system SHALL use `HM_REDIS_URL` to connect to an external Redis server

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

### Requirement: Broker Expectation Validation
The system SHALL validate Kafka and AMQP expectations in loaded behavior definitions.

#### Scenario: Kafka behavior accepts topic
- **WHEN** a loaded concrete behavior defines `expect.kafka.topic` as a non-empty string
- **THEN** the system SHALL accept the behavior as eligible for Kafka message matching

#### Scenario: Kafka behavior rejects missing topic
- **WHEN** a loaded concrete behavior defines `expect.kafka` without a non-empty string `topic`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP behavior accepts exchange and routing key
- **WHEN** a loaded concrete behavior defines `expect.amqp.exchange` and `expect.amqp.routing_key` as non-empty strings
- **THEN** the system SHALL accept the behavior as eligible for AMQP message matching

#### Scenario: AMQP queue defaults during loading
- **WHEN** a loaded concrete behavior defines `expect.amqp` without `queue` or with an empty `queue`
- **THEN** the system SHALL store the effective AMQP queue as the behavior's `expect.amqp.routing_key`

#### Scenario: AMQP behavior rejects missing exchange
- **WHEN** a loaded concrete behavior defines `expect.amqp` without a non-empty string `exchange`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP behavior rejects missing routing key
- **WHEN** a loaded concrete behavior defines `expect.amqp` without a non-empty string `routing_key`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Broker Publish Action Validation
The system SHALL validate `publish_kafka` and `publish_amqp` action payloads before serving requests or consuming broker messages.

#### Scenario: Kafka publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic` and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_kafka` action with string `topic`, string `payload_from_file`, and no `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: Kafka publish action rejects missing payload source
- **WHEN** a loaded behavior contains a `publish_kafka` action without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: AMQP publish action accepts required fields
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, and string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action accepts file-backed payload
- **WHEN** a loaded behavior contains a `publish_amqp` action with string `exchange`, string `routing_key`, string `payload_from_file`, and no `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: AMQP publish action rejects missing payload source
- **WHEN** a loaded behavior contains a `publish_amqp` action without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker publish file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Broker publish file payload is snapshotted at load time
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file`
- **THEN** the system SHALL store a stable snapshot of the file contents for that loaded configuration

#### Scenario: Missing broker publish file payload is rejected
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Broker publish file payload outside templates directory is rejected
- **WHEN** a loaded behavior defines `publish_kafka.payload_from_file` or `publish_amqp.payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
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

### Requirement: Persisted API Mock Loading
The system SHALL load persisted API-added mock definitions at startup and merge them with filesystem-loaded mock definitions into one active set.

#### Scenario: Persisted base mocks load on startup
- **WHEN** the server starts and base API-added mocks are present in persistent storage
- **THEN** the system SHALL load those mocks into the active mock set

#### Scenario: Persisted template sets load on startup
- **WHEN** the server starts and one or more template sets are present in persistent storage
- **THEN** the system SHALL load every persisted template set into the active mock set

#### Scenario: Filesystem and persisted mocks merge
- **WHEN** filesystem-loaded mocks, base API-added mocks, and template-set mocks are all present
- **THEN** the system SHALL merge them into one active mock definition stream

#### Scenario: Duplicate persisted key uses last loaded definition
- **WHEN** multiple loaded definitions from filesystem storage, base API storage, or template sets use the same `key`
- **THEN** the system SHALL keep the last loaded definition for that key and remove the earlier definition from the effective list

### Requirement: API Mock Persistence
The system SHALL persist mock definitions created or updated through the admin API so they can be loaded by later server instances using the same persistent backend.

#### Scenario: Base API mocks survive restart
- **WHEN** valid base API-added mocks have been persisted and the server is restarted with the same persistent backend
- **THEN** the restarted server SHALL load those mocks into the active mock set

#### Scenario: Template sets survive restart
- **WHEN** a valid template set has been persisted and the server is restarted with the same persistent backend
- **THEN** the restarted server SHALL load that template set into the active mock set

### Requirement: Template Set Isolation
The system SHALL store and load each named template set independently.

#### Scenario: Replacing one set does not affect another
- **WHEN** a client replaces template set `a`
- **THEN** the system SHALL leave persisted template set `b` unchanged

#### Scenario: Deleting one set does not affect another
- **WHEN** a client deletes template set `a`
- **THEN** the system SHALL leave persisted template set `b` unchanged

#### Scenario: Deleting base templates does not affect sets
- **WHEN** a client deletes all base API-added mocks
- **THEN** the system SHALL leave every persisted template set unchanged

### Requirement: Admin Mutation Reload Visibility
The system SHALL make successful admin mutations visible to subsequent mock requests within a bounded eventual-reload window.

#### Scenario: Upsert becomes visible after success
- **WHEN** an admin upsert request returns success
- **THEN** later mock requests SHALL observe the updated active mock set within the reload window

#### Scenario: Delete becomes visible after success
- **WHEN** an admin delete request returns success
- **THEN** later mock requests SHALL observe the deleted mock or set within the reload window

#### Scenario: Failed mutation keeps previous active set
- **WHEN** an admin mutation fails validation
- **THEN** the system SHALL keep serving the previously active mock set

### Requirement: Templates Directory Hot Reload
The system SHALL make filesystem template changes visible automatically when templates-directory hot reload is enabled.

#### Scenario: New filesystem definition becomes visible
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is enabled and a YAML definition file is created under `HM_TEMPLATES_DIR`
- **THEN** subsequent mock request handling SHALL observe the new definition without restarting the server

#### Scenario: Edited filesystem definition becomes visible
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is enabled and an existing YAML definition file under `HM_TEMPLATES_DIR` is edited
- **THEN** subsequent mock request handling SHALL observe the edited definition without restarting the server

#### Scenario: Deleted filesystem definition is removed
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is enabled and an existing YAML definition file under `HM_TEMPLATES_DIR` is deleted
- **THEN** subsequent mock request handling SHALL stop serving definitions that only came from that file without restarting the server

#### Scenario: Hot reload disabled preserves loaded filesystem snapshot
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is disabled and files under `HM_TEMPLATES_DIR` are created, edited, or deleted after startup
- **THEN** mock request handling SHALL continue using the previously loaded filesystem definitions until a later reload boundary

#### Scenario: Admin mutations remain visible when filesystem hot reload is disabled
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is disabled and a successful admin API mutation changes persisted mock definitions
- **THEN** subsequent mock request handling SHALL observe the admin mutation within the normal reload window

#### Scenario: Failed filesystem hot reload keeps previous active set
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is enabled and a filesystem change makes the mock collection fail validation
- **THEN** the system SHALL keep serving the previous active mock set

### Requirement: Binary File-Backed Response Body Loading
The system SHALL load `reply_http.body_from_binary_file` content as bytes during mock definition loading.

#### Scenario: Binary response file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary response file is snapshotted at load time
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **THEN** the system SHALL store a stable byte snapshot of the file contents for that loaded configuration

#### Scenario: Missing binary response file is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary response file path outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary response filename is accepted
- **WHEN** a loaded behavior defines `reply_http.binary_file_name` as a string
- **THEN** the system SHALL accept the configured filename for later response header generation

#### Scenario: Non-string binary response filename is rejected
- **WHEN** a loaded behavior defines `reply_http.binary_file_name` as a non-string value
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Binary Outbound HTTP Body Loading
The system SHALL load `send_http.body_from_binary_file` content as bytes during mock definition loading.

#### Scenario: Binary outbound file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary outbound file is snapshotted at load time
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file`
- **THEN** the system SHALL store a stable byte snapshot of the file contents for that loaded configuration

#### Scenario: Missing binary outbound file is rejected
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary outbound file path outside templates directory is rejected
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary outbound filename is accepted
- **WHEN** a loaded behavior defines `send_http.binary_file_name` as a string
- **THEN** the system SHALL accept the configured filename for later outbound request generation

#### Scenario: Non-string binary outbound filename is rejected
- **WHEN** a loaded behavior defines `send_http.binary_file_name` as a non-string value
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: gRPC Expectation Validation
The system SHALL validate gRPC expectations in loaded behavior definitions.

#### Scenario: gRPC behavior accepts service and method
- **WHEN** a loaded concrete behavior defines `expect.grpc.service` and `expect.grpc.method` as non-empty strings
- **THEN** the system SHALL accept the behavior as eligible for gRPC request matching

#### Scenario: gRPC behavior rejects missing service
- **WHEN** a loaded concrete behavior defines `expect.grpc` without a non-empty string `service`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC behavior rejects missing method
- **WHEN** a loaded concrete behavior defines `expect.grpc` without a non-empty string `method`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC participates in exactly-one trigger validation
- **WHEN** a loaded concrete behavior defines `expect.grpc` together with another concrete trigger such as `expect.http`, `expect.kafka`, or `expect.amqp`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: gRPC Reply Action Validation
The system SHALL validate `reply_grpc` action payloads before serving requests.

#### Scenario: gRPC reply accepts inline payload
- **WHEN** a loaded behavior contains `reply_grpc` with string `payload`
- **THEN** the system SHALL accept the action as valid

#### Scenario: gRPC reply accepts file payload
- **WHEN** a loaded behavior contains `reply_grpc` with `payload_from_file` and no non-empty `payload`
- **THEN** the system SHALL resolve and snapshot the file content relative to `HM_TEMPLATES_DIR`

#### Scenario: gRPC reply requires payload source
- **WHEN** a loaded behavior contains `reply_grpc` without `payload` and without `payload_from_file`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: gRPC reply validates headers
- **WHEN** a loaded behavior contains `reply_grpc.headers`
- **THEN** the system SHALL require `headers` to be a string map

#### Scenario: gRPC reply file path outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_grpc.payload_from_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid
