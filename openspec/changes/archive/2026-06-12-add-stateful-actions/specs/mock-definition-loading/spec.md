## MODIFIED Requirements

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

## ADDED Requirements

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
