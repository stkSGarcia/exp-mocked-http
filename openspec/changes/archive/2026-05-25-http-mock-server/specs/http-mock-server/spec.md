## ADDED Requirements

### Requirement: Server startup via environment configuration
The server SHALL read configuration from environment variables at startup: `HM_TEMPLATES_DIR` (default `./templates`), `HM_HTTP_PORT` (default `9999`), `HM_HTTP_HOST` (default `0.0.0.0`), and `HM_LOG_LEVEL` (default `info`, values: `debug`, `info`, `warn`, `error`).

#### Scenario: Default configuration startup
- **WHEN** the server starts with no environment variables set
- **THEN** it listens on `0.0.0.0:9999` and scans `./templates` for mock files

#### Scenario: Custom port and host
- **WHEN** `HM_HTTP_PORT=8080` and `HM_HTTP_HOST=127.0.0.1` are set
- **THEN** the server listens on `127.0.0.1:8080`

### Requirement: YAML mock file loading
The server SHALL recursively scan `HM_TEMPLATES_DIR` for `.yaml` and `.yml` files, load each as a list of behavior objects, and merge all into one ordered list. Files SHALL be scanned in sorted filesystem order for determinism.

#### Scenario: Recursive scan
- **WHEN** template files exist in subdirectories of `HM_TEMPLATES_DIR`
- **THEN** all `.yaml` and `.yml` files in any subdirectory are loaded

#### Scenario: Merged into ordered list
- **WHEN** multiple YAML files are loaded
- **THEN** their behaviors are merged into a single list in file-sorted order

### Requirement: Mock behavior validation
Each loaded behavior SHALL be validated: `key` is required and must be a non-empty string; `kind` defaults to `"Behavior"` when omitted; a behavior with more than one `reply_http` action SHALL be rejected.

#### Scenario: Missing key rejected
- **WHEN** a behavior definition omits `key`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Multiple reply_http rejected
- **WHEN** a behavior has two or more `reply_http` actions
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Kind defaults to Behavior
- **WHEN** a behavior definition omits `kind`
- **THEN** the behavior is treated as `kind: Behavior`

### Requirement: Duplicate key resolution
When multiple loaded behaviors share the same `key`, the last loaded behavior SHALL replace earlier ones. The server SHALL emit a warning log when a key is overridden.

#### Scenario: Last definition wins
- **WHEN** two YAML files both define a behavior with `key: foo`
- **THEN** the later-loaded definition is active and the earlier one is discarded

#### Scenario: Warning logged on override
- **WHEN** a key is overridden by a later definition
- **THEN** a warning log entry is emitted identifying the duplicate key

### Requirement: HTTP request matching by method and path
The server SHALL match incoming HTTP requests against loaded behaviors in load order by `expect.http.method` and `expect.http.path`. Path matching SHALL support named parameters using `:param` syntax.

#### Scenario: Exact path match
- **WHEN** `GET /ping` arrives and a behavior expects `method: GET, path: /ping`
- **THEN** that behavior is selected as the candidate

#### Scenario: Named path parameter match
- **WHEN** `GET /users/42` arrives and a behavior expects `path: /users/:id`
- **THEN** the behavior matches and the captured value `42` is available as path param `id`

#### Scenario: No match returns 404
- **WHEN** no behavior matches the request method and path
- **THEN** the server returns HTTP 404 with body exactly `not found`

### Requirement: Condition evaluation
When a matched behavior has `expect.condition`, the server SHALL render it as a template and check whether the output is exactly `true`. An empty or missing condition SHALL pass. A condition that fails to render SHALL not match.

#### Scenario: Condition passes on true output
- **WHEN** a condition template renders to exactly `true`
- **THEN** the behavior is selected

#### Scenario: Empty condition passes
- **WHEN** `expect.condition` is absent or empty
- **THEN** the behavior matches without condition evaluation

#### Scenario: Condition rendering error skips behavior
- **WHEN** a condition template references an undefined variable
- **THEN** the behavior is skipped (does not match)

#### Scenario: First passing behavior wins
- **WHEN** multiple behaviors match method/path but only the second has a passing condition
- **THEN** the second behavior handles the request

### Requirement: Template rendering
Template expressions in conditions, response bodies, and response headers SHALL use `{{ ... }}` delimiters. The server SHALL replace `\r\n`, `\n`, and `\t` with spaces before parsing. Undefined variable references SHALL cause a render error.

#### Scenario: Variable substitution in body
- **WHEN** `body: '{{ .HTTPPath }}'` and request path is `/api/v1`
- **THEN** response body is `/api/v1`

#### Scenario: Extended function available
- **WHEN** `body: '{{ .HTTPBody | upper }}'` and request body is `hello`
- **THEN** response body is `HELLO`

#### Scenario: Undefined variable is render error
- **WHEN** a template references `.Undefined`
- **THEN** the render fails and the behavior does not match (for conditions) or returns a 500 (for body/headers)

### Requirement: Template context variables
All templates SHALL receive a context with: `.HTTPHeader` (request headers, with `.Get "Name"` accessor), `.HTTPBody` (raw request body string), `.HTTPPath` (full request URL path including query string), `.HTTPQueryString` (raw query string without `?`).

#### Scenario: Header access via Get
- **WHEN** condition is `{{ .HTTPHeader.Get "X-Token" | eq "abc" }}` and request has `X-Token: abc`
- **THEN** the condition renders to `true`

#### Scenario: Query string available
- **WHEN** request is `GET /search?q=test` and body uses `{{ .HTTPQueryString }}`
- **THEN** body renders as `q=test`

### Requirement: reply_http action
The `reply_http` action SHALL send an HTTP response with the configured `status_code`, `headers` (each value rendered as a template), and `body` (rendered as a template). `Content-Type` SHALL default to `application/json` unless overridden. `Content-Length` SHALL be set from the rendered body length.

#### Scenario: Default Content-Type
- **WHEN** `reply_http` has no `headers` field
- **THEN** response includes `Content-Type: application/json`

#### Scenario: Content-Length set automatically
- **WHEN** `body: "hello"` (5 bytes)
- **THEN** response includes `Content-Length: 5`

#### Scenario: Header override
- **WHEN** `headers: {Content-Type: text/plain}`
- **THEN** response `Content-Type` is `text/plain`

### Requirement: sleep action
The `sleep` action SHALL pause execution for the specified `duration` before continuing to the next action. Duration values SHALL support units `ns`, `us`, `ms`, `s`, `m`, `h`.

#### Scenario: Sleep delays response
- **WHEN** actions list is `[sleep: {duration: 100ms}, reply_http: {status_code: 200}]`
- **THEN** the response is delayed by approximately 100ms

#### Scenario: Invalid duration rejected
- **WHEN** `duration: 5x` uses an unsupported unit
- **THEN** the server rejects the behavior at load time

### Requirement: Structured JSON logging
The server SHALL emit structured JSON logs. Each HTTP request/response pair SHALL be logged at `info` level with fields: `http_path`, `http_method`, `http_host`, `http_req`, `http_res`. The server SHALL honor `HM_LOG_LEVEL`.

#### Scenario: Request logged at info
- **WHEN** a request is handled
- **THEN** a JSON log line is emitted at info level with all required fields

#### Scenario: Debug logs suppressed at info level
- **WHEN** `HM_LOG_LEVEL=info`
- **THEN** debug-level log entries are not emitted
