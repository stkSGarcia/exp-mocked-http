# omctl

## Purpose

TBD

## Requirements

### Requirement: omctl push uploads templates to admin API
`omctl push` SHALL load all `.yaml` and `.yml` files recursively from a local directory and POST their combined contents to the admin API as YAML. When `--set-key` is omitted, the payload is POSTed to `{url}/api/v1/templates`. When `--set-key` is provided, the payload is POSTed to `{url}/api/v1/template_sets/{set-key}`.

#### Scenario: Push without set-key posts to base templates endpoint
- **WHEN** `omctl push --directory ./my-templates --url http://localhost:9998` is run
- **THEN** a POST is made to `http://localhost:9998/api/v1/templates` with `Content-Type: application/yaml`

#### Scenario: Push with set-key posts to template sets endpoint
- **WHEN** `omctl push --directory ./my-templates --url http://localhost:9998 --set-key staging`
- **THEN** a POST is made to `http://localhost:9998/api/v1/template_sets/staging`

#### Scenario: Default directory is ./demo_templates
- **WHEN** `omctl push` is run with no `--directory` flag
- **THEN** the tool loads YAML files from `./demo_templates`

#### Scenario: Default URL is http://localhost:9998
- **WHEN** `omctl push` is run with no `--url` flag
- **THEN** the tool targets `http://localhost:9998`

### Requirement: omctl push flag aliases
`omctl push` SHALL accept short flag aliases: `-d` for `--directory`, `-u` for `--url`, `-k` for `--set-key`.

#### Scenario: Short flags accepted
- **WHEN** `omctl push -d ./templates -u http://host:9998 -k mykey` is run
- **THEN** the tool behaves identically to the long-form flags

### Requirement: omctl delete removes a named template set
`omctl delete` SHALL send `DELETE {url}/api/v1/template_sets/{set-key}` and expect a `204 No Content` response. The `--set-key` flag is required.

#### Scenario: Delete sends DELETE to correct endpoint
- **WHEN** `omctl delete --url http://localhost:9998 --set-key staging`
- **THEN** a DELETE request is made to `http://localhost:9998/api/v1/template_sets/staging`

#### Scenario: Missing set-key exits with error
- **WHEN** `omctl delete` is run without `--set-key`
- **THEN** the tool exits with a non-zero status and prints a usage error

#### Scenario: Default URL applies to delete
- **WHEN** `omctl delete --set-key staging` is run with no `--url` flag
- **THEN** the tool targets `http://localhost:9998`

### Requirement: omctl exits non-zero on HTTP error
When the admin API returns an unexpected status code or the request fails (connection refused, timeout), `omctl` SHALL print an error message to stderr and exit with a non-zero status code.

#### Scenario: Server error causes non-zero exit
- **WHEN** the admin API returns `500 Internal Server Error`
- **THEN** `omctl` prints an error and exits with a non-zero status

#### Scenario: Connection failure causes non-zero exit
- **WHEN** the admin API is unreachable
- **THEN** `omctl` prints an error and exits with a non-zero status

### Requirement: omctl silent on success
When an operation succeeds, `omctl` SHALL produce no output and exit with status `0`.

#### Scenario: Successful push produces no output
- **WHEN** `omctl push` completes with a 2xx response
- **THEN** nothing is printed to stdout or stderr and exit status is 0

#### Scenario: Successful delete produces no output
- **WHEN** `omctl delete` receives a `204 No Content` response
- **THEN** nothing is printed and exit status is 0
