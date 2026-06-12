## MODIFIED Requirements

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

## ADDED Requirements

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
