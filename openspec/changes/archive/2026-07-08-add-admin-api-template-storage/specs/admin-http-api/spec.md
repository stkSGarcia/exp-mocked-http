## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions

### Requirement: Admin Server Configuration
The system SHALL read admin HTTP server configuration from environment variables using the documented defaults when variables are absent.

#### Scenario: Defaults enable admin server
- **GIVEN** no admin HTTP environment variables are set
- **WHEN** the process starts
- **THEN** the admin server SHALL be enabled
- **AND** it SHALL listen on host `0.0.0.0` and port `9998`

#### Scenario: Environment overrides admin listener
- **GIVEN** `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_HOST`, or `HM_ADMIN_HTTP_PORT` are set
- **WHEN** the process starts
- **THEN** the system SHALL use those values for the admin server

#### Scenario: Admin server disabled
- **GIVEN** `HM_ADMIN_HTTP_ENABLED` disables the admin server
- **WHEN** the process starts
- **THEN** the system SHALL NOT open the admin HTTP listener

### Requirement: Admin Health Endpoint
The admin server SHALL expose `GET /api/v1/health` for liveness checks.

#### Scenario: Health succeeds
- **WHEN** a client requests `GET /api/v1/health`
- **THEN** the admin server SHALL return `200 OK`
- **AND** the response body SHALL be `{"status":"OK"}`

### Requirement: Admin Template Listing
The admin server SHALL expose `GET /api/v1/templates` to return every active mock definition.

#### Scenario: Active mocks are listed
- **GIVEN** filesystem-loaded mocks and API-added mocks are active
- **WHEN** a client requests `GET /api/v1/templates`
- **THEN** the admin server SHALL return `200 OK`
- **AND** the response body SHALL be a JSON array containing the active mock objects from both sources

### Requirement: Admin Template Upsert (adapts mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering/behavior-schema-validation)
The admin server SHALL expose `POST /api/v1/templates` to add or update base API-added mock definitions after validating the submitted definitions.

#### Scenario: Valid templates are accepted
- **GIVEN** the request body contains valid mock definitions
- **WHEN** a client requests `POST /api/v1/templates`
- **THEN** the admin server SHALL persist the submitted mocks
- **AND** it SHALL return `200 OK` with the submitted mocks in the response body

#### Scenario: Invalid templates are rejected
- **GIVEN** the request body contains invalid mock definitions
- **WHEN** a client requests `POST /api/v1/templates`
- **THEN** the admin server SHALL return `400 Bad Request` with an error message
- **AND** the system SHALL NOT apply the invalid update

### Requirement: Admin Base Template Deletion
The admin server SHALL expose deletion endpoints for API-persisted base templates without deleting filesystem mocks or template sets.

#### Scenario: Delete all API-added base templates
- **GIVEN** API-added base templates, filesystem mocks, and template sets exist
- **WHEN** a client requests `DELETE /api/v1/templates`
- **THEN** the admin server SHALL delete all base API-added mocks
- **AND** it SHALL leave filesystem mocks and template sets untouched
- **AND** it SHALL return `204 No Content`

#### Scenario: Delete one API-added base template
- **GIVEN** an API-persisted mock exists for `templateKey`
- **WHEN** a client requests `DELETE /api/v1/templates/{templateKey}`
- **THEN** the admin server SHALL delete only the API-persisted mock for `templateKey`
- **AND** it SHALL leave any filesystem mock with the same key untouched
- **AND** it SHALL return `204 No Content`

#### Scenario: Delete missing API-added base template
- **GIVEN** no API-persisted mock exists for `templateKey`
- **WHEN** a client requests `DELETE /api/v1/templates/{templateKey}`
- **THEN** the admin server SHALL return `404 Not Found`

