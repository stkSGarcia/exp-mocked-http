## ADDED Requirements

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

## MODIFIED Requirements

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
