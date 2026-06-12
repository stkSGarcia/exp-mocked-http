## ADDED Requirements

> Extends: `admin-template-management/add-admin-api-template-persistence`

### Requirement: omctl command entry point
The project SHALL install an `omctl` command with `push` and `delete` subcommands and SHALL return a non-zero exit status for invalid arguments or unsuccessful HTTP operations.

#### Scenario: Help lists admin operations
- **WHEN** a user invokes `omctl --help`
- **THEN** the output lists the `push` and `delete` subcommands

#### Scenario: Remote operation fails
- **WHEN** an `omctl` request cannot be completed or receives an unexpected status
- **THEN** the command reports the failure
- **AND** exits with a non-zero status

### Requirement: Recursive template push
The `omctl push` command SHALL recursively load `.yaml` and `.yml` files from `--directory`/`-d`, combine their mock definitions, and send them with `Content-Type: application/yaml`.

#### Scenario: Push defaults
- **WHEN** `omctl push` is invoked without flags
- **THEN** it loads YAML files recursively from `./demo_templates`
- **AND** sends a `POST` request to `http://localhost:9998/api/v1/templates`

#### Scenario: Push base templates to configured server
- **GIVEN** `--directory` and `--url` are provided and `--set-key` is omitted
- **WHEN** `omctl push` runs
- **THEN** it posts the combined YAML payload to `{url}/api/v1/templates`
- **AND** sends `Content-Type: application/yaml`

#### Scenario: Push named template set
- **GIVEN** `--set-key`/`-k` is `checkout`
- **WHEN** `omctl push` runs
- **THEN** it posts the combined YAML payload to `{url}/api/v1/template_sets/checkout`

#### Scenario: Invalid local YAML prevents upload
- **GIVEN** any discovered YAML file is invalid or does not contain mock objects
- **WHEN** `omctl push` runs
- **THEN** it exits with a non-zero status
- **AND** sends no admin mutation request

### Requirement: YAML admin payload acceptance
The admin server SHALL accept `application/yaml` mock object or mock array payloads on `POST /api/v1/templates` and `POST /api/v1/template_sets/{setKey}` while preserving the existing validation and atomic mutation behavior.

#### Scenario: YAML base template payload
- **WHEN** a valid YAML mock collection is posted to `/api/v1/templates`
- **THEN** the server applies it using the existing base-template mutation semantics

#### Scenario: Invalid YAML set payload
- **GIVEN** the active runtime and persisted collections are valid
- **WHEN** invalid YAML is posted to `/api/v1/template_sets/{setKey}`
- **THEN** the server returns `400 Bad Request`
- **AND** the active runtime and persisted set remain unchanged

### Requirement: Named template set deletion
The `omctl delete` command SHALL require `--set-key`/`-k`, default `--url`/`-u` to `http://localhost:9998`, and send `DELETE {url}/api/v1/template_sets/{set-key}` expecting `204 No Content`. (adapts `admin-template-management/add-admin-api-template-persistence/named-template-set-deletion`)

#### Scenario: Delete named set
- **GIVEN** `--set-key` is `checkout`
- **WHEN** `omctl delete` runs
- **THEN** it sends `DELETE` to `{url}/api/v1/template_sets/checkout`
- **AND** treats `204 No Content` as success

#### Scenario: Missing set key
- **WHEN** `omctl delete` is invoked without `--set-key`
- **THEN** argument parsing fails without sending an HTTP request

