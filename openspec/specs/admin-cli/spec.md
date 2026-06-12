## Purpose

Define command-line admin operations for managing remote mock template collections.

## Requirements

### Requirement: Admin CLI Entry Point
The system SHALL provide an `omctl` command-line tool for remote admin operations.

#### Scenario: CLI help is available
- **WHEN** a user invokes `omctl --help`
- **THEN** the system SHALL display help for the available admin operations

### Requirement: Push Templates
The CLI SHALL upload local YAML template definitions to the admin API.

#### Scenario: Push base templates with defaults
- **WHEN** a user invokes `omctl push` without flags from a directory containing `./demo_templates`
- **THEN** the CLI SHALL recursively load YAML files from `./demo_templates`
- **AND** it SHALL send `POST http://localhost:9998/api/v1/templates` with `Content-Type: application/yaml`

#### Scenario: Push base templates from custom directory and URL
- **WHEN** a user invokes `omctl push --directory ./templates --url http://admin.test`
- **THEN** the CLI SHALL recursively load YAML files from `./templates`
- **AND** it SHALL send `POST http://admin.test/api/v1/templates` with `Content-Type: application/yaml`

#### Scenario: Push named template set
- **WHEN** a user invokes `omctl push --set-key smoke`
- **THEN** the CLI SHALL send `POST http://localhost:9998/api/v1/template_sets/smoke` with `Content-Type: application/yaml`

#### Scenario: Push uses short flags
- **WHEN** a user invokes `omctl push -d ./templates -u http://admin.test -k smoke`
- **THEN** the CLI SHALL use `./templates` as the source directory, `http://admin.test` as the admin API base URL, and `smoke` as the template set key

### Requirement: Delete Template Set
The CLI SHALL delete named template sets through the admin API.

#### Scenario: Delete template set
- **WHEN** a user invokes `omctl delete --set-key smoke`
- **THEN** the CLI SHALL send `DELETE http://localhost:9998/api/v1/template_sets/smoke`
- **AND** it SHALL treat `204 No Content` as success

#### Scenario: Delete requires set key
- **WHEN** a user invokes `omctl delete` without `--set-key`
- **THEN** the CLI SHALL reject the command before sending an admin API request

#### Scenario: Delete uses short flags
- **WHEN** a user invokes `omctl delete -u http://admin.test -k smoke`
- **THEN** the CLI SHALL send `DELETE http://admin.test/api/v1/template_sets/smoke`
