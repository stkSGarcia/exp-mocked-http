## Purpose

Define dry-run mock evaluation for submitted mock definitions and simulated channel contexts without executing side effects.

## Requirements

### Requirement: Dry-Run Evaluation Request
The system SHALL evaluate one submitted mock definition against one simulated context object without executing side effects.

#### Scenario: Evaluation request accepts one mock and one context object
- **WHEN** a client submits an evaluation request
- **THEN** the request body SHALL contain `mock` as one mock definition object and `context` as one JSON object

#### Scenario: Context object may include multiple channel contexts
- **WHEN** the evaluation request includes `http_context`, `kafka_context`, `amqp_context`, or `grpc_context` under `context`
- **THEN** the system SHALL merge all provided channel sub-objects into one template context for rendering

#### Scenario: Context array is rejected
- **WHEN** the evaluation request provides `context` as an array
- **THEN** the system SHALL reject the request as invalid

### Requirement: Dry-Run Evaluation Validation
The system SHALL reject invalid evaluation requests with `400 Bad Request`.

#### Scenario: Missing mock key is rejected
- **WHEN** the submitted `mock.key` is missing or empty
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing supported matcher is rejected
- **WHEN** the submitted mock does not include at least one supported matcher among `expect.http`, `expect.kafka`, `expect.amqp`, or `expect.grpc`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing required matcher fields are rejected
- **WHEN** a declared matcher omits required fields for its channel
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing required channel context is rejected
- **WHEN** the submitted mock declares a matcher but `context` does not include the matching channel context needed to evaluate it
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: AMQP queue defaults for evaluation
- **WHEN** `mock.expect.amqp.exchange` and `mock.expect.amqp.routing_key` are present but `mock.expect.amqp.queue` is omitted or empty
- **THEN** evaluation SHALL treat the expected queue as `routing_key`

### Requirement: Dry-Run Matching And Conditions
The system SHALL check channel-specific matching before condition rendering and report match and condition results separately.

#### Scenario: Matcher failure returns no performed actions
- **WHEN** the simulated channel context does not match the submitted mock's declared matcher
- **THEN** the system SHALL return `expect_passed` as `false` and `actions_performed` as an empty array

#### Scenario: Empty condition passes
- **WHEN** the simulated channel context matches and `expect.condition` is absent or empty
- **THEN** the system SHALL return `expect_passed` as `true` and `condition_passed` as `true`

#### Scenario: Condition renders true
- **WHEN** the simulated channel context matches and `expect.condition` renders exactly `true`
- **THEN** the system SHALL return `expect_passed` as `true`, `condition_passed` as `true`, and `condition_rendered` as the raw rendered condition output

#### Scenario: Condition renders non-true
- **WHEN** the simulated channel context matches and `expect.condition` renders any value other than exactly `true`
- **THEN** the system SHALL return `expect_passed` as `true`, `condition_passed` as `false`, `condition_rendered` as the raw rendered condition output, and `actions_performed` as an empty array

### Requirement: Dry-Run Action Results
The system SHALL sort actions by effective `order` and return rendered dry-run results only for supported action result types.

#### Scenario: HTTP reply action result is returned
- **WHEN** matching and condition evaluation pass and an ordered action contains `reply_http`
- **THEN** the system SHALL include a `reply_http_action_performed` result with string `status_code`, `content_type`, `body`, and `headers`

#### Scenario: HTTP reply result includes generated headers
- **WHEN** evaluation returns a `reply_http_action_performed` result
- **THEN** the result headers SHALL include generated `Content-Type` and `Content-Length`, defaulting content type to `application/json` when not configured

#### Scenario: Kafka publish action result is returned
- **WHEN** matching and condition evaluation pass and an ordered action contains `publish_kafka`
- **THEN** the system SHALL include a `publish_kafka_action_performed` result with rendered `topic` and `payload`

#### Scenario: Unsupported action result types are omitted
- **WHEN** matching and condition evaluation pass and ordered actions contain side-effecting or unsupported actions other than `reply_http` or `publish_kafka`
- **THEN** the system SHALL NOT execute those actions and SHALL omit them from `actions_performed`

#### Scenario: Action ordering is preserved in dry-run results
- **WHEN** multiple actions have different or equal effective `order` values
- **THEN** the returned supported action results SHALL follow the same stable ascending action order used by live execution

### Requirement: Dry-Run Side Effect Isolation
The system SHALL NOT execute side effects during evaluation.

#### Scenario: Redis action is not executed
- **WHEN** evaluation processes a mock containing a `redis` action
- **THEN** the system SHALL NOT mutate Redis or call a Redis backend

#### Scenario: Outbound network actions are not executed
- **WHEN** evaluation processes a mock containing `send_http`, `publish_kafka`, `publish_amqp`, or `reply_grpc`
- **THEN** the system SHALL NOT perform outbound HTTP, broker publish, or gRPC network side effects

#### Scenario: Sleep action is not executed
- **WHEN** evaluation processes a mock containing a `sleep` action
- **THEN** the system SHALL NOT delay evaluation for the configured duration
