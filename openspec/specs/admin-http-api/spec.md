## Purpose

Define the admin HTTP server configuration, health checks, runtime mock management endpoints, template-set management, and admin mutation visibility.

## Requirements

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

### Requirement: YAML Admin Template Mutation Payloads
The admin server SHALL accept YAML mock-definition payloads for template mutation endpoints.

#### Scenario: Base API templates accept YAML
- **WHEN** a client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and a YAML array of mock definitions
- **THEN** the system SHALL validate the submitted definitions, persist them in the base API-added mock collection, and return `200 OK` with the submitted mocks

#### Scenario: Template set accepts YAML
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and a YAML array of mock definitions
- **THEN** the system SHALL validate the submitted definitions, replace the full persisted set for `{setKey}`, and return `200 OK` with the submitted mocks

#### Scenario: Invalid YAML base API templates are rejected
- **WHEN** a client sends `POST /api/v1/templates` with `Content-Type: application/yaml` and mock definitions that fail parsing or validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT persist the submitted definitions

#### Scenario: Invalid YAML template set is rejected
- **WHEN** a client sends `POST /api/v1/template_sets/{setKey}` with `Content-Type: application/yaml` and mock definitions that fail parsing or validation
- **THEN** the system SHALL return `400 Bad Request` with an error message and SHALL NOT replace the persisted set

### Requirement: Admin Mutation Reload Visibility
Admin mutations SHALL become visible to subsequent mock-server requests within a bounded eventual-reload window.

#### Scenario: Added templates become active
- **WHEN** a successful admin mutation adds or replaces persisted mock definitions
- **THEN** later mock-server requests SHALL observe the resulting active mock set within the reload window

#### Scenario: Deleted templates stop matching
- **WHEN** a successful admin mutation deletes persisted mock definitions
- **THEN** later mock-server requests SHALL observe the deletion within the reload window

### Requirement: Dry-Run Evaluation Endpoint
The admin server SHALL expose `POST /api/v1/evaluate` to evaluate one mock definition against simulated channel context without executing side effects.

#### Scenario: Evaluation request accepts one mock and one context object
- **WHEN** a client sends `POST /api/v1/evaluate` with JSON object fields `mock` and `context`
- **THEN** the system SHALL parse `mock` as one mock definition and `context` as one JSON object containing channel-specific context sub-objects

#### Scenario: Evaluation request rejects missing key
- **WHEN** a client sends an evaluation request where `mock.key` is missing or empty
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Evaluation request requires supported matcher
- **WHEN** a client sends an evaluation request where `mock.expect` does not include `http`, `kafka`, `amqp`, or `grpc`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Evaluation request validates matcher required fields
- **WHEN** a client sends an evaluation request with a declared matcher missing its required fields
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Evaluation request requires matching channel context
- **WHEN** a client sends an evaluation request without the channel context needed by the declared matcher
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Evaluation request uses AMQP routing key as default queue
- **WHEN** a client sends an evaluation request with `mock.expect.amqp.exchange` and `mock.expect.amqp.routing_key` and omits `mock.expect.amqp.queue`
- **THEN** the system SHALL evaluate the AMQP queue as the routing key

#### Scenario: Matcher failure short-circuits rendering
- **WHEN** the simulated channel context does not match the declared matcher
- **THEN** the system SHALL return `expect_passed` as `false` and `actions_performed` as an empty array

#### Scenario: Empty condition passes evaluation
- **WHEN** the simulated channel context matches and the mock omits `expect.condition` or sets it to an empty string
- **THEN** the system SHALL return `expect_passed` as `true` and `condition_passed` as `true`

#### Scenario: Condition failure returns rendered condition
- **WHEN** the simulated channel context matches and `expect.condition` renders to a value other than `true`
- **THEN** the system SHALL return `expect_passed` as `true`, `condition_passed` as `false`, `condition_rendered` as the raw rendered condition output, and `actions_performed` as an empty array

#### Scenario: Passing evaluation renders supported action previews
- **WHEN** the simulated channel context matches and the condition passes
- **THEN** the system SHALL sort actions by `order`, evaluate them without side effects, and include rendered result objects only for `reply_http` and `publish_kafka`

#### Scenario: Reply HTTP preview includes generated headers
- **WHEN** evaluation renders a `reply_http` action preview
- **THEN** the result SHALL have type `reply_http_action_performed` and include string `status_code`, `content_type` defaulting to `application/json`, rendered `body`, and headers containing generated `Content-Type` and `Content-Length`

#### Scenario: Publish Kafka preview includes rendered topic and payload
- **WHEN** evaluation renders a `publish_kafka` action preview
- **THEN** the result SHALL have type `publish_kafka_action_performed` and include rendered `topic` and `payload`

#### Scenario: Side-effecting actions are not executed
- **WHEN** evaluation reaches actions other than `reply_http` and `publish_kafka`
- **THEN** the system SHALL NOT execute side effects and SHALL omit those actions from `actions_performed`
