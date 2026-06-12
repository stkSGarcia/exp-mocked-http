## ADDED Requirements

> Extends: http-yaml-mock-server/add-http-yaml-mock-server

### Requirement: Evaluation endpoint
The system SHALL expose `POST /api/v1/evaluate` and accept a JSON object containing one normal-schema mock definition in `mock` and one object of simulated channel contexts in `context`.

#### Scenario: Combined simulated contexts
- **GIVEN** a request contains two or more supported channel-specific sub-objects under `context`
- **WHEN** the request is evaluated
- **THEN** the system merges the provided sub-objects into one template context

#### Scenario: Context is an array
- **GIVEN** an evaluation request supplies `context` as an array
- **WHEN** the request is validated
- **THEN** the system returns `400 Bad Request`

### Requirement: Evaluation request validation
The system SHALL return `400 Bad Request` unless `mock.key` is non-empty, `mock.expect` declares at least one of `http`, `kafka`, `amqp`, or `grpc`, every declared matcher has its required fields, and `context` supplies the channel context required for each declared matcher.

#### Scenario: Missing supported matcher
- **GIVEN** a mock has no supported matcher under `mock.expect`
- **WHEN** the request is validated
- **THEN** the system returns `400 Bad Request`

#### Scenario: Missing matcher context
- **GIVEN** a mock declares a supported matcher but the corresponding simulated channel context is absent
- **WHEN** the request is validated
- **THEN** the system returns `400 Bad Request`

#### Scenario: AMQP queue omitted
- **GIVEN** `mock.expect.amqp.exchange` and `routing_key` are present and `queue` is omitted or empty
- **WHEN** the AMQP matcher is evaluated
- **THEN** the expected queue is treated as the configured `routing_key`

### Requirement: Simulated channel template context
The system SHALL map supplied HTTP, Kafka, AMQP, and gRPC context fields to the same template variables used by runtime channel processing, including their payload, routing, header, query, service, and method values.

#### Scenario: Render across provided channels
- **GIVEN** an evaluation request provides multiple channel contexts
- **WHEN** a condition or action template references fields from those contexts
- **THEN** all provided channel values are available in the merged template context

### Requirement: Match before condition
The system SHALL evaluate channel-specific matching before rendering the mock condition. Channel matching SHALL use the normal matcher behavior for each declared channel. (adapts http-yaml-mock-server/add-http-yaml-mock-server/http-request-matching)

#### Scenario: Matcher fails
- **GIVEN** the simulated context does not satisfy a declared matcher
- **WHEN** the mock is evaluated
- **THEN** the response has `expect_passed` set to `false`
- **AND** `actions_performed` is empty
- **AND** the condition and actions are not rendered

### Requirement: Condition evaluation
The system SHALL treat an empty condition as passing and otherwise return whether the rendered condition is `true` together with its raw rendered output.

#### Scenario: Empty condition
- **GIVEN** the channel matcher passes and the mock condition is empty
- **WHEN** the mock is evaluated
- **THEN** `expect_passed` and `condition_passed` are `true`

#### Scenario: Condition fails
- **GIVEN** the channel matcher passes and the condition renders to a non-passing value
- **WHEN** the mock is evaluated
- **THEN** `expect_passed` is `true`
- **AND** `condition_passed` is `false`
- **AND** `condition_rendered` contains the raw rendered condition
- **AND** `actions_performed` is empty

### Requirement: Dry-run action evaluation
The system SHALL sort actions by `order` and render them without executing side effects when matching and condition evaluation pass. Only `reply_http` and `publish_kafka` SHALL contribute entries to `actions_performed`; every other action type SHALL be omitted from that array and SHALL NOT execute.

#### Scenario: Ordered supported actions
- **GIVEN** a passing mock has `reply_http` and `publish_kafka` actions with different order values
- **WHEN** the mock is evaluated
- **THEN** `actions_performed` contains their rendered results in action order

#### Scenario: Side-effecting action
- **GIVEN** a passing mock includes an action type other than `reply_http` or `publish_kafka`
- **WHEN** the mock is evaluated
- **THEN** that action performs no external or internal side effect
- **AND** it is omitted from `actions_performed`

### Requirement: HTTP action result
The system SHALL represent a rendered HTTP reply as `reply_http_action_performed` with string `status_code`, `content_type`, `body`, and `headers`. The content type SHALL default to `application/json`, and headers SHALL include generated `Content-Type` and `Content-Length` values.

#### Scenario: Default HTTP result metadata
- **GIVEN** a passing `reply_http` action omits content type
- **WHEN** it is evaluated
- **THEN** its result has `content_type` equal to `application/json`
- **AND** its headers include generated content type and rendered-body content length values

### Requirement: Kafka action result
The system SHALL represent a rendered Kafka publication as `publish_kafka_action_performed` with `topic` and `payload`.

#### Scenario: Render Kafka result
- **GIVEN** a passing `publish_kafka` action
- **WHEN** it is evaluated
- **THEN** its result contains the rendered topic and payload

### Requirement: Evaluation has no side effects
The system MUST NOT execute network calls, broker publications, state changes, delays, process execution, or any other action side effect while handling `POST /api/v1/evaluate`.

#### Scenario: Evaluate side-effect-capable mock
- **GIVEN** a valid passing mock contains one or more side-effect-capable actions
- **WHEN** the evaluation endpoint processes it
- **THEN** no side effect is executed
- **AND** the response contains only eligible rendered action results
