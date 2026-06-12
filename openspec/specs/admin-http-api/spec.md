## Purpose

Define the admin HTTP API used to inspect, add, replace, delete, and persist runtime-managed mock definitions.

## Requirements

### Requirement: Admin Server Configuration
The system SHALL start the admin HTTP server according to admin-specific environment configuration.

#### Scenario: Admin server defaults are used
- **WHEN** the server starts without `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, or `HM_ADMIN_HTTP_HOST`
- **THEN** the admin server SHALL be enabled, listen on port `9998`, and bind to `0.0.0.0`

#### Scenario: Admin server can be disabled
- **WHEN** the server starts with `HM_ADMIN_HTTP_ENABLED` set to `false`
- **THEN** the admin server SHALL NOT listen for admin HTTP requests

#### Scenario: Admin server bind address is configured
- **WHEN** the server starts with `HM_ADMIN_HTTP_ENABLED=true`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` set
- **THEN** the admin server SHALL listen using the configured admin port and host

### Requirement: Admin Health Endpoint
The system SHALL expose an admin health endpoint.

#### Scenario: Health endpoint succeeds
- **WHEN** an admin client sends `GET /api/v1/health`
- **THEN** the system SHALL return `200 OK` with JSON body `{"status":"OK"}`

### Requirement: Admin Template Listing
The system SHALL expose the active mock definitions through the admin templates endpoint.

#### Scenario: Active templates are listed
- **WHEN** an admin client sends `GET /api/v1/templates`
- **THEN** the system SHALL return `200 OK` with a JSON array containing every active mock definition from filesystem-loaded mocks, base API-added mocks, and template sets

### Requirement: Admin Base Template Upsert
The system SHALL allow admin clients to add or replace base API-added mock definitions.

#### Scenario: Submitted base templates are persisted
- **WHEN** an admin client sends `POST /api/v1/templates` with a valid JSON array of mock definitions
- **THEN** the system SHALL persist those definitions in the base API-added template collection and return `200 OK` with the submitted mock definitions

#### Scenario: Submitted base templates are visible after reload
- **WHEN** `POST /api/v1/templates` succeeds with valid mock definitions
- **THEN** later mock requests SHALL observe the updated active mock set within the bounded reload window

#### Scenario: Invalid submitted base templates are rejected
- **WHEN** an admin client sends `POST /api/v1/templates` with invalid mock definitions
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the invalid definitions

### Requirement: Admin Base Template Deletion
The system SHALL allow admin clients to delete base API-added mock definitions without deleting filesystem mocks or template sets.

#### Scenario: All base API-added templates are deleted
- **WHEN** an admin client sends `DELETE /api/v1/templates`
- **THEN** the system SHALL delete all base API-added mocks, leave filesystem mocks and template sets intact, and return `204 No Content`

#### Scenario: One base API-added template is deleted
- **WHEN** an admin client sends `DELETE /api/v1/templates/{templateKey}` for an API-persisted mock key that exists in the base collection
- **THEN** the system SHALL delete that API-persisted mock, leave any filesystem mock with the same key intact, and return `204 No Content`

#### Scenario: Missing base API-added template delete fails
- **WHEN** an admin client sends `DELETE /api/v1/templates/{templateKey}` for a key that does not exist in the base persistent store
- **THEN** the system SHALL return `404 Not Found`

#### Scenario: Base template delete is visible after reload
- **WHEN** a base template deletion succeeds
- **THEN** later mock requests SHALL observe the updated active mock set within the bounded reload window

### Requirement: Admin Template Sets
The system SHALL store named template sets separately from the base API-added template collection.

#### Scenario: Template set is replaced
- **WHEN** an admin client sends `POST /api/v1/template_sets/{setKey}` with a valid JSON array of mock definitions
- **THEN** the system SHALL create or replace the full set for `{setKey}`, persist it separately from base templates, and return `200 OK` with the submitted mock definitions

#### Scenario: Template set update is visible after reload
- **WHEN** `POST /api/v1/template_sets/{setKey}` succeeds
- **THEN** later mock requests SHALL observe the updated active mock set within the bounded reload window

#### Scenario: Invalid template set is rejected
- **WHEN** an admin client sends `POST /api/v1/template_sets/{setKey}` with invalid mock definitions
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the invalid set

#### Scenario: Template set is deleted
- **WHEN** an admin client sends `DELETE /api/v1/template_sets/{setKey}`
- **THEN** the system SHALL delete the entire set for `{setKey}`, leave other sets untouched, and return `204 No Content`

### Requirement: Admin Persistence Across Restart
The system SHALL load API-added base mocks and template sets from persistent storage during startup.

#### Scenario: Base API-added mocks survive restart
- **WHEN** the process restarts after base API-added mocks have been persisted
- **THEN** the system SHALL load those mocks into the active mock set on startup

#### Scenario: Template sets survive restart
- **WHEN** the process restarts after one or more template sets have been persisted
- **THEN** the system SHALL load those template sets into the active mock set on startup while preserving each set under its own set key

#### Scenario: Deleting one template set preserves others
- **WHEN** one persisted template set is deleted
- **THEN** the system SHALL NOT delete or modify any other persisted template set
