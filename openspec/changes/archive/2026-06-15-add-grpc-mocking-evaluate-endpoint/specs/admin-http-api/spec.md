## ADDED Requirements

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
