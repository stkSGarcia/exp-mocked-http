# http-yaml-mock-server Specification

## Purpose
TBD - created by archiving change add-http-yaml-mock-server. Update Purpose after archive.
## Requirements
### Requirement: Server configuration
The system SHALL provide a Python entry point named `hmock.py` that starts an HTTP mock server using environment-based configuration.

#### Scenario: Start server with default configuration
- **WHEN** `uv run --project /app hmock.py` starts without mock-server environment variables
- **THEN** the server listens on host `0.0.0.0`, port `9999`, scans `./templates`, and uses log level `info`

#### Scenario: Start server with overridden configuration
- **WHEN** `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, and `HM_LOG_LEVEL` are set
- **THEN** the server uses those values for template scanning, HTTP binding, and log filtering

### Requirement: Redis backend configuration
The system SHALL provide Redis-compatible state storage configured by environment variables.

#### Scenario: Default Redis backend is memory
- **WHEN** the server starts without `HM_REDIS_TYPE` or `HM_REDIS_URL`
- **THEN** it uses an embedded in-memory Redis-compatible store and the effective Redis URL default is `redis://redis:6379`

#### Scenario: External Redis backend is configured
- **WHEN** `HM_REDIS_TYPE` is set to `redis` and `HM_REDIS_URL` is set
- **THEN** the server uses the configured URL for external Redis command execution

#### Scenario: In-memory Redis state is process local
- **WHEN** the server uses the `memory` Redis backend
- **THEN** data written through Redis commands is not persisted across process restarts

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
- **WHEN** a definition omits `key`
- **THEN** validation rejects that definition

#### Scenario: Empty key is rejected
- **WHEN** a definition has a `key` that is not a non-empty string
- **THEN** validation rejects that definition

#### Scenario: Behavior allowed fields
- **WHEN** a `Behavior` definition contains only `key`, `kind`, `extend`, `expect`, `actions`, and `values`
- **THEN** validation accepts those fields subject to normal required-field and action validation

#### Scenario: AbstractBehavior allowed fields
- **WHEN** an `AbstractBehavior` definition contains only `key`, `kind`, `expect`, `actions`, and `values`
- **THEN** validation accepts those fields subject to normal required-field and action validation

#### Scenario: Template allowed fields
- **WHEN** a `Template` definition contains only `key`, `kind`, and `template`
- **THEN** validation accepts those fields subject to normal required-field validation

#### Scenario: Template rejects behavior fields
- **WHEN** a `Template` definition contains `expect`, `actions`, or `values`
- **THEN** validation rejects that definition

#### Scenario: Behavior rejects template field
- **WHEN** a `Behavior` definition contains `template`
- **THEN** validation rejects that definition

#### Scenario: Multiple HTTP replies are rejected
- **WHEN** a final concrete behavior contains more than one `reply_http` action after inheritance is resolved
- **THEN** validation rejects that behavior definition

### Requirement: Behavior kinds
The system MUST accept exactly three behavior definition kinds: `Behavior`, `Template`, and `AbstractBehavior`.

#### Scenario: Omitted kind defaults to Behavior
- **WHEN** a loaded definition has no `kind`
- **THEN** the server treats the definition as kind `Behavior`

#### Scenario: Accepted kinds load
- **WHEN** loaded definitions use `kind` values `Behavior`, `Template`, and `AbstractBehavior`
- **THEN** validation accepts those kind values subject to their field rules

#### Scenario: Unknown kind is rejected
- **WHEN** a loaded definition uses any other `kind` value
- **THEN** validation rejects that definition

### Requirement: Reusable named templates
The system SHALL support `Template` definitions that register reusable template fragments by key.

#### Scenario: Template registers by key
- **WHEN** a loaded definition has kind `Template`, a non-empty `key`, and a `template` string
- **THEN** the server registers the template string under that key for later rendering

#### Scenario: Named template renders with current request context
- **WHEN** a rendered template calls `{{ template "key" . }}` for a registered template
- **THEN** the server renders the named template with the current template context

#### Scenario: Named template renders with passed values context
- **WHEN** a rendered template calls `{{ template "key" .Values }}`
- **THEN** the server renders the named template with the current behavior values map as its context

#### Scenario: Template definition never matches requests
- **WHEN** a request matches data that only appears in a `Template` definition
- **THEN** the server does not select that template as a behavior

### Requirement: Abstract behaviors
The system SHALL support `AbstractBehavior` definitions as reusable inheritance bases that never match requests directly.

