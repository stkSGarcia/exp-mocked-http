## ADDED Requirements

### Requirement: Admin Server Configuration
The system SHALL run an admin HTTP server according to admin-specific environment configuration.

#### Scenario: Default admin configuration is used
- **WHEN** the server starts without `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, or `HM_ADMIN_HTTP_HOST`
- **THEN** the admin server SHALL be enabled, listen on port `9998`, and bind to `0.0.0.0`

#### Scenario: Admin configuration is overridden
- **WHEN** the server starts with `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_PORT`, and `HM_ADMIN_HTTP_HOST` set
- **THEN** the system SHALL use those values for admin server enablement, listen port, and bind address

#### Scenario: Admin server is disabled
- **WHEN** `HM_ADMIN_HTTP_ENABLED` is set to `false`
- **THEN** the system SHALL NOT start the admin HTTP server

### Requirement: Admin Health Endpoint
The admin server SHALL expose a health endpoint.

#### Scenario: Health check succeeds
- **WHEN** a client sends `GET /api/v1/health` to the admin server
- **THEN** the system SHALL return `200 OK` with JSON body `{"status":"OK"}`

### Requirement: Active Template Listing
The admin server SHALL expose the active mock definitions.

#### Scenario: Active templates are listed
- **WHEN** a client sends `GET /api/v1/templates`
- **THEN** the system SHALL return `200 OK` with a JSON array containing every active filesystem-loaded mock definition, base API-added mock definition, and template-set mock definition

### Requirement: Base API Template Mutation
The admin server SHALL allow clients to add, update, and clear base API-added mock definitions.

#### Scenario: Base API templates are added or updated
- **WHEN** a client sends `POST /api/v1/templates` with a JSON array of mock definitions
- **THEN** the system SHALL validate the submitted definitions, persist them in the base API-added mock collection, and return `200 OK` with the submitted mocks

#### Scenario: Invalid base API templates are rejected
- **WHEN** a client sends `POST /api/v1/templates` with mock definitions that fail validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the submitted definitions

#### Scenario: Base API templates are cleared
- **WHEN** a client sends `DELETE /api/v1/templates`
- **THEN** the system SHALL delete all base API-added mocks, leave filesystem mocks and template sets untouched, and return `204 No Content`

#### Scenario: Single base API template is deleted
- **WHEN** a client sends `DELETE /api/v1/templates/{templateKey}` for a key present in the persistent base API-added mock collection
- **THEN** the system SHALL delete that persisted mock, leave any filesystem mock with the same key untouched, and return `204 No Content`

#### Scenario: Missing base API template delete returns not found
- **WHEN** a client sends `DELETE /api/v1/templates/{templateKey}` for a key absent from the persistent base API-added mock collection
- **THEN** the system SHALL return `404 Not Found`

### Requirement: Template Set Mutation
The admin server SHALL store named groups of mock definitions separately from the base API-added mock collection.

#### Scenario: Template set is replaced
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with a JSON array of mock definitions
- **THEN** the system SHALL validate the submitted definitions, replace the full persisted set for `{setKey}`, and return `200 OK` with the submitted mocks

#### Scenario: Invalid template set is rejected
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with mock definitions that fail validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT replace the persisted set

#### Scenario: Template set is deleted
- **WHEN** a client sends `DELETE /api/v1/template_sets/{setKey}`
- **THEN** the system SHALL delete the entire set for `{setKey}`, leave all other sets and base API-added mocks untouched, and return `204 No Content`

### Requirement: Admin Mutation Reload Visibility
Admin mutations SHALL become visible to subsequent mock-server requests within a bounded eventual-reload window.

#### Scenario: Added templates become active
- **WHEN** a successful admin mutation adds or replaces persisted mock definitions
- **THEN** later mock-server requests SHALL observe the resulting active mock set within the reload window

#### Scenario: Deleted templates stop matching
- **WHEN** a successful admin mutation deletes persisted mock definitions
- **THEN** later mock-server requests SHALL observe the deletion within the reload window
