## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions

### Requirement: Hot Reload Configuration
The system SHALL read `HM_TEMPLATES_DIR_HOT_RELOAD` from runtime configuration using a default of `true`.

#### Scenario: Default hot reload enabled
- **WHEN** runtime configuration is loaded without `HM_TEMPLATES_DIR_HOT_RELOAD`
- **THEN** template directory hot reload is enabled

#### Scenario: Hot reload disabled by environment
- **WHEN** runtime configuration is loaded with `HM_TEMPLATES_DIR_HOT_RELOAD=false`
- **THEN** template directory hot reload is disabled

### Requirement: Enabled Filesystem Reload
The mock HTTP server SHALL make filesystem creations, edits, and deletions under the templates directory visible to request handling without restart when template directory hot reload is enabled.

#### Scenario: Created file becomes visible
- **GIVEN** template directory hot reload is enabled
- **WHEN** a YAML file is created under the templates directory
- **THEN** later matching mock HTTP requests use definitions from that file without restarting the server

#### Scenario: Edited file becomes visible
- **GIVEN** template directory hot reload is enabled
- **WHEN** a YAML file under the templates directory is edited
- **THEN** later matching mock HTTP requests use the edited definition without restarting the server

#### Scenario: Deleted file stops matching
- **GIVEN** template directory hot reload is enabled
- **WHEN** a YAML file under the templates directory is deleted
- **THEN** later mock HTTP requests no longer use definitions from that deleted file

### Requirement: Disabled Filesystem Snapshot
The mock HTTP server SHALL keep using the loaded filesystem template snapshot until a later reload boundary when template directory hot reload is disabled.

#### Scenario: Filesystem edit ignored while disabled
- **GIVEN** template directory hot reload is disabled
- **WHEN** a YAML file under the templates directory is created, edited, or deleted
- **THEN** mock HTTP request handling continues using the previously loaded filesystem definitions

### Requirement: Admin Mutation Visibility
The system SHALL keep admin API mutations visible within the normal eventual-reload window regardless of template directory hot reload configuration.

#### Scenario: Admin update remains visible with hot reload disabled
- **GIVEN** template directory hot reload is disabled
- **WHEN** the admin API updates the base templates or a template set
- **THEN** later mock HTTP requests observe the admin mutation after the normal reload boundary
