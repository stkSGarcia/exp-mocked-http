## Purpose

Define the dry-run evaluation API behavior for validating a single mock definition against simulated channel context without executing side effects.

## Requirements

### Requirement: Evaluation Request Shape
The system SHALL accept a dry-run evaluation request containing one mock definition and one simulated channel context object.

#### Scenario: Evaluate request accepts mock and context
- **WHEN** an admin client sends `POST /api/v1/evaluate` with a JSON object containing `mock` and `context`
- **THEN** the system SHALL parse `mock` as one mock definition and `context` as one object containing simulated channel sub-objects

#### Scenario: Context is not an array
- **WHEN** an evaluation request sends `context` as an array
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Multiple channel contexts merge
- **WHEN** an evaluation request includes more than one supported channel context sub-object
- **THEN** the system SHALL merge the provided sub-objects into one template context for condition and action rendering

### Requirement: Evaluation Validation
The system SHALL validate the submitted mock and simulated context before dry-run evaluation.

#### Scenario: Missing mock key is rejected
- **WHEN** an evaluation request contains a mock without a non-empty `key`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing supported matcher is rejected
- **WHEN** an evaluation request contains a mock whose `expect` omits `http`, `kafka`, `amqp`, and `grpc`
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing matcher required fields are rejected
- **WHEN** an evaluation request declares a supported matcher without that matcher's required fields
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: Missing channel context is rejected
- **WHEN** an evaluation request declares a matcher and omits the corresponding simulated channel context
- **THEN** the system SHALL return `400 Bad Request`

#### Scenario: AMQP queue defaults to routing key
- **WHEN** an evaluation request contains `expect.amqp.exchange` and `expect.amqp.routing_key` but omits `expect.amqp.queue`
- **THEN** the system SHALL evaluate the AMQP expectation using the routing key as the effective queue

### Requirement: Evaluation Context Fields
The system SHALL support simulated HTTP, Kafka, AMQP, and gRPC context sub-objects for dry-run evaluation.

#### Scenario: HTTP context fields are available
- **WHEN** an evaluation request includes `context.http_context`
- **THEN** the evaluation template context SHALL include HTTP method, path, body, headers, and query string from that object

#### Scenario: Kafka context fields are available
- **WHEN** an evaluation request includes `context.kafka_context`
- **THEN** the evaluation template context SHALL include Kafka topic and payload from that object

#### Scenario: AMQP context fields are available
- **WHEN** an evaluation request includes `context.amqp_context`
- **THEN** the evaluation template context SHALL include AMQP exchange, routing key, effective queue, and payload from that object

#### Scenario: gRPC context fields are available
- **WHEN** an evaluation request includes `context.grpc_context`
- **THEN** the evaluation template context SHALL include gRPC service, method, payload JSON string, and metadata headers from that object

### Requirement: Evaluation Matching And Condition
The system SHALL check channel-specific matching before rendering the mock condition.

#### Scenario: Matcher failure returns false expectation
- **WHEN** the simulated channel context does not match the mock expectation
- **THEN** the response SHALL include `expect_passed: false` and an empty `actions_performed` array

#### Scenario: Empty condition passes
- **WHEN** the simulated channel context matches and the mock omits `expect.condition` or sets it to an empty string
- **THEN** the response SHALL include `expect_passed: true` and `condition_passed: true`

#### Scenario: Condition renders true
- **WHEN** the simulated channel context matches and the condition renders exactly `true`
- **THEN** the response SHALL include `expect_passed: true`, `condition_passed: true`, and the rendered condition string

#### Scenario: Condition renders non-true
- **WHEN** the simulated channel context matches and the condition renders any value other than exactly `true`
- **THEN** the response SHALL include `expect_passed: true`, `condition_passed: false`, the rendered condition string, and an empty `actions_performed` array

### Requirement: Evaluation Action Results
The system SHALL sort actions by effective `order` and render supported action results without executing side effects.

#### Scenario: Supported actions are sorted before evaluation
- **WHEN** a matching mock contains actions with different effective `order` values
- **THEN** the system SHALL evaluate lower order values before higher order values while preserving declared order for equal order values

#### Scenario: HTTP reply action result is returned
- **WHEN** a matching mock performs a `reply_http` action during evaluation
- **THEN** `actions_performed` SHALL include a `reply_http_action_performed` result with `status_code`, `content_type`, `body`, and `headers`

#### Scenario: HTTP reply result includes generated headers
- **WHEN** evaluation returns a `reply_http_action_performed` result
- **THEN** the result headers SHALL include generated `Content-Type` and `Content-Length` values

#### Scenario: HTTP reply content type defaults to JSON
- **WHEN** evaluation renders a `reply_http` action without a configured `Content-Type`
- **THEN** the `reply_http_action_performed` result SHALL use `application/json` as `content_type`

#### Scenario: Kafka publish action result is returned
- **WHEN** a matching mock performs a `publish_kafka` action during evaluation
- **THEN** `actions_performed` SHALL include a `publish_kafka_action_performed` result with rendered `topic` and `payload`

#### Scenario: Unsupported action type is omitted
- **WHEN** a matching mock contains an action type other than `reply_http` or `publish_kafka`
- **THEN** the system SHALL NOT execute the action and SHALL omit that action from `actions_performed`

### Requirement: Evaluation Side Effects
The system SHALL NOT execute side effects while evaluating a mock.

#### Scenario: Broker publish is not executed
- **WHEN** evaluation renders a `publish_kafka` action result
- **THEN** the system SHALL NOT send a message to Kafka

#### Scenario: Redis action is not executed
- **WHEN** evaluation sees a `redis` action
- **THEN** the system SHALL NOT execute the Redis command

#### Scenario: Outbound HTTP action is not executed
- **WHEN** evaluation sees a `send_http` action
- **THEN** the system SHALL NOT send an outbound HTTP request

#### Scenario: Sleep action does not delay evaluation
- **WHEN** evaluation sees a `sleep` action
- **THEN** the system SHALL NOT sleep before returning the response
