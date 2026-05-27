## ADDED Requirements

### Requirement: Admin server configuration
The server SHALL read `HM_ADMIN_HTTP_ENABLED` (default `true`), `HM_ADMIN_HTTP_PORT` (default `9998`), and `HM_ADMIN_HTTP_HOST` (default `0.0.0.0`) at startup. When `HM_ADMIN_HTTP_ENABLED=false`, the admin server SHALL NOT start.

#### Scenario: Admin server starts by default
- **WHEN** `HM_ADMIN_HTTP_ENABLED` is not set
- **THEN** the admin server listens on `0.0.0.0:9998`

#### Scenario: Admin server disabled
- **WHEN** `HM_ADMIN_HTTP_ENABLED=false`
- **THEN** no admin server starts and port 9998 is not bound

#### Scenario: Custom admin port and host
- **WHEN** `HM_ADMIN_HTTP_PORT=7777` and `HM_ADMIN_HTTP_HOST=127.0.0.1`
- **THEN** the admin server listens on `127.0.0.1:7777`

### Requirement: GET /api/v1/health
The admin server SHALL respond to `GET /api/v1/health` with `200 OK` and body `{"status": "OK"}`.

#### Scenario: Health check returns 200
- **WHEN** `GET /api/v1/health` is sent to the admin server
- **THEN** the response is `200 OK` with body `{"status": "OK"}`

### Requirement: GET /api/v1/templates
The admin server SHALL respond to `GET /api/v1/templates` with `200 OK` and a JSON array of all currently active mock definitions, including filesystem-loaded mocks and API-added mocks.

#### Scenario: Returns all active mocks
- **WHEN** `GET /api/v1/templates` is called after adding mocks via API and loading filesystem mocks
- **THEN** the response contains both filesystem-loaded and API-added mocks as a JSON array

#### Scenario: Returns empty array when no mocks
- **WHEN** no mocks are loaded
- **THEN** `GET /api/v1/templates` returns `200 OK` with body `[]`

### Requirement: POST /api/v1/templates
The admin server SHALL accept `POST /api/v1/templates` with a JSON array of mock definitions in the request body, add or update the submitted mocks in the base API store, persist them, and make them visible to subsequent mock-server requests within the reload window. On validation failure it SHALL return `400 Bad Request` with an error message. On success it SHALL return `200 OK` with the submitted mocks.

#### Scenario: Valid mocks accepted and stored
- **WHEN** a valid JSON array of mock definitions is `POST`ed to `/api/v1/templates`
- **THEN** the response is `200 OK` with the submitted mocks, and they are active within the reload window

#### Scenario: Invalid mocks return 400
- **WHEN** the request body is invalid JSON or fails mock validation
- **THEN** the response is `400 Bad Request` with an error message

#### Scenario: Existing mock updated on re-post
- **WHEN** a mock with an existing key is `POST`ed
- **THEN** the updated version replaces the previous one

### Requirement: DELETE /api/v1/templates
The admin server SHALL respond to `DELETE /api/v1/templates` by deleting all base API-added mocks, leaving filesystem mocks and template sets untouched, and returning `204 No Content`.

#### Scenario: All API base mocks deleted
- **WHEN** `DELETE /api/v1/templates` is called
- **THEN** API-added base mocks are removed and the response is `204 No Content`

#### Scenario: Filesystem mocks untouched by delete all
- **WHEN** `DELETE /api/v1/templates` is called and filesystem mocks exist
- **THEN** filesystem mocks remain active after the reload window

#### Scenario: Template sets untouched by delete all
- **WHEN** `DELETE /api/v1/templates` is called and template sets exist
- **THEN** template sets remain active after the reload window

### Requirement: DELETE /api/v1/templates/{templateKey}
The admin server SHALL respond to `DELETE /api/v1/templates/{templateKey}` by deleting the API-persisted mock for `{templateKey}`. If the key does not exist in the persistent store, it SHALL return `404 Not Found`. On success it SHALL return `204 No Content`. Filesystem mocks with the same key SHALL remain untouched.

#### Scenario: Existing API mock deleted by key
- **WHEN** `DELETE /api/v1/templates/foo` is called and `foo` exists in the API store
- **THEN** the response is `204 No Content` and the mock is removed within the reload window

#### Scenario: Missing key returns 404
- **WHEN** `DELETE /api/v1/templates/nonexistent` is called
- **THEN** the response is `404 Not Found`

#### Scenario: Filesystem mock with same key unaffected
- **WHEN** a filesystem mock has key `foo` and `DELETE /api/v1/templates/foo` is called
- **THEN** the filesystem mock remains active and only the API-stored version is deleted

### Requirement: POST /api/v1/template_sets/{setKey}
The admin server SHALL accept `POST /api/v1/template_sets/{setKey}` with a JSON array of mock definitions, create or fully replace the set for `{setKey}`, persist it separately from base templates, make it visible within the reload window, and return `200 OK` with the submitted mocks.

#### Scenario: Template set created
- **WHEN** `POST /api/v1/template_sets/myset` is called with valid mock definitions
- **THEN** the response is `200 OK` with the submitted mocks and the set is active within the reload window

#### Scenario: Template set replaced on re-post
- **WHEN** `POST /api/v1/template_sets/myset` is called twice with different mocks
- **THEN** the second call fully replaces the set (no mocks from the first call remain)

### Requirement: DELETE /api/v1/template_sets/{setKey}
The admin server SHALL respond to `DELETE /api/v1/template_sets/{setKey}` by deleting the entire set for `{setKey}`, leaving all other sets untouched, and returning `204 No Content`.

#### Scenario: Template set deleted
- **WHEN** `DELETE /api/v1/template_sets/myset` is called
- **THEN** the response is `204 No Content` and the set's mocks are no longer active

#### Scenario: Other sets unaffected
- **WHEN** `DELETE /api/v1/template_sets/myset` is called and `otherset` exists
- **THEN** `otherset` remains active after the reload window
