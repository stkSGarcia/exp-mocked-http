## ADDED Requirements

> Extends: http-yaml-mock-server/add-http-yaml-mock-server

### Requirement: Admin server configuration
The system SHALL run an admin HTTP server independently from the mock HTTP listener, controlled by `HM_ADMIN_HTTP_ENABLED`, `HM_ADMIN_HTTP_HOST`, and `HM_ADMIN_HTTP_PORT`. The enabled default SHALL be `true`, the host default SHALL be `0.0.0.0`, and the port default SHALL be `9998`.

#### Scenario: Admin server uses defaults
- **GIVEN** no admin HTTP environment variables are set
- **WHEN** the process starts
- **THEN** the admin server listens on `0.0.0.0:9998`

#### Scenario: Admin server is disabled
- **GIVEN** `HM_ADMIN_HTTP_ENABLED` is set to `false`
- **WHEN** the process starts
- **THEN** the process does not start an admin HTTP listener
- **AND** the mock HTTP listener remains available

#### Scenario: Admin listener address is overridden
- **GIVEN** `HM_ADMIN_HTTP_HOST` and `HM_ADMIN_HTTP_PORT` contain valid overrides
- **WHEN** the process starts with the admin server enabled
- **THEN** the admin server listens on the configured address

### Requirement: Admin health endpoint
The admin server SHALL expose `GET /api/v1/health` and return `200 OK` with the JSON object `{"status":"OK"}`.

#### Scenario: Health check succeeds
- **WHEN** a client requests `GET /api/v1/health`
- **THEN** the response status is `200 OK`
- **AND** the JSON response body is `{"status":"OK"}`

### Requirement: Active template listing
The admin server SHALL expose `GET /api/v1/templates` and return every definition in the currently active merged mock set, including filesystem-loaded definitions, API-added base definitions, and definitions from named template sets.

#### Scenario: List all active definitions
- **GIVEN** filesystem, API base, and named-set definitions are active
- **WHEN** a client requests `GET /api/v1/templates`
- **THEN** the response status is `200 OK`
- **AND** the response body is a JSON array containing the active definition object for every active key

#### Scenario: Duplicate keys are represented by the winner
- **GIVEN** multiple sources contain the same mock key
- **WHEN** a client requests `GET /api/v1/templates`
- **THEN** the response contains only the definition selected by the active merge precedence

### Requirement: Base template upsert
The admin server SHALL expose `POST /api/v1/templates`, validate submitted mock definitions using the existing definition schema, add or replace base API definitions by key, persist the resulting base collection, and return `200 OK` with the submitted definitions.

#### Scenario: Add valid base definitions
- **GIVEN** the request body contains valid mock definitions
- **WHEN** a client posts the body to `POST /api/v1/templates`
- **THEN** the response status is `200 OK`
- **AND** the response body contains the submitted definitions
- **AND** the definitions are stored in the base API collection

#### Scenario: Update an existing base definition
- **GIVEN** the base API collection already contains a definition with a submitted key
- **WHEN** a valid replacement is posted to `POST /api/v1/templates`
- **THEN** the persisted base definition for that key is replaced
- **AND** other base definitions remain unchanged

#### Scenario: Reject invalid definitions
- **GIVEN** the request body is malformed or contains a definition that fails existing mock validation
- **WHEN** a client posts the body to `POST /api/v1/templates`
- **THEN** the response status is `400 Bad Request`
- **AND** the response body contains an error message
- **AND** no submitted definition is persisted

### Requirement: Base template deletion
The admin server SHALL expose deletion operations that affect only the persistent base API collection.

#### Scenario: Delete all base API definitions
- **GIVEN** base API definitions, filesystem definitions, and named template sets exist
- **WHEN** a client requests `DELETE /api/v1/templates`
- **THEN** the response status is `204 No Content`
- **AND** all base API definitions are deleted
- **AND** filesystem definitions and named template sets remain unchanged

#### Scenario: Delete one persisted base definition
- **GIVEN** the base API collection contains `{templateKey}`
- **WHEN** a client requests `DELETE /api/v1/templates/{templateKey}`
- **THEN** the response status is `204 No Content`
- **AND** only that base API definition is deleted
- **AND** a filesystem definition with the same key remains unchanged

#### Scenario: Delete a missing base definition
- **GIVEN** `{templateKey}` does not exist in the persistent base API collection
- **WHEN** a client requests `DELETE /api/v1/templates/{templateKey}`
- **THEN** the response status is `404 Not Found`
- **AND** no other collection is changed

### Requirement: Named template set replacement
The admin server SHALL expose `POST /api/v1/template_sets/{setKey}`, validate the submitted definitions, create or replace the complete named set, persist it separately from base templates and other sets, and return `200 OK` with the submitted definitions.

#### Scenario: Create a named set
- **GIVEN** `{setKey}` does not exist and the request contains valid definitions
- **WHEN** a client posts to `POST /api/v1/template_sets/{setKey}`
- **THEN** the response status is `200 OK`
- **AND** the response body contains the submitted definitions
- **AND** the complete set is persisted under `{setKey}`

#### Scenario: Replace a named set
- **GIVEN** `{setKey}` already contains persisted definitions
- **WHEN** a client posts a valid replacement collection to `POST /api/v1/template_sets/{setKey}`
- **THEN** the persisted contents of `{setKey}` equal the submitted collection
- **AND** base templates and every other named set remain unchanged

#### Scenario: Reject an invalid named set
- **GIVEN** the submitted collection contains an invalid definition
- **WHEN** a client posts to `POST /api/v1/template_sets/{setKey}`
- **THEN** the response status is `400 Bad Request`
- **AND** the previously persisted set remains unchanged

### Requirement: Named template set deletion
The admin server SHALL expose `DELETE /api/v1/template_sets/{setKey}` to delete the complete named set while leaving base templates and other named sets unchanged.

#### Scenario: Delete one named set
- **GIVEN** multiple named sets and base API definitions exist
- **WHEN** a client requests `DELETE /api/v1/template_sets/{setKey}`
- **THEN** the response status is `204 No Content`
- **AND** `{setKey}` is removed
- **AND** all other named sets and base definitions remain unchanged

#### Scenario: Delete an absent named set
- **GIVEN** `{setKey}` does not exist
- **WHEN** a client requests `DELETE /api/v1/template_sets/{setKey}`
- **THEN** the response status is `204 No Content`
- **AND** no stored collection is changed

### Requirement: Mutation reload visibility
After each successful mutating admin request, the system SHALL rebuild the active mock set and make the resulting state visible to later mock and admin requests within a bounded reload window.

#### Scenario: Successful mutation becomes visible
- **GIVEN** a mutating admin request returns a success status
- **WHEN** the reload window elapses
- **THEN** subsequent mock requests use the resulting active definitions
- **AND** `GET /api/v1/templates` reports the resulting active set

#### Scenario: Failed mutation does not trigger a partial reload
- **GIVEN** a mutating admin request fails validation
- **WHEN** later mock or admin requests are served
- **THEN** they continue to observe the previously valid active set

### Requirement: Persistent collection isolation
The persistent store SHALL keep the base API collection and each named template set in separate internal records so replacing or deleting one collection cannot alter another.

#### Scenario: Base mutation preserves sets
- **GIVEN** base API definitions and multiple named sets are persisted
- **WHEN** the base API collection is updated or deleted
- **THEN** every named set retains its prior contents

#### Scenario: Set mutation preserves other collections
- **GIVEN** base API definitions and multiple named sets are persisted
- **WHEN** one named set is replaced or deleted
- **THEN** the base API collection and every other named set retain their prior contents
