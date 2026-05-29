# admin-api

## Purpose

TBD

## Requirements

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

### Requirement: POST /api/v1/evaluate
The admin server SHALL accept `POST /api/v1/evaluate` with a JSON object containing `mock` (one mock definition using the normal mock schema) and `context` (one JSON object containing one or more simulated channel contexts). The endpoint SHALL validate the request, evaluate matching and template rendering without executing any side effects, and return the result. On validation failure it SHALL return `400 Bad Request` with an error message. On success it SHALL return `200 OK`.

#### Scenario: Valid request returns 200
- **WHEN** a valid `POST /api/v1/evaluate` body is submitted with a matching mock and context
- **THEN** the response is `200 OK` with an evaluation result object

#### Scenario: Missing mock.key returns 400
- **WHEN** the submitted `mock` has an empty or absent `key`
- **THEN** the response is `400 Bad Request` with an error message

#### Scenario: Missing matcher returns 400
- **WHEN** `mock.expect` does not include any of `http`, `kafka`, `amqp`, or `grpc`
- **THEN** the response is `400 Bad Request` with an error message

#### Scenario: Missing required matcher fields returns 400
- **WHEN** `mock.expect.http` is declared but lacks required fields
- **THEN** the response is `400 Bad Request` with an error message

#### Scenario: Missing channel context for declared matcher returns 400
- **WHEN** `mock.expect.http` is declared but `context` does not include `http_context`
- **THEN** the response is `400 Bad Request` with an error message

#### Scenario: Missing amqp.exchange or amqp.routing_key returns 400
- **WHEN** `mock.expect.amqp` is declared but `exchange` or `routing_key` is absent
- **THEN** the response is `400 Bad Request` with an error message

### Requirement: Evaluate context fields
The `context` object in the evaluate request SHALL be a single JSON object (not an array). It MAY contain any combination of `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects. The endpoint SHALL merge all provided sub-objects into a single template context for rendering. The fields for each sub-object are: `http_context` — `method`, `path`, `body`, `headers`, `query_string`; `kafka_context` — `topic`, `payload`; `amqp_context` — `exchange`, `routing_key`, `queue`, `payload`; `grpc_context` — `service`, `method`, `payload`, `headers`.

#### Scenario: http_context fields exposed in template context
- **WHEN** `context.http_context` contains `method: GET` and `path: /foo`
- **THEN** the template context exposes `.Method = "GET"` and `.Path = "/foo"` during rendering

#### Scenario: grpc_context fields exposed in template context
- **WHEN** `context.grpc_context` contains `service: com.example.Greeter`, `method: SayHello`, and `payload: '{"name":"world"}'`
- **THEN** the template context exposes `.GRPCService`, `.GRPCMethod`, and `.GRPCPayload` accordingly

#### Scenario: amqp_context queue defaults to routing_key
- **WHEN** `context.amqp_context` contains `routing_key: orders` and omits `queue`
- **THEN** the effective queue is `orders`

### Requirement: Evaluate response shape
When the channel-specific matcher fails, the response SHALL be `{"expect_passed": false, "actions_performed": []}`. When matching passes but the condition fails, the response SHALL include `expect_passed: true`, `condition_passed: false`, the rendered condition string in `condition_rendered`, and an empty `actions_performed`. When both matching and condition pass, the response SHALL include `expect_passed: true`, `condition_passed: true`, `condition_rendered`, and `actions_performed` containing rendered results for `reply_http` and `publish_kafka` actions only. Actions SHALL be evaluated in `order` sort order.

#### Scenario: No match returns expect_passed false
- **WHEN** `mock.expect.http.method: GET` and `context.http_context.method: POST`
- **THEN** the response is `{"expect_passed": false, "actions_performed": []}`

#### Scenario: Condition failure returns expect_passed true and condition_passed false
- **WHEN** matching passes but `mock.expect.condition` renders to `false`
- **THEN** the response includes `expect_passed: true`, `condition_passed: false`, the rendered condition in `condition_rendered`, and `actions_performed: []`

#### Scenario: Full match returns rendered reply_http result
- **WHEN** matching and condition both pass and `actions` contains a `reply_http` action
- **THEN** `actions_performed` contains one `reply_http_action_performed` entry with `status_code`, `content_type`, `body`, and `headers` (including `Content-Type` and `Content-Length`); `status_code` is a string

#### Scenario: Full match returns rendered publish_kafka result
- **WHEN** matching and condition both pass and `actions` contains a `publish_kafka` action
- **THEN** `actions_performed` contains one `publish_kafka_action_performed` entry with `topic` and `payload`

#### Scenario: Empty condition treated as passing
- **WHEN** `mock.expect` has no `condition` field and matching passes
- **THEN** `condition_passed` is `true` and evaluation continues to actions

#### Scenario: Non-reply_http and non-publish_kafka actions omitted
- **WHEN** actions include `sleep`, `redis`, `send_http`, `publish_amqp`, or `reply_grpc`
- **THEN** those actions are omitted from `actions_performed` and no side effects occur

#### Scenario: reply_http default content_type is application/json
- **WHEN** a `reply_http` action does not specify `content_type`
- **THEN** the `reply_http_action_performed` entry has `content_type: application/json`
