## ADDED Requirements

### Requirement: YAML Admin Template Mutation Payloads
The admin server SHALL accept YAML mock-definition payloads for template mutation endpoints.

#### Scenario: Base API templates accept YAML
- **WHEN** a client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and a YAML array of mock definitions
- **THEN** the system SHALL validate the submitted definitions, persist them in the base API-added mock collection, and return `200 OK` with the submitted mocks

#### Scenario: Template set accepts YAML
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and a YAML array of mock definitions
- **THEN** the system SHALL validate the submitted definitions, replace the full persisted set for `{setKey}`, and return `200 OK` with the submitted mocks

#### Scenario: Invalid YAML base API templates are rejected
- **WHEN** a client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and mock definitions that fail parsing or validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the submitted definitions

#### Scenario: Invalid YAML template set is rejected
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and mock definitions that fail parsing or validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT replace the persisted set
