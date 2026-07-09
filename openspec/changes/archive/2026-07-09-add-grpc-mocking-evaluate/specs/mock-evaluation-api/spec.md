## ADDED Requirements

> Extends: mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering
> Extends: template-rendering/add-admin-template-storage
> Extends: mock-definition-loading/add-stateful-actions

### Requirement: Evaluation Endpoint
The system SHALL expose `POST /api/v1/evaluate` to accept one mock definition and one simulated channel context object, evaluate the mock without executing side effects, and return the match and render result.

#### Scenario: Evaluation accepts one mock and context object
- **GIVEN** a request body contains `mock` and `context`
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the system evaluates only that mock definition against the provided context object

#### Scenario: Evaluation does not execute side effects
- **GIVEN** a mock contains actions that would publish, send, store, or otherwise mutate external state
- **WHEN** the mock is evaluated through `/api/v1/evaluate`
- **THEN** the system does not execute those side effects

### Requirement: Evaluation Request Validation
The system SHALL return `400 Bad Request` when an evaluation request is invalid, including when `mock.key` is empty, no supported matcher is declared, a declared matcher is missing required fields, or the context required by the declared matcher is absent. (adapts mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering/behavior-schema-validation)

#### Scenario: Missing mock key rejected
- **GIVEN** an evaluation request contains an empty `mock.key`
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the response status is `400 Bad Request`

#### Scenario: Missing matcher context rejected
- **GIVEN** a mock declares `expect.grpc`
- **AND** `context.grpc_context` is absent
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the response status is `400 Bad Request`

### Requirement: Channel Context Merging
The system SHALL accept `context` as a single object containing any combination of `http_context`, `kafka_context`, `amqp_context`, and `grpc_context`, and SHALL merge the provided channel sub-objects into one template context.

#### Scenario: Multiple simulated contexts merge
- **GIVEN** an evaluation request includes both `http_context` and `kafka_context`
- **WHEN** a template renders during evaluation
- **THEN** the template context includes values from both provided sub-objects

#### Scenario: Context array rejected
- **GIVEN** an evaluation request provides `context` as an array
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the response status is `400 Bad Request`

### Requirement: Evaluation Matching and Conditions
The system SHALL perform channel-specific matching before condition rendering, treat an empty condition as passing, and return empty `actions_performed` when matching or conditions fail.

#### Scenario: Matcher failure short-circuits evaluation
- **GIVEN** a mock expectation does not match the simulated channel context
- **WHEN** the mock is evaluated
- **THEN** the response contains `expect_passed: false`
- **AND** `actions_performed` is empty

#### Scenario: Condition failure reported
- **GIVEN** a mock expectation matches the simulated channel context
- **AND** the rendered condition is not `true`
- **WHEN** the mock is evaluated
- **THEN** the response contains `expect_passed: true`
- **AND** `condition_passed: false`
- **AND** `condition_rendered` contains the raw rendered condition output
- **AND** `actions_performed` is empty

### Requirement: Evaluation Action Results
The system SHALL sort actions by `order`, evaluate them without side effects, include rendered results only for `reply_http` and `publish_kafka`, and omit every other action type from `actions_performed`.

#### Scenario: HTTP reply dry-run result returned
- **GIVEN** matching and condition evaluation pass
- **AND** the mock includes a `reply_http` action
- **WHEN** the mock is evaluated
- **THEN** `actions_performed` includes a `reply_http_action_performed` result with `status_code`, `content_type`, `body`, and `headers`
- **AND** the result defaults `content_type` to `application/json` when absent
- **AND** the result headers include generated `Content-Type` and `Content-Length`

#### Scenario: Kafka publish dry-run result returned
- **GIVEN** matching and condition evaluation pass
- **AND** the mock includes a `publish_kafka` action
- **WHEN** the mock is evaluated
- **THEN** `actions_performed` includes a `publish_kafka_action_performed` result with rendered `topic` and `payload`

#### Scenario: Unsupported action dry-run result omitted
- **GIVEN** matching and condition evaluation pass
- **AND** the mock includes an action other than `reply_http` or `publish_kafka`
- **WHEN** the mock is evaluated
- **THEN** that action is not included in `actions_performed`
