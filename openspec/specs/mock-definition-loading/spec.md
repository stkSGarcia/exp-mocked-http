## Purpose

Define how YAML mock definitions are discovered, validated, ordered, and merged before serving requests.

## Requirements

### Requirement: Server Configuration
The system SHALL read its runtime configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Default configuration is used
- **WHEN** the server starts without `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, or `HM_LOG_LEVEL`
- **THEN** it SHALL scan `./templates`, listen on port `9999`, bind to `0.0.0.0`, and use log level `info`

#### Scenario: Environment overrides configuration
- **WHEN** the server starts with `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, and `HM_LOG_LEVEL` set
- **THEN** it SHALL use those values for template discovery, HTTP bind address, HTTP port, and log filtering

### Requirement: Recursive YAML Discovery
The system SHALL recursively scan `HM_TEMPLATES_DIR` and load every file ending in `.yaml` or `.yml`.

#### Scenario: Nested YAML files are loaded
- **WHEN** the templates directory contains YAML files at multiple directory depths
- **THEN** the system SHALL load each `.yaml` and `.yml` file into the mock definition stream

#### Scenario: Non-YAML files are ignored
- **WHEN** the templates directory contains files without `.yaml` or `.yml` extensions
- **THEN** the system SHALL ignore those files during mock loading

### Requirement: Behavior Schema Validation
The system SHALL validate loaded mock behaviors before serving requests.

#### Scenario: Missing key is rejected
- **WHEN** a loaded behavior omits `key`
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Empty key is rejected
- **WHEN** a loaded behavior has `key` set to an empty string or non-string value
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Kind defaults to Behavior
- **WHEN** a loaded behavior omits `kind`
- **THEN** the system SHALL treat `kind` as `Behavior`

#### Scenario: Multiple HTTP replies are rejected
- **WHEN** a loaded behavior contains more than one `reply_http` action
- **THEN** the system SHALL reject that behavior as invalid

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
