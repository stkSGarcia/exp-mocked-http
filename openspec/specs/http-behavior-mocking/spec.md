## Purpose

Define the HTTP request matching and action execution behavior for `hmock.py`.

## Requirements

### Requirement: HTTP Server Entry Point
The system SHALL provide `hmock.py` as the HTTP mock server entry point.

#### Scenario: Server starts with uv
- **WHEN** `uv run --project /app hmock.py` is executed in the application environment
- **THEN** the system SHALL start the HTTP mock server using the configured host, port, templates directory, and log level

### Requirement: Method And Path Matching
The system SHALL match HTTP requests against behaviors by `expect.http.method` and `expect.http.path`.

#### Scenario: Exact method and path match
- **WHEN** a request method and path exactly match a behavior's `expect.http.method` and `expect.http.path`
- **THEN** the behavior SHALL be eligible for condition evaluation and action execution

#### Scenario: Method mismatch
- **WHEN** a request path matches but the request method differs from `expect.http.method`
- **THEN** the behavior SHALL NOT match the request

#### Scenario: Query string excluded from route matching
- **WHEN** a request path matches `expect.http.path` and includes a query string
- **THEN** the system SHALL match the route using the path without the query string

### Requirement: Named Path Parameters
The system SHALL support named path parameters in behavior paths using `:param` syntax.

#### Scenario: Named parameter captures segment
- **WHEN** a behavior expects `/api/:id/resource` and a request uses `/api/42/resource`
- **THEN** the behavior SHALL match and capture `id` with value `42`

#### Scenario: Named parameter does not cross segment boundary
- **WHEN** a behavior expects `/api/:id/resource` and a request uses `/api/42/extra/resource`
- **THEN** the behavior SHALL NOT match

#### Scenario: Captures are available to templates
- **WHEN** a behavior with named path parameters matches a request
- **THEN** the captured values SHALL be available through the request URL template context

### Requirement: Condition Routing
The system SHALL evaluate matching behaviors in load order and use the first behavior whose condition passes.

#### Scenario: Missing condition passes
- **WHEN** a behavior matches method and path and omits `expect.condition`
- **THEN** the behavior SHALL be selected

#### Scenario: Empty condition passes
- **WHEN** a behavior matches method and path and has an empty `expect.condition`
- **THEN** the behavior SHALL be selected

#### Scenario: Condition must render true
- **WHEN** a behavior matches method and path and its condition renders exactly `true`
- **THEN** the behavior SHALL be selected

#### Scenario: Condition renders non-true
- **WHEN** a behavior matches method and path and its condition renders any value other than exactly `true`
- **THEN** the behavior SHALL NOT match

#### Scenario: Condition render failure
- **WHEN** a behavior matches method and path but condition rendering fails
- **THEN** the behavior SHALL NOT match and later behaviors SHALL still be evaluated

### Requirement: Action Execution
The system SHALL execute the selected behavior's actions in stable ascending `order` and stop evaluating further behaviors.

#### Scenario: Sleep delays next action
- **WHEN** a selected behavior contains a `sleep` action with a supported duration
- **THEN** the system SHALL pause for that duration before executing the next ordered action

#### Scenario: Unsupported sleep duration is invalid
- **WHEN** a `sleep` action uses a duration without one of `ns`, `us`, `ms`, `s`, `m`, or `h`
- **THEN** the system SHALL reject the action as invalid

#### Scenario: Reply action sends response
- **WHEN** a selected behavior executes `reply_http`
- **THEN** the system SHALL send the configured HTTP status, rendered headers, and rendered body

#### Scenario: Redis action renders command templates in order
- **WHEN** a selected behavior contains a `redis` action with multiple command template strings
- **THEN** the system SHALL render each command template independently and execute the rendered Redis commands in array order

#### Scenario: Outbound HTTP action renders request fields
- **WHEN** a selected behavior executes `send_http`
- **THEN** the system SHALL render the action's `url`, header values, and body using the same request context and template functions available to response bodies

#### Scenario: Outbound HTTP file body renders
- **WHEN** a selected behavior executes `send_http` with `body_from_file`
- **THEN** the system SHALL render the loaded file content as the outbound HTTP request body