#### Scenario: Abstract behavior accepts reusable behavior fields
- **WHEN** a loaded definition has kind `AbstractBehavior` with `expect`, `actions`, and `values`
- **THEN** validation accepts those fields subject to normal behavior validation rules

#### Scenario: Abstract behavior never matches directly
- **WHEN** a request matches an `AbstractBehavior` definition's `expect` data
- **THEN** the server does not execute actions from that abstract behavior unless a concrete behavior inherits them

### Requirement: Behavior inheritance
The system SHALL allow a `Behavior` to extend another `Behavior` or an `AbstractBehavior`.

#### Scenario: Parent resolves regardless of definition order
- **WHEN** a `Behavior` extends a parent definition that appears later in the loaded YAML definitions
- **THEN** the server resolves the parent and loads the child with inherited fields

#### Scenario: Missing parent is skipped
- **WHEN** a `Behavior` extends a key that is not present
- **THEN** the server ignores the extension and validates the child using only its own fields

#### Scenario: Missing parent still allows validation failure
- **WHEN** a `Behavior` extends a missing key and the child remains invalid without inherited fields
- **THEN** validation rejects that child

#### Scenario: Parent values merge with child override
- **WHEN** a child behavior extends a parent and both define `values`
- **THEN** the merged values contain parent keys plus child keys, with child values overriding parent values for matching keys

#### Scenario: Parent actions precede child actions before sorting
- **WHEN** a child behavior extends a parent and both define `actions`
- **THEN** the child's final action list contains parent actions followed by child actions before action ordering is applied

#### Scenario: Expect fields merge recursively
- **WHEN** a child behavior extends a parent and both define nested `expect` fields
- **THEN** missing child fields inherit parent values and matching child fields override parent values

#### Scenario: Other fields prefer child non-zero values
- **WHEN** a child behavior extends a parent and both define fields other than `values`, `actions`, or `expect`
- **THEN** the final behavior uses the child's non-zero field value and otherwise keeps the parent value

#### Scenario: Final reply cardinality is enforced
- **WHEN** inherited and child actions combine to more than one `reply_http` action for a final `Behavior`
- **THEN** validation rejects that behavior

### Requirement: Behavior values
The system SHALL allow `Behavior` and `AbstractBehavior` definitions to define arbitrary `values` maps and expose merged values as `.Values`.

#### Scenario: Values render in response body
- **WHEN** a matched behavior defines `values` and a response body template references `.Values.<key>`
- **THEN** the rendered response body includes the value for that key

#### Scenario: Values render in conditions
- **WHEN** a matched behavior's condition references `.Values.<key>`
- **THEN** the condition is evaluated with that behavior's merged values

#### Scenario: Inherited values render
- **WHEN** a behavior extends a parent with values and overrides one value
- **THEN** templates render using the merged values map with the child override

### Requirement: Duplicate behavior keys
The system SHALL treat duplicate behavior keys as overrides where the last loaded behavior wins and SHALL log a warning for each override.

#### Scenario: Later duplicate key overrides earlier behavior
- **WHEN** multiple loaded behaviors use the same `key`
- **THEN** only the last loaded behavior for that key remains active for request matching

#### Scenario: Duplicate key emits warning
- **WHEN** a later behavior overrides an earlier behavior with the same `key`
- **THEN** the server emits a structured warning log describing the override

### Requirement: HTTP request matching
The system SHALL match concrete behaviors by `expect.http.method`, `expect.http.path`, and optional `expect.condition` in active load order.

#### Scenario: Exact method and path match
- **WHEN** a request method and path equal a behavior's expected HTTP method and path and the behavior has no condition
- **THEN** that behavior matches the request

#### Scenario: Named path parameter match
- **WHEN** a behavior expects a path containing `:param` and a request path has a value in that segment
- **THEN** the behavior matches and the captured parameter value is exposed in the request URL context

#### Scenario: First passing behavior handles request
- **WHEN** multiple concrete behaviors match the request method and path
- **THEN** the first behavior in active load order whose condition passes handles the request and later behaviors are not evaluated

#### Scenario: Non-concrete definitions are skipped
- **WHEN** loaded `Template` or `AbstractBehavior` definitions contain request-like data
- **THEN** the matcher does not evaluate those definitions as active behaviors

#### Scenario: No matching behavior
- **WHEN** no concrete behavior matches the request method, path, and condition
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
The system SHALL provide request data and behavior values to every condition, response body, response header, side-effect, and named-template render.

