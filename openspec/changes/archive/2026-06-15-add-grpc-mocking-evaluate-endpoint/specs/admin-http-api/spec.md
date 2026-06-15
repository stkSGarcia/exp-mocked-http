## ADDED Requirements

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
