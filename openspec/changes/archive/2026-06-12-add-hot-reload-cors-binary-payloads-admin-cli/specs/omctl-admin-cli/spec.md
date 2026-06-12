## ADDED Requirements

### Requirement: CLI Entry Point
The system SHALL provide `omctl` as a command-line tool for remote admin operations.

#### Scenario: Command help is available
- **WHEN** a user runs `omctl --help`
- **THEN** the CLI SHALL show available commands including `push` and `delete`

#### Scenario: Unknown command fails
- **WHEN** a user runs `omctl` with an unsupported command
- **THEN** the CLI SHALL exit non-zero and print an error

### Requirement: Push Templates Command
The system SHALL allow users to push local YAML mock definitions to the admin API.

#### Scenario: Push defaults to demo templates and local admin URL
- **WHEN** a user runs `omctl push` without flags
- **THEN** the CLI SHALL load YAML templates from `./demo_templates` and POST them to `http://localhost:9998/api/v1/templates`

#### Scenario: Push directory flag overrides template directory
- **WHEN** a user runs `omctl push --directory ./fixtures`
- **THEN** the CLI SHALL load YAML templates recursively from `./fixtures`

#### Scenario: Push short directory flag is accepted
- **WHEN** a user runs `omctl push -d ./fixtures`
- **THEN** the CLI SHALL load YAML templates recursively from `./fixtures`

#### Scenario: Push URL flag overrides admin base URL
- **WHEN** a user runs `omctl push --url http://127.0.0.1:18080`
- **THEN** the CLI SHALL POST to `http://127.0.0.1:18080/api/v1/templates`

#### Scenario: Push short URL flag is accepted
- **WHEN** a user runs `omctl push -u http://127.0.0.1:18080`
- **THEN** the CLI SHALL POST to `http://127.0.0.1:18080/api/v1/templates`

#### Scenario: Push set key targets template set endpoint
- **WHEN** a user runs `omctl push --set-key smoke`
- **THEN** the CLI SHALL POST to `http://localhost:9998/api/v1/template_sets/smoke`

#### Scenario: Push short set key flag is accepted
- **WHEN** a user runs `omctl push -k smoke`
- **THEN** the CLI SHALL POST to `http://localhost:9998/api/v1/template_sets/smoke`

#### Scenario: Push sends YAML content type
- **WHEN** `omctl push` sends definitions to the admin API
- **THEN** the request SHALL include `Content-Type: application/yaml`

#### Scenario: Push loads YAML recursively
- **WHEN** the configured directory contains `.yaml` and `.yml` files at multiple directory depths
- **THEN** the CLI SHALL include definitions from every YAML file in the submitted payload

#### Scenario: Push ignores non-YAML files
- **WHEN** the configured directory contains files without `.yaml` or `.yml` extensions
- **THEN** the CLI SHALL ignore those files

#### Scenario: Push expects success
- **WHEN** the admin API returns `200 OK` to a push request
- **THEN** the CLI SHALL exit successfully

#### Scenario: Push failure exits non-zero
- **WHEN** the admin API returns a non-`200` response or the request fails
- **THEN** the CLI SHALL exit non-zero and print the failure

### Requirement: Delete Template Set Command
The system SHALL allow users to delete a named template set through the admin API.

#### Scenario: Delete requires set key
- **WHEN** a user runs `omctl delete` without `--set-key` or `-k`
- **THEN** the CLI SHALL exit non-zero and report the missing required set key

#### Scenario: Delete defaults to local admin URL
- **WHEN** a user runs `omctl delete --set-key smoke` without `--url`
- **THEN** the CLI SHALL send `DELETE http://localhost:9998/api/v1/template_sets/smoke`

#### Scenario: Delete URL flag overrides admin base URL
- **WHEN** a user runs `omctl delete --url http://127.0.0.1:18080 --set-key smoke`
- **THEN** the CLI SHALL send `DELETE http://127.0.0.1:18080/api/v1/template_sets/smoke`

#### Scenario: Delete short flags are accepted
- **WHEN** a user runs `omctl delete -u http://127.0.0.1:18080 -k smoke`
- **THEN** the CLI SHALL send `DELETE http://127.0.0.1:18080/api/v1/template_sets/smoke`

#### Scenario: Delete expects no content
- **WHEN** the admin API returns `204 No Content` to a delete request
- **THEN** the CLI SHALL exit successfully

#### Scenario: Delete failure exits non-zero
- **WHEN** the admin API returns a response other than `204 No Content` or the request fails
- **THEN** the CLI SHALL exit non-zero and print the failure