#### Scenario: Header context is available
- **WHEN** a template calls `.HTTPHeader.Get "Header-Name"`
- **THEN** it receives the matching request header value from a case-insensitive header map

#### Scenario: Body and URL context are available
- **WHEN** a template references `.HTTPBody`, `.HTTPPath`, or `.HTTPQueryString`
- **THEN** it receives the raw request body, full request URL path including query string, or raw query string without `?`

#### Scenario: Values context is available
- **WHEN** a template references `.Values.<key>`
- **THEN** it receives the matched behavior's merged value for that key

#### Scenario: Undefined variable is an error
- **WHEN** a template references a variable that is not defined in the context
- **THEN** rendering fails

### Requirement: Template language support
The system MUST support the checkpoint template syntax and functions for conditions, response bodies, file-backed response bodies, response headers, side-effect fields, and named templates.

#### Scenario: Supported syntax renders
- **WHEN** a template uses expressions, pipelines, conditionals, loops, assignment, raw strings, or whitespace trimming with `{{ ... }}` delimiters
- **THEN** the template renderer evaluates the syntax according to the mock-server template rules

#### Scenario: Template newlines and tabs are normalized
- **WHEN** a template contains `\r\n`, `\n`, or `\t` before parsing
- **THEN** the renderer replaces those characters with spaces before parsing

#### Scenario: Built-in and extended functions render
- **WHEN** a template uses a listed comparison, logic, output, encoding, collection, invocation, string, fallback, environment, math, or UUID function
- **THEN** the renderer evaluates the function and includes its result in the rendered output

#### Scenario: Named template function renders
- **WHEN** a template calls `template(name, context)` or uses `{{ template "name" context }}`
- **THEN** the renderer evaluates the registered named template using the supplied context

#### Scenario: JSON XPath-style helper renders
- **WHEN** a template calls `jsonPath(expr, data)` with JSON data and an expression such as `foo` or `//bar`
- **THEN** the renderer returns the matched node's inner text

#### Scenario: JSON XPath-style helper handles empty or missing data
- **WHEN** a template calls `jsonPath(expr, data)` with empty data or with an expression that does not match
- **THEN** the renderer returns `""`

#### Scenario: GJSON dot-notation helper renders nested values
- **WHEN** a template calls `gJsonPath(expr, data)` with a nested field expression such as `context.type` or `user.address.city`
- **THEN** the renderer returns the matched value

#### Scenario: GJSON helper renders array indexes wildcards and counts
- **WHEN** a template calls `gJsonPath(expr, data)` with array index syntax such as `items.0`, wildcard syntax such as `items.#.id`, or count syntax such as `items.#`
- **THEN** the renderer returns the matched value

#### Scenario: GJSON helper handles empty or missing data
- **WHEN** a template calls `gJsonPath(expr, data)` with empty data or with an expression that does not match
- **THEN** the renderer returns `""`

#### Scenario: GJSON helper rejects invalid JSON
- **WHEN** a template calls `gJsonPath(expr, data)` with non-empty data that is not valid JSON
- **THEN** rendering fails with a render error

#### Scenario: XML XPath helper renders
- **WHEN** a template calls `xmlPath(expr, data)` with XML data and a matching XPath expression
- **THEN** the renderer returns the matched node's inner text

#### Scenario: XML XPath helper handles empty or missing data
- **WHEN** a template calls `xmlPath(expr, data)` with empty data or with an expression that does not match
- **THEN** the renderer returns `""`

#### Scenario: Deterministic UUID v5 helper renders
- **WHEN** a template calls `uuidv5(data)` with the same input multiple times
- **THEN** the renderer returns the same UUID v5 generated with the OID namespace each time

#### Scenario: Regex submatch helpers render
- **WHEN** a template calls `regexFindAllSubmatch(pattern, str)` or `regexFindFirstSubmatch(pattern, str)` with a matching pattern
- **THEN** `regexFindAllSubmatch` returns the full match followed by capture groups and `regexFindFirstSubmatch` returns the first capture group

#### Scenario: Regex submatch helpers handle no capture
- **WHEN** a template calls `regexFindFirstSubmatch(pattern, str)` and the pattern does not match or has no capture groups
- **THEN** the renderer returns `""`

#### Scenario: HMAC SHA256 helper renders
- **WHEN** a template calls `hmacSHA256(secret, data)`
- **THEN** the renderer returns the hex-encoded HMAC-SHA256 digest

