# http-mock-server

## Purpose

A lightweight HTTP mock server that loads behavior definitions from YAML template files and responds to incoming HTTP requests according to configurable match conditions, template-rendered responses, and action sequences.

## Requirements

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
Each loaded behavior SHALL be validated: `key` is required and must be a non-empty string; `kind` defaults to `"Behavior"` when omitted; accepted `kind` values are `Behavior`, `AbstractBehavior`, and `Template` — any other `kind` SHALL be rejected; a behavior with more than one `reply_http` action SHALL be rejected. Valid action types are `sleep`, `reply_http`, `redis`, and `send_http`. Each kind enforces an allowed-field rule: `Template` MAY only contain `key`, `kind`, and `template`; `AbstractBehavior` MAY contain `key`, `kind`, `expect`, `actions`, and `values`; `Behavior` MAY contain `key`, `kind`, `extend`, `expect`, `actions`, and `values`. Fields not in the allowed set SHALL be rejected at load time.

#### Scenario: Missing key rejected
- **WHEN** a behavior definition omits `key`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Multiple reply_http rejected
- **WHEN** a behavior has two or more `reply_http` actions
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Kind defaults to Behavior
- **WHEN** a behavior definition omits `kind`
- **THEN** the behavior is treated as `kind: Behavior`

#### Scenario: Unknown kind rejected
- **WHEN** a behavior defines `kind: Widget`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Template with disallowed field rejected
- **WHEN** a `Template` definition includes an `actions` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: AbstractBehavior with template field rejected
- **WHEN** an `AbstractBehavior` definition includes a `template` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Behavior with template field rejected
- **WHEN** a `Behavior` definition includes a `template` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: redis action accepted
- **WHEN** a behavior includes a `redis` action
- **THEN** the server loads the behavior without error

#### Scenario: send_http action accepted
- **WHEN** a behavior includes a `send_http` action
- **THEN** the server loads the behavior without error

### Requirement: Duplicate key resolution
When multiple loaded behaviors share the same `key`, the last loaded behavior SHALL replace earlier ones. The server SHALL emit a warning log when a key is overridden.

#### Scenario: Last definition wins
- **WHEN** two YAML files both define a behavior with `key: foo`
- **THEN** the later-loaded definition is active and the earlier one is discarded

#### Scenario: Warning logged on override
- **WHEN** a key is overridden by a later definition
- **THEN** a warning log entry is emitted identifying the duplicate key

### Requirement: Template kind — reusable named fragments
The server SHALL support `kind: Template` items. Each `Template` SHALL be registered under its `key` and callable from any template expression as `{{template "key" <context>}}`. Templates MAY accept any context value, including `.Values`. Templates SHALL NOT be treated as matchable behaviors.

#### Scenario: Template callable from body
- **WHEN** a `Template` with key `color-template` and `template: '{"color": "{{.color}}"}'` is defined, and a behavior body contains `{{template "color-template" .Values}}` with `values: {color: purple}`
- **THEN** the response body contains `{"color": "purple"}`

#### Scenario: Template callable with full context
- **WHEN** a `Template` with key `path-info` contains `{{.HTTPPath}}` and a behavior body calls `{{template "path-info" .}}`
- **THEN** the rendered output contains the request path

#### Scenario: Template not matched as behavior
- **WHEN** only a `Template` definition is loaded with no `Behavior` definitions
- **THEN** all requests return HTTP 404

### Requirement: AbstractBehavior kind — non-matchable base behaviors
The server SHALL support `kind: AbstractBehavior` items. An `AbstractBehavior` MAY define `expect`, `actions`, and `values`. It SHALL never match incoming requests directly and SHALL be excluded from the request-matching loop.

#### Scenario: AbstractBehavior does not match requests
- **WHEN** only an `AbstractBehavior` definition exists for `GET /api`
- **THEN** `GET /api` returns HTTP 404

#### Scenario: AbstractBehavior usable as parent
- **WHEN** an `AbstractBehavior` defines `expect.http.method: GET` and `expect.http.path: /api`, and a `Behavior` extends it
- **THEN** the `Behavior` matches `GET /api`

### Requirement: Behavior extension via extend field
A `Behavior` MAY declare `extend: <parent-key>` to inherit `expect`, `actions`, and `values` from a parent `Behavior` or `AbstractBehavior`. The server SHALL resolve extension regardless of definition order. When the parent key does not exist, the server SHALL skip the extension and load the child with only its own fields; if the child then fails field-presence validation, the server SHALL reject it. Merge rules:
1. `values` maps are merged; child keys override parent keys.
2. Parent `actions` precede child `actions`.
3. `expect` is merged recursively; child fields override matching parent fields; missing child fields inherit parent values.
4. For scalar fields (`kind`, `key`), the child's non-falsy value wins; otherwise the parent value is used.

#### Scenario: Child inherits parent expect
- **WHEN** an `AbstractBehavior` defines `expect.http.method: GET` and `expect.http.path: /teapot`, and a `Behavior` extends it with no `expect` of its own
- **THEN** `GET /teapot` matches the child behavior

