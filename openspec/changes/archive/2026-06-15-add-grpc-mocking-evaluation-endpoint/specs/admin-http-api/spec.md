## ADDED Requirements

### Requirement: Admin Dry-Run Evaluation Endpoint
The system SHALL expose an admin HTTP endpoint for evaluating one mock definition against simulated channel context without persisting the mock or executing side effects.

#### Scenario: Evaluation endpoint accepts JSON
- **WHEN** an admin client sends `POST /api/v1/evaluate` with a valid JSON evaluation request
- **THEN** the system SHALL return `200 OK` with the dry-run evaluation response

#### Scenario: Evaluation endpoint rejects invalid JSON
- **WHEN** an admin client sends `POST /api/v1/evaluate` with malformed JSON
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Evaluation endpoint rejects validation failures
- **WHEN** an admin client sends `POST /api/v1/evaluate` with a mock or context that fails evaluation validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the mock definition

#### Scenario: Evaluation endpoint has no persistence side effect
- **WHEN** `POST /api/v1/evaluate` succeeds
- **THEN** later `GET /api/v1/templates` responses SHALL NOT include the evaluated mock unless it was already active from another source
