## ADDED Requirements

> Extends: `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`

### Requirement: Hot reload configuration
The system SHALL read `HM_TEMPLATES_DIR_HOT_RELOAD` as a boolean setting with a default value of `true`.

#### Scenario: Default hot reload setting
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is omitted
- **THEN** template-directory hot reload is enabled

#### Scenario: Invalid hot reload setting
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is not a supported boolean value
- **THEN** configuration loading fails with an error naming `HM_TEMPLATES_DIR_HOT_RELOAD`

### Requirement: Automatic filesystem visibility
When template-directory hot reload is enabled, the mock server SHALL detect creations, edits, and deletions under the configured templates directory and atomically install a newly compiled runtime without requiring a process restart.

#### Scenario: Created template becomes active
- **GIVEN** hot reload is enabled and the server is running
- **WHEN** a valid YAML template file is created under the templates directory
- **THEN** the definitions from that file become visible to later requests without restarting the server

#### Scenario: Edited template replaces behavior
- **GIVEN** hot reload is enabled and a filesystem behavior is active
- **WHEN** its YAML definition is edited
- **THEN** later requests use the edited behavior after the automatic reload window

#### Scenario: Deleted template is removed
- **GIVEN** hot reload is enabled and a filesystem behavior is active
- **WHEN** the YAML file defining it is deleted
- **THEN** later requests no longer match that behavior after the automatic reload window

### Requirement: Stable runtime during reload
The system SHALL continue serving the last successfully compiled runtime until a complete replacement runtime has been validated and installed.

#### Scenario: Invalid filesystem edit
- **GIVEN** a valid runtime is installed and hot reload is enabled
- **WHEN** a filesystem edit produces invalid YAML or an invalid mock definition
- **THEN** the server keeps serving the previous runtime
- **AND** no partially compiled filesystem state becomes visible

### Requirement: Disabled filesystem reload
When template-directory hot reload is disabled, filesystem changes SHALL NOT affect request handling until a later explicit reload boundary rebuilds the runtime.

#### Scenario: Filesystem edit remains deferred
- **GIVEN** hot reload is disabled and a filesystem behavior is active
- **WHEN** its source file is edited
- **THEN** later mock requests continue using the loaded behavior until a reload boundary

#### Scenario: Admin mutation remains visible
- **GIVEN** hot reload is disabled
- **WHEN** a valid admin API mutation succeeds
- **THEN** the mutation becomes visible within the normal admin mutation reload window
- **AND** the rebuilt runtime uses the filesystem state observed at that reload boundary
