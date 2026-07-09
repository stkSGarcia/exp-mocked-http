## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions

### Requirement: Admin Server Configuration
The system SHALL run an admin HTTP server when enabled by environment configuration.

#### Scenario: Admin server uses defaults
- **GIVEN** `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` are absent
- **WHEN** the system starts
- **THEN** the admin HTTP server SHALL listen on `0.0.0.0:9998`

#### Scenario: Admin server can be disabled
- **GIVEN** `HM_ADMIN_HTTP_ENABLED` is `false`
- **WHEN** the system starts
- **THEN** the admin HTTP server SHALL NOT listen for requests

### Requirement: Health Endpoint
The admin HTTP server SHALL expose `GET /api/v1/health`.

#### Scenario: Health reports OK
- **WHEN** a client requests `GET /api/v1/health`
- **THEN** the admin HTTP server SHALL return `200 OK`
- **AND** the response body SHALL be `{"status":"OK"}`

### Requirement: Template Collection Listing
The admin HTTP server SHALL expose `GET /api/v1/templates` to return every active mock definition.

#### Scenario: Active templates include all loaded sources
- **GIVEN** the active mock set contains filesystem-loaded mocks and API-added mocks
- **WHEN** a client requests `GET /api/v1/templates`
- **THEN** the admin HTTP server SHALL return `200 OK`
- **AND** the response body SHALL be a JSON array containing the active mock objects from both sources

### Requirement: Template Collection Upsert
The admin HTTP server SHALL expose `POST /api/v1/templates` to add or update API-submitted base mock definitions.

#### Scenario: Valid submitted templates are persisted
- **GIVEN** the request body contains valid mock definitions
- **WHEN** a client posts to `POST /api/v1/templates`
- **THEN** the system SHALL add or update the submitted mocks in persistent base-template storage
- **AND** the admin HTTP server SHALL return `200 OK` with the submitted mocks

#### Scenario: Invalid submitted templates are rejected
- **GIVEN** the request body contains invalid mock definitions
- **WHEN** a client posts to `POST /api/v1/templates`
- **THEN** the admin HTTP server SHALL return `400 Bad Request` with an error message
- **AND** the system SHALL NOT persist the invalid mocks

### Requirement: Template Collection Deletion
The admin HTTP server SHALL expose delete endpoints for API-persisted base mocks.

#### Scenario: Delete all API-added base templates
- **GIVEN** API-added base mocks, filesystem mocks, and template sets exist
- **WHEN** a client requests `DELETE /api/v1/templates`
- **THEN** the system SHALL delete all API-added base mocks
- **AND** the system SHALL leave filesystem mocks and template sets untouched
- **AND** the admin HTTP server SHALL return `204 No Content`

#### Scenario: Delete one API-added base template
- **GIVEN** an API-persisted base mock exists for `templateKey`
- **WHEN** a client requests `DELETE /api/v1/templates/{templateKey}`
- **THEN** the system SHALL delete only the API-persisted base mock for `templateKey`
- **AND** the system SHALL leave any filesystem mock with the same key untouched
- **AND** the admin HTTP server SHALL return `204 No Content`

#### Scenario: Delete missing API-added base template
- **GIVEN** no API-persisted base mock exists for `templateKey`
- **WHEN** a client requests `DELETE /api/v1/templates/{templateKey}`
- **THEN** the admin HTTP server SHALL return `404 Not Found`

### Requirement: Template Set Management
The admin HTTP server SHALL expose endpoints to create, replace, and delete named template sets stored separately from the base template collection.

#### Scenario: Replace template set
- **GIVEN** the request body contains valid mock definitions
- **WHEN** a client posts to `POST /api/v1/template_sets/{setKey}`
- **THEN** the system SHALL create or replace the full persisted template set for `setKey`
- **AND** the admin HTTP server SHALL return `200 OK` with the submitted mocks

#### Scenario: Delete template set
- **GIVEN** a persisted template set exists for `setKey`
- **WHEN** a client requests `DELETE /api/v1/template_sets/{setKey}`
- **THEN** the system SHALL delete only the persisted template set for `setKey`
- **AND** the admin HTTP server SHALL return `204 No Content`

### Requirement: Admin Mutation Visibility
The system SHALL make successful mutating admin requests visible to later mock requests within a bounded eventual-reload window.

#### Scenario: Mutation becomes active
- **WHEN** a mutating admin request succeeds
- **THEN** subsequent mock requests SHALL observe the resulting active mock set within the reload window