#### Scenario: Last index helper renders
- **WHEN** a template calls `isLastIndex(index, array)` with an index equal to the last valid index in the array
- **THEN** the renderer returns `true`

#### Scenario: HTML escape helper renders
- **WHEN** a template calls `htmlEscapeString(str)` with text containing `<`, `>`, `&`, `"`, or `'`
- **THEN** the renderer returns the text with those characters escaped

### Requirement: Redis template command helper
The system SHALL provide a `redisDo` template function for executing supported Redis commands from any rendered template expression.

#### Scenario: redisDo is available in conditions
- **WHEN** a behavior condition calls `redisDo`
- **THEN** the Redis command is executed while evaluating whether the behavior matches

#### Scenario: redisDo is available in response bodies
- **WHEN** a `reply_http.body` or loaded `reply_http.body_from_file` template calls `redisDo`
- **THEN** the Redis command result is available in the rendered response body

#### Scenario: redisDo is available in response headers
- **WHEN** a `reply_http.headers` value template calls `redisDo`
- **THEN** the Redis command result is available in the rendered response header value

#### Scenario: redisDo is available in redis actions
- **WHEN** a `redis` action item template calls `redisDo`
- **THEN** the nested Redis command is executed during rendering before the rendered action item command is executed

### Requirement: Redis command support
The system SHALL support the Redis commands `SET`, `GET`, `RPUSH`, `LPUSH`, `LRANGE`, `LPOP`, `RPOP`, `HSET`, `HGET`, `HGETALL`, `HDEL`, `DEL`, `EXISTS`, and `KEYS`.

#### Scenario: String commands execute
- **WHEN** templates or actions execute `SET key value` followed by `GET key`
- **THEN** `GET key` returns `value` as a string

#### Scenario: List push commands execute
- **WHEN** templates or actions execute `RPUSH queue a`, `RPUSH queue b`, and `LPUSH queue z`
- **THEN** the list value for `queue` is ordered as `z`, `a`, `b`

#### Scenario: List range command returns joined array results
- **WHEN** templates or actions execute `LRANGE queue 0 -1` for a list containing `z`, `a`, and `b`
- **THEN** the command result is the string `z;;a;;b`

#### Scenario: List pop commands execute
- **WHEN** templates or actions execute `LPOP queue` or `RPOP queue`
- **THEN** the command returns the removed list value as a string

#### Scenario: Hash commands execute
- **WHEN** templates or actions execute `HSET user name Ada`, `HGET user name`, `HGETALL user`, and `HDEL user name`
- **THEN** hash fields can be set, read, listed, and deleted through the Redis backend

#### Scenario: Key commands execute
- **WHEN** templates or actions execute `DEL key`, `EXISTS key`, or `KEYS pattern`
- **THEN** keys can be deleted, checked for existence, and listed by pattern through the Redis backend

#### Scenario: Single-value results render as strings
- **WHEN** a supported Redis command returns a single value
- **THEN** the command result renders as that value's string form

#### Scenario: Array results use delimiter
- **WHEN** a supported Redis command returns multiple values
- **THEN** the command result joins those values with `;;`

#### Scenario: Delimited results can become template lists
- **WHEN** a template pipes an array command result through `splitList` with delimiter `;;`
- **THEN** the rendered template can iterate or index the returned values as a list

### Requirement: HTTP reply action
The system SHALL support `reply_http` actions that render a single HTTP response.

#### Scenario: Reply renders status headers and body
- **WHEN** a matched behavior executes a `reply_http` action with `status_code`, `headers`, and `body`
- **THEN** the server responds with the configured status code and rendered header and body templates

#### Scenario: Headers render as templates
- **WHEN** a matched behavior executes a `reply_http` action with header values containing template expressions
- **THEN** the server renders every configured header value as a template using the request context and available template functions

#### Scenario: File-backed body renders
- **WHEN** a matched behavior executes a `reply_http` action with `body_from_file` and no non-empty `body`
- **THEN** the server renders the loaded file content as the response body template using the request context and available template functions

#### Scenario: File-backed body resolves relative to templates directory
- **WHEN** a mock file configures `reply_http.body_from_file`
- **THEN** the server resolves the configured path relative to `HM_TEMPLATES_DIR`

#### Scenario: File-backed body uses loaded snapshot
- **WHEN** a file referenced by `reply_http.body_from_file` changes after the behavior configuration is loaded
- **THEN** subsequent responses render the file content snapshot that was loaded with the configuration