#### Scenario: Child values override parent values
- **WHEN** a parent defines `values: {color: red, size: large}` and the child defines `values: {color: blue}`
- **THEN** the merged values are `{color: blue, size: large}`

#### Scenario: Parent actions precede child actions
- **WHEN** a parent defines action `sleep 100ms` and the child defines action `reply_http 200`
- **THEN** the server sleeps before sending the response

#### Scenario: Child expect field overrides parent
- **WHEN** a parent defines `expect.http.path: /base` and the child defines `expect.http.path: /override`
- **THEN** only `GET /override` matches the child behavior

#### Scenario: Missing parent skips extension
- **WHEN** a `Behavior` declares `extend: nonexistent-key`
- **THEN** the server loads the behavior using only its own fields without error

#### Scenario: Forward reference resolved
- **WHEN** a child `Behavior` is defined before its `AbstractBehavior` parent in the YAML file
- **THEN** the child still inherits the parent's fields correctly

### Requirement: Values map for behaviors
`Behavior` and `AbstractBehavior` items MAY define a `values` field as an arbitrary string-keyed map. The server SHALL expose the merged values in all template expressions (conditions, bodies, headers) as `.Values.<key>`. When a child extends a parent, the merged values map is used.

#### Scenario: Values accessible in body
- **WHEN** a behavior defines `values: {color: blue}` and body template `{{.Values.color}}`
- **THEN** the response body is `blue`

#### Scenario: Values accessible in condition
- **WHEN** a behavior defines `values: {expected_token: secret}` and condition `{{.HTTPHeader.Get "X-Token" | eq .Values.expected_token}}`
- **THEN** the condition passes when `X-Token: secret` is present

#### Scenario: Merged values available in extended behavior
- **WHEN** a parent defines `values: {a: 1}` and a child defines `values: {b: 2}`, and the child's body template uses `{{.Values.a}}` and `{{.Values.b}}`
- **THEN** both values render correctly

### Requirement: Action ordering via order field
Each action MAY include an `order` field (integer, positive, negative, or zero). The server SHALL sort all actions (including inherited ones) by `order` ascending before execution. `order` SHALL default to `0` when absent. When two actions share the same `order`, the server SHALL preserve their original relative order (stable sort).

#### Scenario: Lower order executes first
- **WHEN** a behavior has a `reply_http` action with `order: 1` and a `sleep` action with `order: 0`
- **THEN** the server sleeps before sending the response

#### Scenario: Negative order executes before default
- **WHEN** an inherited `reply_http` has no order (defaults to 0) and a child adds `sleep` with `order: -1000`
- **THEN** the sleep executes before the reply

#### Scenario: Same-order actions preserve original relative order
- **WHEN** two actions share `order: 0`
- **THEN** they execute in the order they appear in the merged actions list

#### Scenario: Default order is zero
- **WHEN** an action has no `order` field
- **THEN** it is sorted as if `order: 0`

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

### Requirement: jsonPath template function
The server SHALL provide a `jsonPath(expr, data)` template function that queries JSON using XPath-style syntax (e.g. `"foo"` or `"//bar"`), returns the matched node's inner text, and returns `""` when `data` is empty or nothing matches.

#### Scenario: Simple key match
- **WHEN** `jsonPath("foo", data)` and `data` is `{"foo": "bar"}`
- **THEN** the function returns `"bar"`

#### Scenario: Empty data returns empty string
- **WHEN** `jsonPath("foo", "")` is called
- **THEN** the function returns `""`

#### Scenario: No match returns empty string
- **WHEN** `jsonPath("missing", data)` and the key is absent
- **THEN** the function returns `""`

### Requirement: gJsonPath template function
The server SHALL provide a `gJsonPath(expr, data)` template function that queries JSON using dot-notation (e.g. `"context.type"`, `"items.0"`, `"users.1.name"`), supports array index access, array count via `"items.#"`, and array wildcard via `"items.#.field"`. It SHALL return `""` when `data` is empty or nothing matches, and SHALL return a render error when `data` is not valid JSON.

#### Scenario: Nested field access
- **WHEN** `gJsonPath("user.address.city", data)` and `data` is `{"user":{"address":{"city":"Paris"}}}`
- **THEN** the function returns `"Paris"`

#### Scenario: Array index access
- **WHEN** `gJsonPath("items.0", data)` and `data` is `{"items":["a","b"]}`
- **THEN** the function returns `"a"`

#### Scenario: Array count
- **WHEN** `gJsonPath("items.#", data)` and `data` is `{"items":[1,2,3]}`
- **THEN** the function returns `"3"`

#### Scenario: Array wildcard
- **WHEN** `gJsonPath("items.#.id", data)` and `data` is `{"items":[{"id":"x"},{"id":"y"}]}`
- **THEN** the function returns a string containing both `"x"` and `"y"`

#### Scenario: Empty data returns empty string
- **WHEN** `gJsonPath("foo", "")` is called
- **THEN** the function returns `""`

#### Scenario: Invalid JSON returns render error
- **WHEN** `gJsonPath("foo", "not-json")` is called
- **THEN** the function returns a render error

