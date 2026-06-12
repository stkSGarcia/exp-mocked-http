## MODIFIED Requirements

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
