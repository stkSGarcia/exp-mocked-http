## ADDED Requirements

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
