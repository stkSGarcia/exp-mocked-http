## ADDED Requirements

### Requirement: Server configuration
The system SHALL provide a Python entry point named `hmock.py` that starts an HTTP mock server using environment-based configuration.

#### Scenario: Start server with default configuration
- **WHEN** `uv run --project /app hmock.py` starts without mock-server environment variables
- **THEN** the server listens on host `0.0.0.0`, port `9999`, scans `./templates`, and uses log level `info`

#### Scenario: Start server with overridden configuration
- **WHEN** `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, and `HM_LOG_LEVEL` are set
- **THEN** the server uses those values for template scanning, HTTP binding, and log filtering

### Requirement: YAML mock loading
The system SHALL recursively scan `HM_TEMPLATES_DIR`, load every `.yaml` and `.yml` file, and merge loaded YAML objects into one ordered behavior list.

#### Scenario: Load nested YAML files
- **WHEN** the templates directory contains YAML files in nested directories
- **THEN** the server loads every `.yaml` and `.yml` file and preserves behavior order from the loaded files

#### Scenario: Ignore non-YAML files
- **WHEN** the templates directory contains files without `.yaml` or `.yml` extensions
- **THEN** the server does not load those files as mock definitions

### Requirement: Behavior validation
The system MUST validate loaded behavior definitions before serving requests.

#### Scenario: Valid behavior omits kind
- **WHEN** a behavior has a non-empty string `key`, no `kind`, and valid actions
- **THEN** the server treats its `kind` as `Behavior`

#### Scenario: Missing key is rejected
- **WHEN** a behavior omits `key`
- **THEN** validation rejects that behavior definition

#### Scenario: Empty key is rejected
- **WHEN** a behavior has a `key` that is not a non-empty string
- **THEN** validation rejects that behavior definition

#### Scenario: Multiple HTTP replies are rejected
- **WHEN** a behavior contains more than one `reply_http` action
- **THEN** validation rejects that behavior definition

### Requirement: Duplicate behavior keys
The system SHALL treat duplicate behavior keys as overrides where the last loaded behavior wins and SHALL log a warning for each override.

#### Scenario: Later duplicate key overrides earlier behavior
- **WHEN** multiple loaded behaviors use the same `key`
- **THEN** only the last loaded behavior for that key remains active for request matching

#### Scenario: Duplicate key emits warning
- **WHEN** a later behavior overrides an earlier behavior with the same `key`
- **THEN** the server emits a structured warning log describing the override

### Requirement: HTTP request matching
The system SHALL match behaviors by `expect.http.method`, `expect.http.path`, and optional `expect.condition` in active load order.

#### Scenario: Exact method and path match
- **WHEN** a request method and path equal a behavior's expected HTTP method and path and the behavior has no condition
- **THEN** that behavior matches the request

#### Scenario: Named path parameter match
- **WHEN** a behavior expects a path containing `:param` and a request path has a value in that segment
- **THEN** the behavior matches and the captured parameter value is exposed in the request URL context

#### Scenario: First passing behavior handles request
- **WHEN** multiple behaviors match the request method and path
- **THEN** the first behavior in active load order whose condition passes handles the request and later behaviors are not evaluated

#### Scenario: No matching behavior
- **WHEN** no behavior matches the request method, path, and condition
- **THEN** the server returns status `404 Not Found` with response body exactly `not found`

### Requirement: Condition evaluation
The system SHALL evaluate `expect.condition` as a template expression and treat the behavior as matched only when the rendered output is exactly `true`.

#### Scenario: Missing condition passes
- **WHEN** a behavior has no condition or an empty condition
- **THEN** the condition passes

#### Scenario: Rendered true condition passes
- **WHEN** a behavior condition renders exactly `true`
- **THEN** the condition passes

#### Scenario: Non-true condition fails
- **WHEN** a behavior condition renders any output other than exactly `true`
- **THEN** the condition fails and the behavior does not match

#### Scenario: Condition render error fails behavior
- **WHEN** rendering a behavior condition fails
- **THEN** the behavior does not match and evaluation continues with later behaviors

### Requirement: Template context
The system SHALL provide request data to every condition, response body, and response header template.

#### Scenario: Header context is available
- **WHEN** a template calls `.HTTPHeader.Get "Header-Name"`
- **THEN** it receives the matching request header value from a case-insensitive header map

#### Scenario: Body and URL context are available
- **WHEN** a template references `.HTTPBody`, `.HTTPPath`, or `.HTTPQueryString`
- **THEN** it receives the raw request body, full request URL path including query string, or raw query string without `?`

#### Scenario: Undefined variable is an error
- **WHEN** a template references a variable that is not defined in the context
- **THEN** rendering fails

### Requirement: Template language support
The system MUST support the checkpoint template syntax and functions for conditions, response bodies, and response headers.

#### Scenario: Supported syntax renders
- **WHEN** a template uses expressions, pipelines, conditionals, loops, assignment, raw strings, or whitespace trimming with `{{ ... }}` delimiters
- **THEN** the template renderer evaluates the syntax according to the mock-server template rules

#### Scenario: Template newlines and tabs are normalized
- **WHEN** a template contains `\r\n`, `\n`, or `\t` before parsing
- **THEN** the renderer replaces those characters with spaces before parsing

#### Scenario: Built-in and extended functions render
- **WHEN** a template uses a listed comparison, logic, output, encoding, collection, invocation, string, fallback, environment, math, or UUID function
- **THEN** the renderer evaluates the function and includes its result in the rendered output

### Requirement: HTTP reply action
The system SHALL support `reply_http` actions that render a single HTTP response.

#### Scenario: Reply renders status headers and body
- **WHEN** a matched behavior executes a `reply_http` action with `status_code`, `headers`, and `body`
- **THEN** the server responds with the configured status code and rendered header and body templates

#### Scenario: Default content type is JSON
- **WHEN** a `reply_http` action does not specify a `Content-Type` header
- **THEN** the server sets `Content-Type` to `application/json`

#### Scenario: Content type override is preserved
- **WHEN** a `reply_http` action specifies a `Content-Type` header
- **THEN** the server uses the rendered configured value

#### Scenario: Content length is calculated
- **WHEN** the server sends a `reply_http` response
- **THEN** it sets `Content-Length` from the rendered body length

### Requirement: Sleep action
The system SHALL support `sleep` actions that pause action execution before the next action.

#### Scenario: Sleep pauses before next action
- **WHEN** a matched behavior executes a `sleep` action before a `reply_http` action
- **THEN** the server waits for the configured duration before sending the reply

#### Scenario: Supported duration units
- **WHEN** a `sleep` action uses a duration with unit `ns`, `us`, `ms`, `s`, `m`, or `h`
- **THEN** the server parses the duration and sleeps for the corresponding amount of time

### Requirement: Action execution order
The system SHALL execute matched behavior actions in the order listed and stop evaluating other behaviors after selecting a match.

#### Scenario: Ordered actions execute once
- **WHEN** a behavior matches and contains multiple actions
- **THEN** the server executes those actions in list order for that request only

#### Scenario: Later behaviors are skipped
- **WHEN** a behavior matches and handles a request
- **THEN** the server does not evaluate or execute actions from later matching behaviors

### Requirement: Structured request logging
The system SHALL emit structured JSON logs and honor `HM_LOG_LEVEL`.

#### Scenario: Request response pair is logged
- **WHEN** the server handles an HTTP request
- **THEN** it emits an `info` log containing `http_path`, `http_method`, `http_host`, `http_req`, and `http_res`

#### Scenario: Log level filters output
- **WHEN** `HM_LOG_LEVEL` is set to `debug`, `info`, `warn`, or `error`
- **THEN** the server emits only logs at or above the configured level
