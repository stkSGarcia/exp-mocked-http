## ADDED Requirements

### Requirement: Admin YAML Template Payloads
The system SHALL accept YAML mock definition payloads for admin template replacement endpoints.

#### Scenario: Base templates accept YAML
- **WHEN** an admin client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and a valid YAML array of mock definitions
- **THEN** the system SHALL persist those definitions in the base API-added template collection and return `200 OK` with the submitted mock definitions

#### Scenario: Template set accepts YAML
- **WHEN** an admin client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and a valid YAML array of mock definitions
- **THEN** the system SHALL create or replace the full set for `{setKey}`, persist it separately from base templates, and return `200 OK` with the submitted mock definitions

#### Scenario: Invalid YAML base templates are rejected
- **WHEN** an admin client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and invalid mock definitions
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the invalid definitions

#### Scenario: Invalid YAML template set is rejected
- **WHEN** an admin client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and invalid mock definitions
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the invalid set
