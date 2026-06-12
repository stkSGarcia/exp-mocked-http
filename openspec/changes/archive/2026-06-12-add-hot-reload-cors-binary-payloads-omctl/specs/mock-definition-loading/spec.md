## ADDED Requirements

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
