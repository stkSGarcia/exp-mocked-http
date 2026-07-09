## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions

### Requirement: CLI Push Command
The `omctl` CLI SHALL provide a `push` command that uploads local YAML templates to the remote admin API.

#### Scenario: Push loads YAML recursively
- **WHEN** `omctl push` runs with a template directory
- **THEN** it loads all YAML files from that directory recursively

#### Scenario: Push uses default directory and URL
- **WHEN** `omctl push` runs without `--directory` or `--url`
- **THEN** it uses `./demo_templates` and `http://localhost:9998`

#### Scenario: Push base templates
- **WHEN** `omctl push` runs without `--set-key`
- **THEN** it sends `POST {url}/api/v1/templates` with `Content-Type: application/yaml`

#### Scenario: Push named template set
- **WHEN** `omctl push` runs with `--set-key alpha`
- **THEN** it sends `POST {url}/api/v1/template_sets/alpha` with `Content-Type: application/yaml`

### Requirement: CLI Delete Command
The `omctl` CLI SHALL provide a `delete` command that deletes a named remote template set through the admin API.

#### Scenario: Delete requires set key
- **WHEN** `omctl delete` runs without `--set-key`
- **THEN** it fails before sending an admin API request

#### Scenario: Delete uses default URL
- **WHEN** `omctl delete --set-key alpha` runs without `--url`
- **THEN** it sends `DELETE http://localhost:9998/api/v1/template_sets/alpha`

#### Scenario: Delete expects no content
- **WHEN** `omctl delete --set-key alpha` receives `204 No Content`
- **THEN** it treats the delete operation as successful

### Requirement: CLI Flag Aliases
The `omctl` CLI SHALL support documented short aliases for admin operation flags.

#### Scenario: Push short aliases
- **WHEN** `omctl push -d ./templates -u http://admin.test -k alpha` runs
- **THEN** it behaves the same as `omctl push --directory ./templates --url http://admin.test --set-key alpha`

#### Scenario: Delete short aliases
- **WHEN** `omctl delete -u http://admin.test -k alpha` runs
- **THEN** it behaves the same as `omctl delete --url http://admin.test --set-key alpha`
