## MODIFIED Requirements

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

## ADDED Requirements

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
