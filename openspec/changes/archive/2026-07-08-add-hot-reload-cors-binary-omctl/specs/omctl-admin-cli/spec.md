## ADDED Requirements

> Extends: template-set-storage/add-admin-api-template-storage
> Extends: api-template-persistence/add-admin-api-template-storage

### Requirement: omctl Push Command
The `omctl` CLI SHALL provide a `push` command that recursively loads YAML files from a local directory and uploads them to the remote admin API with `Content-Type: application/yaml`.

#### Scenario: Push base templates
- **GIVEN** `omctl push` is run without `--set-key`
- **AND** the selected directory contains YAML templates
- **WHEN** the command sends the upload request
- **THEN** it SHALL `POST` the YAML payload to `{url}/api/v1/templates`
- **AND** it SHALL send `Content-Type: application/yaml`

#### Scenario: Push named template set
- **GIVEN** `omctl push` is run with `--set-key alpha`
- **AND** the selected directory contains YAML templates
- **WHEN** the command sends the upload request
- **THEN** it SHALL `POST` the YAML payload to `{url}/api/v1/template_sets/alpha`
- **AND** it SHALL send `Content-Type: application/yaml`

#### Scenario: Push command defaults
- **GIVEN** `omctl push` is run without `--directory` or `--url`
- **WHEN** the command resolves flags
- **THEN** it SHALL use `./demo_templates` as the directory
- **AND** it SHALL use `http://localhost:9998` as the admin API base URL

### Requirement: omctl Delete Command
The `omctl` CLI SHALL provide a `delete` command that deletes a required named template set through the remote admin API and expects `204 No Content`. (adapts template-set-storage/add-admin-api-template-storage/template-set-deletion)

#### Scenario: Delete named template set
- **GIVEN** `omctl delete` is run with `--set-key alpha`
- **WHEN** the command sends the delete request
- **THEN** it SHALL send `DELETE {url}/api/v1/template_sets/alpha`
- **AND** it SHALL treat `204 No Content` as success

#### Scenario: Delete requires set key
- **GIVEN** `omctl delete` is run without `--set-key`
- **WHEN** the command validates flags
- **THEN** it SHALL fail before sending an HTTP request

#### Scenario: Delete command URL default
- **GIVEN** `omctl delete` is run without `--url`
- **WHEN** the command resolves flags
- **THEN** it SHALL use `http://localhost:9998` as the admin API base URL