#### Scenario: Inline body takes precedence over file-backed body
- **WHEN** a `reply_http` action configures both a non-empty `body` and `body_from_file`
- **THEN** the server renders the inline `body` and does not use `body_from_file`

#### Scenario: Empty inline body falls back to file-backed body
- **WHEN** a `reply_http` action configures an empty `body` and `body_from_file`
- **THEN** the server renders the loaded file content as the response body template

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

### Requirement: Redis action
The system SHALL support a `redis` action containing an array of template strings.

#### Scenario: Redis action items execute in order
- **WHEN** a matched behavior executes a `redis` action with multiple items
- **THEN** the server renders and executes each item as an independent Redis command in array order

#### Scenario: Later redis action items see earlier writes
- **WHEN** a `redis` action writes state in one item and reads that state in a later item
- **THEN** the later item observes the earlier write

#### Scenario: Redis action continues to later actions
- **WHEN** a matched behavior executes a `redis` action followed by `sleep`, `send_http`, or `reply_http`
- **THEN** the server continues executing later actions after the Redis action completes

### Requirement: Outbound HTTP side-effect action
The system SHALL support a `send_http` action that makes an outbound HTTP request as a side effect.

#### Scenario: Required send_http fields
- **WHEN** a behavior defines a `send_http` action
- **THEN** the action requires `url` and `method`

#### Scenario: send_http renders request fields
- **WHEN** a matched behavior executes `send_http` with templated `url`, `headers`, and `body`
- **THEN** the server renders the URL, every header value, and the body using the request context and available template functions before sending the outbound request

#### Scenario: send_http supports file-backed body
- **WHEN** a matched behavior executes `send_http` with `body_from_file` and no non-empty inline `body`
- **THEN** the server sends the loaded file content rendered as the outbound request body template

#### Scenario: Inline send_http body takes precedence
- **WHEN** a `send_http` action configures both a non-empty `body` and `body_from_file`
- **THEN** the server renders and sends the inline `body`

#### Scenario: Outbound failure does not fail inbound response
- **WHEN** a `send_http` outbound request fails
- **THEN** the server logs the failure and continues executing the matched behavior without failing mock execution or changing the inbound response because of that failure

### Requirement: Action execution order
The system SHALL execute matched behavior actions sorted by explicit `order` and stop evaluating other behaviors after selecting a match.

#### Scenario: Actions default to order zero
- **WHEN** a behavior action does not define `order`
- **THEN** the server treats that action's order as `0`

#### Scenario: Lower order executes first
- **WHEN** a matched behavior contains actions with different `order` values
- **THEN** the server executes actions in ascending order value

#### Scenario: Negative order executes before zero
- **WHEN** a matched behavior contains an action with negative `order` and another action with default order
- **THEN** the server executes the negative-order action first

#### Scenario: Equal order preserves relative order
- **WHEN** multiple actions have the same `order`
- **THEN** the server preserves their original relative order from the merged action list

#### Scenario: Inherited actions participate in sorting
- **WHEN** a behavior inherits parent actions and defines child actions with explicit order values
- **THEN** the server sorts the combined inherited and child actions together before execution

#### Scenario: Ordered actions execute once
- **WHEN** a behavior matches and contains multiple actions
- **THEN** the server executes those actions in sorted order for that request only

#### Scenario: Later behaviors are skipped
- **WHEN** a behavior matches and handles a request
- **THEN** the server does not evaluate or execute actions from later matching behaviors

### Requirement: Mixed side-effect action execution
The system SHALL allow a behavior to mix `redis`, `send_http`, `sleep`, and `reply_http` actions in one ordered action list.

#### Scenario: Mixed actions execute in listed order
- **WHEN** a matched behavior contains `redis`, `send_http`, `sleep`, and `reply_http` actions
- **THEN** the server executes side-effect and sleep actions in list order until `reply_http` produces the inbound response

#### Scenario: Reply still ends action processing
- **WHEN** a matched behavior executes `reply_http`
- **THEN** the server returns that response and does not execute later actions in the same behavior

### Requirement: Structured request logging
The system SHALL emit structured JSON logs and honor `HM_LOG_LEVEL`.

#### Scenario: Request response pair is logged
- **WHEN** the server handles an HTTP request
- **THEN** it emits an `info` log containing `http_path`, `http_method`, `http_host`, `http_req`, and `http_res`

#### Scenario: Log level filters output
- **WHEN** `HM_LOG_LEVEL` is set to `debug`, `info`, `warn`, or `error`
- **THEN** the server emits only logs at or above the configured level
