## ADDED Requirements

> Extends: http-behavior-mocking/add-http-yaml-mock-server

### Requirement: Evaluation Endpoint
The system SHALL provide `POST /api/v1/evaluate` to evaluate one mock definition against simulated channel context without executing side effects.

#### Scenario: Valid evaluation request is accepted
- **GIVEN** a request body contains `mock` with one mock definition and `context` with one JSON object
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the system SHALL validate the mock definition and simulated context
- **AND** return the match and render result

#### Scenario: Context object is not an array
- **GIVEN** an evaluation request contains `context` as an array
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Invalid evaluation request is rejected
- **GIVEN** an evaluation request fails validation
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the system SHALL return `400 Bad Request`

### Requirement: Evaluation Request Validation
The system SHALL require `mock.key`, at least one supported matcher, matcher-specific required fields, and the simulated channel context required by each declared matcher.

#### Scenario: Missing key is rejected
- **GIVEN** an evaluation request contains `mock.key` as empty or absent
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing supported matcher is rejected
- **GIVEN** an evaluation request contains a mock without `expect.http`, `expect.kafka`, `expect.amqp`, or `expect.grpc`
- **WHEN** the client posts to `/api/v1/evaluate`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing matcher context is rejected
- **GIVEN** an evaluation request declares a supported matcher
- **WHEN** `context` omits that matcher's required simulated channel context
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: AMQP queue defaults to routing key
- **GIVEN** an evaluation request contains `expect.amqp.exchange` and `expect.amqp.routing_key` with no `expect.amqp.queue`
- **WHEN** the system evaluates the AMQP matcher
- **THEN** the system SHALL evaluate the queue as the routing key

### Requirement: Simulated Channel Context
The system SHALL merge provided `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` sub-objects into one template context for evaluation.

#### Scenario: HTTP context maps to template fields
- **GIVEN** `context.http_context` includes method, path, body, headers, and query string
- **WHEN** the system evaluates a mock with `expect.http`
- **THEN** the template context SHALL expose the corresponding HTTP request fields

#### Scenario: Kafka context maps to template fields
- **GIVEN** `context.kafka_context` includes topic and payload
- **WHEN** the system evaluates a mock with `expect.kafka`
- **THEN** the template context SHALL expose the corresponding Kafka fields

#### Scenario: AMQP context maps to template fields
- **GIVEN** `context.amqp_context` includes exchange, routing key, queue, and payload
- **WHEN** the system evaluates a mock with `expect.amqp`
- **THEN** the template context SHALL expose the corresponding AMQP fields

#### Scenario: gRPC context maps to template fields
- **GIVEN** `context.grpc_context` includes service, method, payload, and headers
- **WHEN** the system evaluates a mock with `expect.grpc`
- **THEN** the template context SHALL expose `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader`

### Requirement: Dry-Run Matching And Conditions
The system SHALL check channel-specific matching before rendering conditions, treat an empty condition as passing, and never execute side effects during evaluation (adapts http-behavior-mocking/add-http-yaml-mock-server/method-and-path-matching).

#### Scenario: Matcher failure short-circuits
- **GIVEN** the simulated context does not satisfy the declared matcher
- **WHEN** the system evaluates the mock
- **THEN** the response SHALL include `expect_passed: false`
- **AND** `actions_performed` SHALL be empty

#### Scenario: Empty condition passes
- **GIVEN** the simulated context satisfies the declared matcher and the mock omits `expect.condition`
- **WHEN** the system evaluates the mock
- **THEN** the response SHALL include `expect_passed: true` and `condition_passed: true`

#### Scenario: Condition failure returns rendered condition
- **GIVEN** the simulated context satisfies the declared matcher
- **WHEN** the rendered condition is not exactly `true`
- **THEN** the response SHALL include `expect_passed: true`, `condition_passed: false`, and `condition_rendered`
- **AND** `actions_performed` SHALL be empty

### Requirement: Dry-Run Action Results
The system SHALL sort actions by effective `order` and evaluate renderable action results without executing side effects (adapts http-behavior-mocking/add-stateful-actions/action-execution).

#### Scenario: HTTP reply result is returned
- **GIVEN** matching and condition evaluation pass and an action contains `reply_http`
- **WHEN** the system evaluates the mock
- **THEN** `actions_performed` SHALL include a `reply_http_action_performed` result with `status_code`, `content_type`, `body`, and `headers`

#### Scenario: Kafka publish result is returned
- **GIVEN** matching and condition evaluation pass and an action contains `publish_kafka`
- **WHEN** the system evaluates the mock
- **THEN** `actions_performed` SHALL include a `publish_kafka_action_performed` result with `topic` and `payload`

#### Scenario: Unsupported action result is omitted
- **GIVEN** matching and condition evaluation pass and an action contains any action other than `reply_http` or `publish_kafka`
- **WHEN** the system evaluates the mock
- **THEN** the system SHALL NOT execute that action
- **AND** `actions_performed` SHALL omit that action

#### Scenario: Action order is stable
- **GIVEN** matching and condition evaluation pass and multiple supported actions are present
- **WHEN** the system evaluates action results
- **THEN** the system SHALL sort actions by ascending `order`
- **AND** preserve declared order for equal effective `order` values
