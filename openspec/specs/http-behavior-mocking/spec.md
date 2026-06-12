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
The system SHALL execute the selected behavior's actions in their declared order and stop evaluating further behaviors.

#### Scenario: Sleep delays next action
- **WHEN** a selected behavior contains a `sleep` action with a supported duration
- **THEN** the system SHALL pause for that duration before executing the next action

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

#### Scenario: Mixed actions execute in declared order
- **WHEN** a selected behavior mixes `redis`, `send_http`, `sleep`, and `reply_http` actions
- **THEN** the system SHALL execute those actions in the order declared by the behavior

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

### Requirement: Unmatched HTTP Request
The system SHALL return a 404 response for requests with no matching behavior.

#### Scenario: No matching behavior
- **WHEN** no loaded behavior matches the request method, path, and condition
- **THEN** the system SHALL return status `404 Not Found` with response body exactly `not found`
