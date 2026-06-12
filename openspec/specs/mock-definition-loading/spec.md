## Purpose

Define how YAML mock definitions are discovered, validated, ordered, and merged before serving requests.

## Requirements

### Requirement: Server Configuration
The system SHALL read its runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Default configuration is used
- **WHEN** the server starts without `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, or `HM_ADMIN_HTTP_HOST`
- **THEN** it SHALL scan `./templates`, listen on port `9999`, bind to `0.0.0.0`, use log level `info`, use Redis backend type `memory`, use Redis URL `redis://redis:6379`, enable the admin HTTP server, use admin port `9998`, and use admin host `0.0.0.0`

#### Scenario: Environment overrides configuration
- **WHEN** the server starts with `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`, `HM_REDIS_TYPE`, `HM_REDIS_URL`, `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` set
- **THEN** it SHALL use those values for template discovery, HTTP bind address, HTTP port, log filtering, Redis backend type, external Redis URL, admin server enablement, admin bind address, and admin port

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

### Requirement: Ordered Behavior Merge
The system SHALL merge all loaded behavior objects into one ordered list for request evaluation.

#### Scenario: Filesystem behaviors preserve load order
- **WHEN** multiple valid behaviors are loaded from discovered YAML files
- **THEN** the system SHALL evaluate matching filesystem behaviors in the merged filesystem load order

#### Scenario: Persisted base mocks load after filesystem mocks
- **WHEN** filesystem mocks and persisted base API-added mocks are loaded
- **THEN** the system SHALL merge persisted base API-added mocks after filesystem-loaded mocks

#### Scenario: Persisted template sets load after base mocks
- **WHEN** filesystem mocks, persisted base API-added mocks, and persisted template sets are loaded
- **THEN** the system SHALL merge persisted template-set mocks after persisted base API-added mocks

#### Scenario: Template sets use deterministic merge order
- **WHEN** multiple persisted template sets are loaded
- **THEN** the system SHALL merge those template sets in deterministic set-key order

#### Scenario: Duplicate key replacement
- **WHEN** multiple loaded behaviors use the same `key`
- **THEN** the system SHALL keep the last loaded behavior for that key and remove the earlier behavior from the effective list

#### Scenario: Duplicate key warning
- **WHEN** a later behavior replaces an earlier behavior with the same `key`
- **THEN** the system SHALL emit a warning log for the override

### Requirement: Persisted Definition Sources
The system SHALL load persisted base API-added mocks and persisted template sets as mock definition sources.

#### Scenario: Persisted base API-added mocks are loaded
- **WHEN** the persistent store contains base API-added mock definitions
- **THEN** the system SHALL load those definitions into the active mock set

#### Scenario: Persisted template sets are loaded
- **WHEN** the persistent store contains one or more template sets
- **THEN** the system SHALL load every stored template-set definition into the active mock set

#### Scenario: Template set storage remains isolated
- **WHEN** multiple template sets exist in persistent storage
- **THEN** the system SHALL keep each set stored under its own set key

### Requirement: Admin Definition Validation
The system SHALL validate admin-submitted mock definitions before persisting them.

#### Scenario: Valid admin definitions are accepted
- **WHEN** an admin request submits mock definitions that satisfy the existing mock definition schema
- **THEN** the system SHALL accept those definitions for persistence

#### Scenario: Invalid admin definitions are rejected
- **WHEN** an admin request submits mock definitions that violate the existing mock definition schema
- **THEN** the system SHALL reject those definitions before writing them to persistent storage

### Requirement: Hot Reload Configuration
The system SHALL configure filesystem template hot reload using `HM_TEMPLATES_DIR_HOT_RELOAD`.

#### Scenario: Hot reload is enabled by default
- **WHEN** the server starts without `HM_TEMPLATES_DIR_HOT_RELOAD`
- **THEN** the system SHALL enable filesystem template hot reload

#### Scenario: Hot reload can be disabled
- **WHEN** the server starts with `HM_TEMPLATES_DIR_HOT_RELOAD=false`
- **THEN** the system SHALL keep filesystem-loaded mock definitions pinned to the loaded configuration until a later reload boundary

### Requirement: Filesystem Hot Reload Visibility
The system SHALL make filesystem template creations, edits, and deletions visible without restart when filesystem hot reload is enabled.

#### Scenario: Created filesystem template becomes active
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=true` and a YAML mock definition file is created under the templates directory
- **THEN** later mock requests SHALL evaluate the created definition without restarting the process

#### Scenario: Edited filesystem template replaces active behavior
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=true` and an existing YAML mock definition file is edited under the templates directory
- **THEN** later mock requests SHALL evaluate the edited definition without restarting the process

#### Scenario: Deleted filesystem template stops matching
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=true` and a YAML mock definition file is deleted under the templates directory
- **THEN** later mock requests SHALL stop evaluating definitions that only came from the deleted file without restarting the process

#### Scenario: Disabled hot reload ignores filesystem edits
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=false` and a YAML mock definition file is created, edited, or deleted under the templates directory
- **THEN** later mock requests SHALL continue using the previously loaded filesystem definitions until a later reload boundary

### Requirement: Binary File-Backed Body Loading
The system SHALL load binary file body content during mock definition loading for `reply_http` and `send_http` actions.

#### Scenario: Binary file path resolves relative to templates directory
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` or `send_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary file body is snapshotted at load time
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` or `send_http.body_from_binary_file`
- **THEN** the system SHALL store a stable byte snapshot of the file contents for that loaded configuration

#### Scenario: Missing binary file is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` or `send_http.body_from_binary_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary file outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` or `send_http.body_from_binary_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary filename is optional string metadata
- **WHEN** a loaded behavior defines `binary_file_name` on `reply_http` or `send_http`
- **THEN** the system SHALL accept the field only when it is a string
