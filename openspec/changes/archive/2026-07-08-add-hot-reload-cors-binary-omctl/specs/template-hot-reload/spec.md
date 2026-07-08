## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions
> Extends: api-template-persistence/add-admin-api-template-storage
> Extends: template-set-storage/add-admin-api-template-storage

### Requirement: Template Directory Hot Reload
The mock server SHALL read `HM_TEMPLATES_DIR_HOT_RELOAD` as a boolean runtime configuration value with default `true`, and SHALL make filesystem creations, edits, and deletions under the templates directory visible to later request handling automatically when the value is enabled.

#### Scenario: Filesystem edit becomes visible
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is enabled
- **AND** the server is running with a templates directory
- **WHEN** a template file is created, edited, or deleted under that directory
- **THEN** a later matching mock request SHALL reflect the changed templates directory without restarting the process

#### Scenario: Default enables hot reload
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is absent from the environment
- **WHEN** the server reads runtime configuration
- **THEN** template directory hot reload SHALL be enabled

### Requirement: Deferred Filesystem Reload
The mock server SHALL keep filesystem edits from affecting request handling until a later reload boundary when `HM_TEMPLATES_DIR_HOT_RELOAD` is disabled.

#### Scenario: Filesystem edit is held
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is disabled
- **AND** the server has loaded templates from the templates directory
- **WHEN** a template file is created, edited, or deleted under that directory
- **THEN** request handling SHALL continue using the previously loaded filesystem templates until a later reload boundary

### Requirement: Admin Mutation Visibility
The mock server SHALL keep mutating admin API requests visible within the normal bounded eventual-reload window regardless of `HM_TEMPLATES_DIR_HOT_RELOAD`. (adapts api-template-persistence/add-admin-api-template-storage/base-template-reload-visibility; adapts template-set-storage/add-admin-api-template-storage/template-set-reload-visibility)

#### Scenario: Admin mutation remains visible
- **GIVEN** `HM_TEMPLATES_DIR_HOT_RELOAD` is disabled
- **WHEN** a client successfully mutates base templates or a named template set through the admin API
- **THEN** later request handling after the normal eventual-reload window SHALL use the active mock set that includes the admin mutation
