## ADDED Requirements

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
