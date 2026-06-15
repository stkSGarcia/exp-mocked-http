## Purpose

Define the admin HTTP server configuration and management endpoints for runtime mock definitions.
## Requirements
### Requirement: Admin Server Configuration
The system SHALL read admin HTTP server configuration from environment variables using documented defaults when variables are absent.

#### Scenario: Admin configuration defaults are used
- **WHEN** the server starts without `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, or `HM_ADMIN_HTTP_HOST`
- **THEN** the system SHALL enable the admin server, bind it to `0.0.0.0`, and listen on port `9998`

#### Scenario: Admin configuration overrides are used
- **WHEN** the server starts with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` set
- **THEN** the system SHALL use those values for admin enablement, admin bind address, and admin port

#### Scenario: Admin server disabled
- **WHEN** `HM_ADMIN_HTTP_ENABLED` is `false`
- **THEN** the system SHALL NOT start the admin HTTP server

### Requirement: Admin Health Endpoint
The system SHALL expose a health endpoint on the admin server.

#### Scenario: Health check succeeds
- **WHEN** a client sends `GET /api/v1/health` to the admin server
- **THEN** the system SHALL return `200 OK` with JSON body `{"status":"OK"}`

### Requirement: Admin Template Listing
The system SHALL expose the active mock definition collection through the admin server.

#### Scenario: Active templates are listed
- **WHEN** a client sends `GET /api/v1/templates`
- **THEN** the system SHALL return `200 OK` with a JSON array containing filesystem-loaded mock definitions and API-added mock definitions active at the time of the request

### Requirement: Admin Base Template Upsert
The system SHALL allow clients to add or update base API-added mock definitions using JSON or YAML payloads.

#### Scenario: Base templates are added
- **WHEN** a client sends `POST /api/v1/templates` with a JSON array of valid mock definitions
- **THEN** the system SHALL persist the submitted definitions as base API-added mocks
- **AND** the system SHALL return `200 OK` with the submitted mock definitions as JSON

#### Scenario: YAML base templates are added
- **WHEN** a client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and a YAML array of valid mock definitions
- **THEN** the system SHALL persist the submitted definitions as base API-added mocks
- **AND** the system SHALL return `200 OK` with the submitted mock definitions as JSON

#### Scenario: Base templates are updated
- **WHEN** a client sends `POST /api/v1/templates` with a valid mock definition whose key already exists in base API-added storage
- **THEN** the system SHALL replace the stored base API-added mock for that key
- **AND** the updated mock SHALL be visible to subsequent requests within the reload window

#### Scenario: Invalid base template is rejected
- **WHEN** a client sends `POST /api/v1/templates` with a mock definition that fails validation
- **THEN** the system SHALL return `400 Bad Request` with an error message
- **AND** the system SHALL NOT change the active mock set

#### Scenario: Invalid YAML base template payload is rejected
- **WHEN** a client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and a payload that cannot be parsed as a valid YAML array of mock definitions
- **THEN** the system SHALL return `400 Bad Request` with an error message
- **AND** the system SHALL NOT change the active mock set

### Requirement: Admin Base Template Deletion
The system SHALL allow clients to delete base API-added mock definitions without deleting filesystem mocks or template sets.

#### Scenario: All base API templates are deleted
- **WHEN** a client sends `DELETE /api/v1/templates`
- **THEN** the system SHALL delete all base API-added mocks
- **AND** the system SHALL leave filesystem-loaded mocks and template sets unchanged
- **AND** the system SHALL return `204 No Content`

#### Scenario: One base API template is deleted
- **WHEN** a client sends `DELETE /api/v1/templates/{templateKey}` for a key present in base API-added storage
- **THEN** the system SHALL delete only that base API-added mock
- **AND** the system SHALL leave any filesystem-loaded mock with the same key unchanged
- **AND** the system SHALL return `204 No Content`

#### Scenario: Missing base API template delete returns not found
- **WHEN** a client sends `DELETE /api/v1/templates/{templateKey}` for a key absent from base API-added storage
- **THEN** the system SHALL return `404 Not Found`

### Requirement: Admin Template Sets
The system SHALL allow clients to manage named groups of persisted mock definitions separately from the base template collection using JSON or YAML payloads.

#### Scenario: Template set is replaced
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with a JSON array of valid mock definitions
- **THEN** the system SHALL create or replace the full template set for `{setKey}`
- **AND** the system SHALL persist that set separately from base API-added mocks and other sets
- **AND** the system SHALL return `200 OK` with the submitted mock definitions as JSON

#### Scenario: YAML template set is replaced
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and a YAML array of valid mock definitions
- **THEN** the system SHALL create or replace the full template set for `{setKey}`
- **AND** the system SHALL persist that set separately from base API-added mocks and other sets
- **AND** the system SHALL return `200 OK` with the submitted mock definitions as JSON

#### Scenario: Template set validation failure is rejected
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with a mock definition that fails validation
- **THEN** the system SHALL return `400 Bad Request` with an error message
- **AND** the system SHALL NOT change the active mock set

#### Scenario: YAML template set parse failure is rejected
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and a payload that cannot be parsed as a valid YAML array of mock definitions
- **THEN** the system SHALL return `400 Bad Request` with an error message
- **AND** the system SHALL NOT change the active mock set

#### Scenario: Template set is deleted
- **WHEN** a client sends `DELETE /api/v1/template_sets/{setKey}` for an existing template set
- **THEN** the system SHALL delete the entire set for `{setKey}`
- **AND** the system SHALL leave all other sets unchanged
- **AND** the system SHALL return `204 No Content`

#### Scenario: Missing template set delete is idempotent
- **WHEN** a client sends `DELETE /api/v1/template_sets/{setKey}` for a set that does not exist
- **THEN** the system SHALL return `204 No Content`

### Requirement: Admin Mock Evaluation Endpoint
The system SHALL expose `POST /api/v1/evaluate` on the admin HTTP server for dry-run evaluation of a single mock definition.

#### Scenario: Evaluation endpoint returns JSON
- **WHEN** a client sends a valid JSON evaluation request to `POST /api/v1/evaluate`
- **THEN** the system SHALL return `200 OK` with a JSON evaluation result

#### Scenario: Evaluation validation failure is rejected
- **WHEN** a client sends an invalid evaluation request to `POST /api/v1/evaluate`
- **THEN** the system SHALL return `400 Bad Request` with an error message

#### Scenario: Evaluation endpoint does not persist mock
- **WHEN** a client sends a valid evaluation request to `POST /api/v1/evaluate`
- **THEN** the submitted mock SHALL NOT be added to base templates, template sets, filesystem mocks, or the active mock collection

#### Scenario: Evaluation endpoint does not execute side effects
- **WHEN** a client sends a valid evaluation request to `POST /api/v1/evaluate`
- **THEN** the admin server SHALL only compute and return the rendered result without executing mock side effects
