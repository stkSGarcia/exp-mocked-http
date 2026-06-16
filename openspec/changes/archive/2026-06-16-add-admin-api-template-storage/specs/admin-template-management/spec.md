## ADDED Requirements

> Extends: http-behavior-mocking/add-http-yaml-mock-server

### Requirement: Admin Server Configuration
The system SHALL run an admin HTTP server according to admin environment configuration.

#### Scenario: Admin server defaults are used
- **WHEN** the process starts without `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, or `HM_ADMIN_HTTP_HOST`
- **THEN** the admin server SHALL be enabled, listen on port `9998`, and bind to `0.0.0.0`

#### Scenario: Admin server is disabled
- **WHEN** the process starts with `HM_ADMIN_HTTP_ENABLED` set to `false`
- **THEN** the admin HTTP server SHALL NOT accept admin requests

#### Scenario: Admin bind settings are overridden
- **WHEN** the process starts with `HM_ADMIN_HTTP_PORT` and `HM_ADMIN_HTTP_HOST` set
- **THEN** the admin server SHALL listen using those configured values

### Requirement: Admin Health Endpoint
The admin server SHALL expose `GET /api/v1/health` as a health check endpoint.

#### Scenario: Health check succeeds
- **WHEN** a client sends `GET /api/v1/health`
- **THEN** the admin server SHALL return `200 OK` with body exactly `{"status":"OK"}`

### Requirement: Active Template Listing
The admin server SHALL expose `GET /api/v1/templates` to list every active mock definition.

#### Scenario: Filesystem and API mocks are listed
- **WHEN** a client sends `GET /api/v1/templates`
- **THEN** the admin server SHALL return `200 OK` with a JSON array containing filesystem-loaded mocks and API-added mocks from the active mock set

#### Scenario: Template-set mocks are listed
- **WHEN** template sets are active and a client sends `GET /api/v1/templates`
- **THEN** the response JSON array SHALL include active mock definitions contributed by those template sets

### Requirement: Base Template Upsert
The admin server SHALL expose `POST /api/v1/templates` to add or update base API-managed mock definitions.

#### Scenario: Valid base templates are persisted
- **WHEN** a client posts valid mock definitions to `/api/v1/templates`
- **THEN** the admin server SHALL add or update those definitions in the base API-managed template collection, persist them, and return `200 OK` with the submitted mocks

#### Scenario: Invalid base templates are rejected
- **WHEN** a client posts invalid mock definitions to `/api/v1/templates`
- **THEN** the admin server SHALL return `400 Bad Request` with an error message and SHALL NOT persist the invalid definitions

#### Scenario: Base template update becomes visible
- **WHEN** a valid `POST /api/v1/templates` request succeeds
- **THEN** later mock requests SHALL observe the updated active mock set within a bounded eventual-reload window

### Requirement: Base Template Deletion
The admin server SHALL expose base API-managed template deletion endpoints.

#### Scenario: All base API templates are deleted
- **WHEN** a client sends `DELETE /api/v1/templates`
- **THEN** the admin server SHALL delete all base API-managed mocks, leave filesystem mocks and template sets untouched, and return `204 No Content`

#### Scenario: One base API template is deleted
- **WHEN** a client sends `DELETE /api/v1/templates/{templateKey}` for a key present in the persistent base API-managed store
- **THEN** the admin server SHALL delete that persisted mock, leave any filesystem mock with the same key untouched, and return `204 No Content`

#### Scenario: Missing base API template returns not found
- **WHEN** a client sends `DELETE /api/v1/templates/{templateKey}` for a key absent from the persistent base API-managed store
- **THEN** the admin server SHALL return `404 Not Found`

#### Scenario: Base template delete becomes visible
- **WHEN** a base template delete request succeeds
- **THEN** later mock requests SHALL observe the updated active mock set within a bounded eventual-reload window

### Requirement: Template Set Replacement
The admin server SHALL expose `POST /api/v1/template_sets/{setKey}` to create or replace a named template set.

#### Scenario: Valid template set is persisted
- **WHEN** a client posts valid mock definitions to `/api/v1/template_sets/{setKey}`
- **THEN** the admin server SHALL replace the full set for `{setKey}`, persist that set separately from base templates, and return `200 OK` with the submitted mocks

#### Scenario: Invalid template set is rejected
- **WHEN** a client posts invalid mock definitions to `/api/v1/template_sets/{setKey}`
- **THEN** the admin server SHALL return `400 Bad Request` with an error message and SHALL NOT persist the invalid set

#### Scenario: Template set replacement becomes visible
- **WHEN** a valid `POST /api/v1/template_sets/{setKey}` request succeeds
- **THEN** later mock requests SHALL observe the updated active mock set within a bounded eventual-reload window

### Requirement: Template Set Deletion
The admin server SHALL expose `DELETE /api/v1/template_sets/{setKey}` to delete a named template set.

#### Scenario: Template set is deleted
- **WHEN** a client sends `DELETE /api/v1/template_sets/{setKey}`
- **THEN** the admin server SHALL delete the entire set for `{setKey}`, leave other sets untouched, and return `204 No Content`

#### Scenario: Template set delete becomes visible
- **WHEN** a template set delete request succeeds
- **THEN** later mock requests SHALL observe the updated active mock set within a bounded eventual-reload window
