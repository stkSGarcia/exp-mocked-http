## ADDED Requirements

> Extends: mock-definition-loading

### Requirement: Template Directory Hot Reload Configuration
The system SHALL control visibility of filesystem edits under the templates directory with `HM_TEMPLATES_DIR_HOT_RELOAD`.

#### Scenario: Hot reload default is enabled
- **GIVEN** the server starts without `HM_TEMPLATES_DIR_HOT_RELOAD`
- **WHEN** runtime configuration is read
- **THEN** the system SHALL behave as though `HM_TEMPLATES_DIR_HOT_RELOAD` is `true`

#### Scenario: Filesystem edits are visible when enabled
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is `true`
- **WHEN** a YAML template file under the templates directory is created, edited, or deleted
- **THEN** subsequent request handling SHALL observe the updated loaded configuration without restarting the server

#### Scenario: Filesystem edits are isolated when disabled
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is `false`
- **WHEN** a YAML template file under the templates directory is created, edited, or deleted after startup
- **THEN** request handling SHALL continue using the previously loaded configuration until a later reload boundary

#### Scenario: Admin mutations still reload
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is `false`
- **WHEN** the admin API mutates templates or template sets
- **THEN** the mutation SHALL still become visible within the normal eventual-reload window

### Requirement: CORS Configuration
The system SHALL read `HM_CORS_ENABLED` to control global CORS behavior for the mock HTTP server.

#### Scenario: CORS default is disabled
- **GIVEN** the server starts without `HM_CORS_ENABLED`
- **WHEN** runtime configuration is read
- **THEN** the system SHALL behave as though `HM_CORS_ENABLED` is `false`

#### Scenario: CORS can be enabled
- **GIVEN** the server starts with `HM_CORS_ENABLED=true`
- **WHEN** runtime configuration is read
- **THEN** the system SHALL enable global CORS response behavior for mock HTTP responses

### Requirement: Binary File Payload Loading
The system SHALL validate and snapshot binary file payloads declared by `reply_http.body_from_binary_file` and `send_http.body_from_binary_file`.

#### Scenario: Binary reply file path resolves relative to templates directory
- **GIVEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **WHEN** the behavior is loaded
- **THEN** the system SHALL resolve the binary file path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary reply file is snapshotted
- **GIVEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **WHEN** the behavior is loaded
- **THEN** the system SHALL store a stable binary snapshot for the loaded configuration

#### Scenario: Binary send file path resolves relative to templates directory
- **GIVEN** a loaded behavior defines `send_http.body_from_binary_file`
- **WHEN** the behavior is loaded
- **THEN** the system SHALL resolve the binary file path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary send file is snapshotted
- **GIVEN** a loaded behavior defines `send_http.body_from_binary_file`
- **WHEN** the behavior is loaded
- **THEN** the system SHALL store a stable binary snapshot for the loaded configuration

#### Scenario: Missing binary file is rejected
- **GIVEN** a loaded behavior defines `reply_http.body_from_binary_file` or `send_http.body_from_binary_file`
- **WHEN** the resolved binary file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary file outside templates directory is rejected
- **GIVEN** a loaded behavior defines `reply_http.body_from_binary_file` or `send_http.body_from_binary_file`
- **WHEN** the resolved binary file path is outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

