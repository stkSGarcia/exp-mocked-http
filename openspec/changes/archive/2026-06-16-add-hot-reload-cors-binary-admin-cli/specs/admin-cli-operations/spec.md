## ADDED Requirements

### Requirement: Template Push Command
The system SHALL provide `omctl push` for uploading local YAML mock templates to the remote admin API.

#### Scenario: Push base template collection
- **GIVEN** a local template directory containing `.yaml` and `.yml` files at one or more directory depths
- **WHEN** `omctl push` runs without `--set-key`
- **THEN** the command SHALL recursively load all YAML files from the directory and `POST` the combined YAML payload to `{url}/api/v1/templates`
- **AND** the request SHALL use `Content-Type: application/yaml`

#### Scenario: Push named template set
- **GIVEN** a local template directory containing YAML templates and a set key
- **WHEN** `omctl push --set-key <setKey>` runs
- **THEN** the command SHALL recursively load all YAML files from the directory and `POST` the combined YAML payload to `{url}/api/v1/template_sets/{setKey}`
- **AND** the request SHALL use `Content-Type: application/yaml`

#### Scenario: Push defaults are applied
- **GIVEN** `omctl push` is run without `--directory` or `--url`
- **WHEN** the command builds the admin request
- **THEN** it SHALL read YAML templates from `./demo_templates`
- **AND** it SHALL use `http://localhost:9998` as the admin API base URL

### Requirement: Template Set Delete Command
The system SHALL provide `omctl delete` for deleting a named template set from the remote admin API.

#### Scenario: Delete named template set
- **GIVEN** a set key and an admin API base URL
- **WHEN** `omctl delete --set-key <setKey>` runs
- **THEN** the command SHALL send `DELETE {url}/api/v1/template_sets/{setKey}`
- **AND** the command SHALL treat `204 No Content` as success

#### Scenario: Delete requires set key
- **GIVEN** `omctl delete` is run without `--set-key`
- **WHEN** the command validates its arguments
- **THEN** it SHALL fail before sending an admin API request

#### Scenario: Delete default URL is applied
- **GIVEN** `omctl delete --set-key <setKey>` is run without `--url`
- **WHEN** the command builds the admin request
- **THEN** it SHALL use `http://localhost:9998` as the admin API base URL

