## ADDED Requirements

### Requirement: Admin CLI Entry Point
The system SHALL provide an `omctl` CLI entry point for remote admin operations.

#### Scenario: CLI help is available
- **WHEN** a user runs `omctl --help`
- **THEN** the CLI SHALL describe the available `push` and `delete` subcommands

### Requirement: Admin CLI Push
The system SHALL allow users to upload local YAML templates to the admin API.

#### Scenario: Base templates are pushed
- **WHEN** a user runs `omctl push` without `--set-key`
- **THEN** the CLI SHALL recursively load YAML files from `./demo_templates` and POST the combined YAML payload to `http://localhost:9998/api/v1/templates` with `Content-Type: application/yaml`

#### Scenario: Directory flag selects template source
- **WHEN** a user runs `omctl push --directory <path>`
- **THEN** the CLI SHALL recursively load `.yaml` and `.yml` files from `<path>`

#### Scenario: URL flag selects admin base URL
- **WHEN** a user runs `omctl push --url <url>`
- **THEN** the CLI SHALL send the request to `<url>` as the admin API base URL

#### Scenario: Template set is pushed
- **WHEN** a user runs `omctl push --set-key <setKey>`
- **THEN** the CLI SHALL POST the combined YAML payload to `{url}/api/v1/template_sets/{setKey}` with `Content-Type: application/yaml`

### Requirement: Admin CLI Delete
The system SHALL allow users to delete a named template set through the admin API.

#### Scenario: Template set is deleted
- **WHEN** a user runs `omctl delete --set-key <setKey>`
- **THEN** the CLI SHALL send `DELETE http://localhost:9998/api/v1/template_sets/{setKey}` and treat `204 No Content` as success

#### Scenario: Delete URL flag selects admin base URL
- **WHEN** a user runs `omctl delete --url <url> --set-key <setKey>`
- **THEN** the CLI SHALL send the DELETE request to `<url>/api/v1/template_sets/{setKey}`

#### Scenario: Delete requires set key
- **WHEN** a user runs `omctl delete` without `--set-key`
- **THEN** the CLI SHALL fail argument parsing without sending an admin request
