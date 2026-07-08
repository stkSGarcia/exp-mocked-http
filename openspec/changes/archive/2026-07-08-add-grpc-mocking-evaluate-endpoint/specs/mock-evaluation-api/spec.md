## ADDED Requirements

> Extends: http-behavior-mocking/add-stateful-actions
> Extends: template-rendering/add-http-yaml-mock-server
> Extends: internal-keyspace-protection/add-admin-api-template-storage

### Requirement: Evaluation API Request
The system SHALL expose `POST /api/v1/evaluate` to accept one mock definition and one simulated channel context object.

#### Scenario: Valid request shape
- **GIVEN** a request body contains a `mock` object using the normal mock schema
- **AND** the request body contains a `context` object
- **WHEN** `POST /api/v1/evaluate` is called
- **THEN** the system evaluates the mock definition against the simulated context

#### Scenario: Context object is not an array
- **GIVEN** a request body contains `context` as an array
- **WHEN** `POST /api/v1/evaluate` is called
- **THEN** the response is `400 Bad Request`

### Requirement: Evaluation API Validation
The system SHALL return `400 Bad Request` when the mock definition or simulated context cannot be evaluated.

#### Scenario: Missing mock key
- **GIVEN** the request `mock.key` is empty
- **WHEN** `POST /api/v1/evaluate` is called
- **THEN** the response is `400 Bad Request`

#### Scenario: Missing supported matcher
- **GIVEN** the request `mock.expect` omits all supported matchers
- **WHEN** `POST /api/v1/evaluate` is called
- **THEN** the response is `400 Bad Request`

#### Scenario: Required matcher fields
- **GIVEN** the request declares an `http`, `kafka`, `amqp`, or `grpc` matcher
- **AND** one of that matcher's required fields is missing
- **WHEN** `POST /api/v1/evaluate` is called
- **THEN** the response is `400 Bad Request`

#### Scenario: Required channel context
- **GIVEN** the request declares a supported matcher
- **AND** `context` does not include the matching channel context object
- **WHEN** `POST /api/v1/evaluate` is called
- **THEN** the response is `400 Bad Request`

#### Scenario: AMQP queue default
- **GIVEN** the request declares `mock.expect.amqp.exchange` and `mock.expect.amqp.routing_key`
- **AND** `mock.expect.amqp.queue` is omitted or empty
- **WHEN** AMQP matching is evaluated
- **THEN** the queue is evaluated as the routing key

### Requirement: Simulated Evaluation Context
The system SHALL merge provided `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects into one template context for evaluation. (adapts template-rendering/add-http-yaml-mock-server/template-context)

#### Scenario: HTTP context fields
- **GIVEN** `context.http_context` includes `method`, `path`, `body`, `headers`, and `query_string`
- **WHEN** the mock is evaluated
- **THEN** those fields are available to HTTP matching and template rendering

#### Scenario: Kafka context fields
- **GIVEN** `context.kafka_context` includes `topic` and `payload`
- **WHEN** the mock is evaluated
- **THEN** those fields are available to Kafka matching and template rendering

#### Scenario: AMQP context fields
- **GIVEN** `context.amqp_context` includes `exchange`, `routing_key`, `queue`, and `payload`
- **WHEN** the mock is evaluated
- **THEN** those fields are available to AMQP matching and template rendering

#### Scenario: gRPC context fields
- **GIVEN** `context.grpc_context` includes `service`, `method`, `payload`, and `headers`
- **WHEN** the mock is evaluated
- **THEN** those fields are available to gRPC matching and template rendering

### Requirement: Evaluation Flow
The system SHALL evaluate channel-specific matching before condition rendering and shall treat an empty condition as passing.

#### Scenario: Matcher fails
- **GIVEN** the simulated channel context does not match the mock's declared matcher
- **WHEN** the mock is evaluated
- **THEN** the response contains `expect_passed: false`
- **AND** `actions_performed` is empty

#### Scenario: Condition fails
- **GIVEN** the simulated channel context matches the mock's declared matcher
- **AND** the rendered condition does not evaluate to `true`
- **WHEN** the mock is evaluated
- **THEN** the response contains `expect_passed: true`
- **AND** the response contains `condition_passed: false`
- **AND** the response contains the raw `condition_rendered` string
- **AND** `actions_performed` is empty

#### Scenario: Empty condition passes
- **GIVEN** the simulated channel context matches the mock's declared matcher
- **AND** the mock condition is empty
- **WHEN** the mock is evaluated
- **THEN** the response contains `condition_passed: true`

### Requirement: Dry-Run Action Results
The system SHALL evaluate actions in ascending `order` without executing side effects and return rendered action results only for `reply_http` and `publish_kafka`.

#### Scenario: Reply HTTP result
- **GIVEN** matching and condition evaluation pass
- **AND** the mock includes a `reply_http` action
- **WHEN** actions are evaluated
- **THEN** `actions_performed` includes a `reply_http_action_performed` result
- **AND** the result includes `status_code`, `content_type`, `body`, and `headers`
- **AND** `status_code` is a string
- **AND** `content_type` defaults to `application/json` when omitted
- **AND** generated `Content-Type` and `Content-Length` headers are included

#### Scenario: Publish Kafka result
- **GIVEN** matching and condition evaluation pass
- **AND** the mock includes a `publish_kafka` action
- **WHEN** actions are evaluated
- **THEN** `actions_performed` includes a `publish_kafka_action_performed` result
- **AND** the result includes `topic` and `payload`

#### Scenario: Other action types remain dry-run only
- **GIVEN** matching and condition evaluation pass
- **AND** the mock includes an action other than `reply_http` or `publish_kafka`
- **WHEN** actions are evaluated
- **THEN** the action does not execute side effects
- **AND** no rendered action result for that action is included in `actions_performed`