#### Scenario: Outbound HTTP inline body takes precedence
- **WHEN** a `send_http` action defines both a non-empty `body` and `body_from_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Outbound HTTP failure does not replace inbound response
- **WHEN** a selected behavior executes `send_http` and the outbound request fails
- **THEN** the system SHALL continue mock action execution and preserve the inbound response produced by the behavior

#### Scenario: Mixed actions with equal order execute in declared order
- **WHEN** a selected behavior mixes `redis`, `send_http`, `sleep`, and `reply_http` actions and those actions have the same effective `order`
- **THEN** the system SHALL execute those actions in the order declared by the effective behavior

#### Scenario: Actions are sorted by ascending order
- **WHEN** a selected behavior contains actions with different `order` values
- **THEN** the system SHALL execute lower order values before higher order values

#### Scenario: Missing action order defaults to zero
- **WHEN** a selected behavior contains an action without `order`
- **THEN** the system SHALL treat that action's order as `0`

#### Scenario: Negative action order is accepted
- **WHEN** a selected behavior contains an action with a negative `order`
- **THEN** the system SHALL execute that action before actions with greater order values

#### Scenario: Equal action order is stable
- **WHEN** a selected behavior contains multiple actions with the same effective `order`
- **THEN** the system SHALL preserve those actions' original relative order

#### Scenario: Inherited actions are included in ordering
- **WHEN** a selected behavior includes actions inherited from a parent and actions declared on the child
- **THEN** the system SHALL sort all inherited and child actions together by effective `order`

### Requirement: HTTP Broker Publish Actions
The system SHALL execute broker publish actions from HTTP-selected behaviors using the existing ordered action execution model.

#### Scenario: HTTP behavior publishes Kafka message
- **WHEN** a selected HTTP behavior executes `publish_kafka`
- **THEN** the system SHALL render and publish the Kafka message without replacing the inbound HTTP response

#### Scenario: HTTP behavior publishes AMQP message
- **WHEN** a selected HTTP behavior executes `publish_amqp`
- **THEN** the system SHALL render and publish the AMQP message without replacing the inbound HTTP response

#### Scenario: Broker publish actions respect order
- **WHEN** a selected HTTP behavior mixes `publish_kafka`, `publish_amqp`, `redis`, `send_http`, `sleep`, and `reply_http` actions with different effective `order` values
- **THEN** the system SHALL execute lower order values before higher order values

#### Scenario: Broker publish actions preserve equal order
- **WHEN** a selected HTTP behavior mixes broker publish actions with other actions that have the same effective `order`
- **THEN** the system SHALL preserve those actions' original relative order

#### Scenario: Kafka publish failure preserves inbound response
- **WHEN** a selected HTTP behavior executes `publish_kafka` and the publish fails
- **THEN** the system SHALL continue mock action execution and preserve the inbound response produced by the behavior

#### Scenario: AMQP publish failure preserves inbound response
- **WHEN** a selected HTTP behavior executes `publish_amqp` and the publish fails
- **THEN** the system SHALL continue mock action execution and preserve the inbound response produced by the behavior

### Requirement: HTTP Response Defaults
The system SHALL apply HTTP response defaults and framing for `reply_http` actions.

#### Scenario: Content type defaults to JSON
- **WHEN** a `reply_http` action omits a `Content-Type` header
- **THEN** the system SHALL set `Content-Type` to `application/json`

#### Scenario: Explicit content type is preserved
- **WHEN** a `reply_http` action defines a `Content-Type` header
- **THEN** the system SHALL use the configured header value

#### Scenario: Content length is computed
- **WHEN** a `reply_http` response body is rendered
- **THEN** the system SHALL set `Content-Length` to the rendered body length

#### Scenario: Missing body defaults to empty
- **WHEN** a `reply_http` action omits `body`
- **THEN** the system SHALL render and send an empty response body

### Requirement: File-Backed HTTP Response Body
The system SHALL support response bodies loaded from files for `reply_http` actions.

#### Scenario: File-backed body renders
- **WHEN** a selected behavior executes `reply_http` with `body_from_file`
- **THEN** the system SHALL render the loaded file content as the HTTP response body

#### Scenario: File-backed body uses request template context
- **WHEN** a loaded response body file contains template expressions
- **THEN** the system SHALL render those expressions with the same request context and template functions available to inline response bodies

#### Scenario: Inline body takes precedence
- **WHEN** a `reply_http` action defines both a non-empty `body` and `body_from_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline body uses file-backed body
- **WHEN** a `reply_http` action defines `body_from_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL render and send the loaded file-backed body

### Requirement: Templated HTTP Response Headers
The system SHALL render every configured `reply_http.headers` value as a template.

#### Scenario: Header value uses request context
- **WHEN** a selected behavior executes `reply_http` with a header value containing a template expression
- **THEN** the system SHALL render the header value using the same request context and template functions available to response bodies

### Requirement: Active Mock Reload Visibility
The system SHALL serve mock requests from the latest active mock set after admin mutations are reloaded.

#### Scenario: Added template becomes matchable
- **WHEN** an admin mutation adds a mock definition and the bounded reload window has elapsed
- **THEN** a later matching mock request SHALL be evaluated against that added definition

#### Scenario: Updated template replaces previous active behavior
- **WHEN** an admin mutation updates a mock definition with a key that already exists and the bounded reload window has elapsed
- **THEN** a later matching mock request SHALL use the latest active definition selected by the duplicate-key merge rule

#### Scenario: Deleted base template stops matching
- **WHEN** an admin mutation deletes a base API-added mock and no filesystem mock or template-set mock with the same key remains active after the bounded reload window
- **THEN** a later request that only matched the deleted mock SHALL return the unmatched HTTP response

#### Scenario: Filesystem template remains after API delete
- **WHEN** an admin mutation deletes a base API-added mock with the same key as a filesystem mock and the bounded reload window has elapsed
- **THEN** a later matching mock request SHALL still be able to select the filesystem mock

### Requirement: Unmatched HTTP Request
The system SHALL return a 404 response for requests with no matching behavior.

#### Scenario: No matching behavior
- **WHEN** no loaded behavior matches the request method, path, and condition
- **THEN** the system SHALL return status `404 Not Found` with response body exactly `not found`

### Requirement: Mock HTTP CORS
The system SHALL optionally add global CORS headers to responses from the mock HTTP server.

#### Scenario: CORS disabled by default
- **WHEN** the server starts without `HM_CORS_ENABLED`
- **THEN** responses from the mock HTTP server SHALL NOT receive global CORS headers unless a mock defines them

#### Scenario: CORS headers are added when enabled
- **WHEN** `HM_CORS_ENABLED=true` and the mock HTTP server sends a response
- **THEN** the response SHALL include `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`

#### Scenario: Mock CORS headers are preserved
- **WHEN** `HM_CORS_ENABLED=true` and `reply_http.headers` defines a CORS header also set by the global middleware
- **THEN** the response SHALL use the mock-defined header value for that header

#### Scenario: Explicit OPTIONS behavior takes precedence
- **WHEN** `HM_CORS_ENABLED=true` and an `OPTIONS` request matches a loaded mock behavior
- **THEN** the system SHALL execute the matched mock behavior

#### Scenario: Unmatched OPTIONS request becomes preflight
- **WHEN** `HM_CORS_ENABLED=true` and an `OPTIONS` request matches no loaded behavior
- **THEN** the system SHALL return `200 OK` with an empty body and the global CORS headers

### Requirement: Binary HTTP Response Body
The system SHALL support binary response bodies loaded from files for `reply_http` actions.

#### Scenario: Binary response sends bytes as-is
- **WHEN** a selected behavior executes `reply_http` with `body_from_binary_file` and no non-empty `body`
- **THEN** the system SHALL send the snapshotted binary bytes without template rendering

#### Scenario: Binary response content length is computed from bytes
- **WHEN** a selected behavior sends a binary response body
- **THEN** the system SHALL set `Content-Length` to the binary byte length

#### Scenario: Binary response filename sets content disposition
- **WHEN** a selected behavior executes `reply_http` with `body_from_binary_file` and `binary_file_name`
- **THEN** the system SHALL add `Content-Disposition: inline; filename="<binary_file_name>"`

#### Scenario: Inline body takes precedence over binary file body
- **WHEN** a `reply_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline body uses binary file body
- **WHEN** a `reply_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL send the snapshotted binary file body

### Requirement: Binary Outbound HTTP Body
The system SHALL support binary request bodies loaded from files for `send_http` actions.

#### Scenario: POST binary file sends multipart form data
- **WHEN** a selected behavior executes `send_http` with method `POST` and `body_from_binary_file`
- **THEN** the outbound request SHALL send multipart form data using form field name `file`

#### Scenario: Multipart upload uses configured filename
- **WHEN** a `send_http` POST action defines `body_from_binary_file` and `binary_file_name`
- **THEN** the multipart file part SHALL use `binary_file_name` as the uploaded filename

#### Scenario: Multipart upload defaults filename to basename
- **WHEN** a `send_http` POST action defines `body_from_binary_file` and omits `binary_file_name`
- **THEN** the multipart file part SHALL use the basename of `body_from_binary_file` as the uploaded filename

#### Scenario: Multipart upload defaults content type
- **WHEN** a `send_http` POST action defines `body_from_binary_file` without an overriding content type header
- **THEN** the file part content type SHALL be `application/octet-stream`

#### Scenario: Non-POST binary file sends raw body
- **WHEN** a selected behavior executes `send_http` with a non-POST method and `body_from_binary_file`
- **THEN** the outbound request SHALL send the snapshotted binary bytes as the raw request body

#### Scenario: Inline outbound body takes precedence over binary file body
- **WHEN** a `send_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty outbound inline body uses binary file body
- **WHEN** a `send_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL send the snapshotted binary file body