### Requirement: xmlPath template function
The server SHALL provide an `xmlPath(expr, data)` template function that queries XML using XPath, returns the matched node's inner text, and returns `""` when `data` is empty or nothing matches.

#### Scenario: Element text extraction
- **WHEN** `xmlPath("//name", data)` and `data` is `<root><name>Alice</name></root>`
- **THEN** the function returns `"Alice"`

#### Scenario: Empty data returns empty string
- **WHEN** `xmlPath("//foo", "")` is called
- **THEN** the function returns `""`

#### Scenario: No match returns empty string
- **WHEN** `xmlPath("//missing", data)` and the XPath selects nothing
- **THEN** the function returns `""`

### Requirement: uuidv5 template function
The server SHALL provide a `uuidv5(data)` template function that generates a deterministic UUID v5 using the OID namespace. The same input SHALL always produce the same UUID.

#### Scenario: Deterministic output
- **WHEN** `uuidv5("hello")` is called twice with the same input
- **THEN** both calls return the identical UUID string

#### Scenario: Different inputs produce different UUIDs
- **WHEN** `uuidv5("a")` and `uuidv5("b")` are called
- **THEN** the two UUID strings differ

### Requirement: regexFindAllSubmatch template function
The server SHALL provide a `regexFindAllSubmatch(pattern, str)` template function that matches `pattern` against `str`, returns a list where index `0` is the full match and index `1+` are capture groups from the first match, and returns an empty list when there is no match.

#### Scenario: Capture groups returned
- **WHEN** `regexFindAllSubmatch("(\\w+)@(\\w+)", "user@host")` is called
- **THEN** the result list is `["user@host", "user", "host"]`

#### Scenario: No match returns empty list
- **WHEN** the pattern does not match `str`
- **THEN** the function returns an empty list

### Requirement: regexFindFirstSubmatch template function
The server SHALL provide a `regexFindFirstSubmatch(pattern, str)` template function that returns the first capture group from the first match, and returns `""` when there is no match or the pattern has no capture groups.

#### Scenario: First capture group returned
- **WHEN** `regexFindFirstSubmatch("(\\d+)", "abc123def")` is called
- **THEN** the function returns `"123"`

#### Scenario: No match returns empty string
- **WHEN** the pattern does not match `str`
- **THEN** the function returns `""`

#### Scenario: No capture groups returns empty string
- **WHEN** pattern has no capture groups and matches
- **THEN** the function returns `""`

### Requirement: hmacSHA256 template function
The server SHALL provide an `hmacSHA256(secret, data)` template function that computes HMAC-SHA256 of `data` using `secret` and returns the hex-encoded digest.

#### Scenario: Correct digest produced
- **WHEN** `hmacSHA256("key", "message")` is called
- **THEN** the result is the lowercase hex HMAC-SHA256 digest of `"message"` with key `"key"`

### Requirement: isLastIndex template function
The server SHALL provide an `isLastIndex(index, array)` template function that returns `true` when `index` equals the last valid index of `array`, and `false` otherwise.

#### Scenario: Last index detected
- **WHEN** `isLastIndex(2, ["a","b","c"])` is called
- **THEN** the function returns `true`

#### Scenario: Non-last index returns false
- **WHEN** `isLastIndex(0, ["a","b","c"])` is called
- **THEN** the function returns `false`

### Requirement: htmlEscapeString template function
The server SHALL provide an `htmlEscapeString(str)` template function that escapes `<`, `>`, `&`, `"`, and `'` in the input string.

#### Scenario: Special characters escaped
- **WHEN** `htmlEscapeString("<b>hello & \"world\"</b>")` is called
- **THEN** the result contains no unescaped `<`, `>`, `&`, `"`, or `'` characters

### Requirement: body_from_file field on reply_http
The `reply_http` action SHALL accept a `body_from_file` field whose value is a path resolved relative to `HM_TEMPLATES_DIR`. The server SHALL read and snapshot the file contents at load time. At request time, the snapshot SHALL be rendered as a template with the same request context and functions as `body`. When both `body` and `body_from_file` are set, `body_from_file` SHALL be used only when `body` is empty.

#### Scenario: File body rendered at request time
- **WHEN** `body_from_file` points to a valid file containing a template expression
- **THEN** the response body is the rendered result of that file's contents

#### Scenario: body_from_file takes precedence over empty body
- **WHEN** `body` is empty and `body_from_file` is set
- **THEN** the file contents are used as the response body template

#### Scenario: body used when body_from_file not set
- **WHEN** only `body` is set and `body_from_file` is absent
- **THEN** the `body` value is used as before

#### Scenario: File path resolved relative to HM_TEMPLATES_DIR
- **WHEN** `body_from_file: responses/payload.json` and `HM_TEMPLATES_DIR=./templates`
- **THEN** the server reads `./templates/responses/payload.json`

#### Scenario: Path outside templates dir rejected at load time
- **WHEN** `body_from_file` resolves to a path outside `HM_TEMPLATES_DIR`
- **THEN** the server rejects the behavior at startup with an error
