## Purpose

Define the template context, syntax, render error behavior, and functions available to HTTP mock conditions and responses.

## Requirements

### Requirement: Template Context
The system SHALL render conditions, response bodies, response headers, Redis action items, and outbound HTTP action fields using the same request and behavior template context.

#### Scenario: Header context is available
- **WHEN** a template uses `.HTTPHeader.Get "Header-Name"`
- **THEN** the system SHALL provide the matching request header value

#### Scenario: Body context is available
- **WHEN** a template uses `.HTTPBody`
- **THEN** the system SHALL provide the raw request body as a string

#### Scenario: Path context is available
- **WHEN** a template uses `.HTTPPath`
- **THEN** the system SHALL provide the full request URL path including the query string when present

#### Scenario: Query string context is available
- **WHEN** a template uses `.HTTPQueryString`
- **THEN** the system SHALL provide the raw query string without the leading `?`

#### Scenario: Values context is available
- **WHEN** a selected behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: Merged inherited values are available
- **WHEN** a selected behavior extends a parent with `values`
- **THEN** every template render for that behavior SHALL expose the merged parent and child values as `.Values`

### Requirement: Named Template Rendering
The system SHALL support named reusable templates registered from mock definitions.

#### Scenario: Named template renders with root context
- **WHEN** a template expression invokes `{{ template "key" . }}` and a template named `key` is registered
- **THEN** the system SHALL render the registered template source with the current render context

#### Scenario: Named template renders with values context
- **WHEN** a template expression invokes `{{ template "key" .Values }}` and a template named `key` is registered
- **THEN** the system SHALL render the registered template source with the behavior values map as its context

#### Scenario: Named template accepts arbitrary context
- **WHEN** a template expression invokes a registered named template with any resolved context value
- **THEN** the system SHALL render the registered template source using that value as the root context for the nested render

#### Scenario: Missing named template fails rendering
- **WHEN** a template expression invokes `{{ template "missing" . }}` and no template named `missing` is registered
- **THEN** the system SHALL treat rendering as an error

### Requirement: Template Preprocessing
The system SHALL normalize template source text before parsing.

#### Scenario: Line and tab characters are replaced
- **WHEN** template source contains `\r\n`, `\n`, or `\t`
- **THEN** the system SHALL replace those characters with spaces before parsing

### Requirement: Template Syntax
The system SHALL support the required template expression syntax using `{{ ... }}` delimiters.

#### Scenario: Variable expression renders
- **WHEN** a template contains `{{ .HTTPBody }}`
- **THEN** the system SHALL render the current request body at that position

#### Scenario: Pipeline renders
- **WHEN** a template contains `{{ .HTTPBody | upper }}`
- **THEN** the system SHALL pass the value through the named function and render the result

#### Scenario: Conditional renders selected branch
- **WHEN** a template contains `{{ if expr }}yes{{ else }}no{{ end }}`
- **THEN** the system SHALL render only the branch selected by `expr`

#### Scenario: Range renders collection values
- **WHEN** a template contains `{{ range $i, $v := .Collection }}{{ $v }}{{ end }}`
- **THEN** the system SHALL iterate the collection and render each iteration body

#### Scenario: Assignment stores local value
- **WHEN** a template contains `{{ $x := expr }}`
- **THEN** the system SHALL store the evaluated expression for later use in the same template render

#### Scenario: Raw string renders literal
- **WHEN** a template contains a backtick raw string expression
- **THEN** the system SHALL render the literal raw string content

#### Scenario: Whitespace trim delimiters are accepted
- **WHEN** a template uses `{{- expr -}}`
- **THEN** the system SHALL parse and render the expression with trim delimiters accepted

#### Scenario: Undefined variables fail
- **WHEN** a template references a variable that is not defined in the render context
- **THEN** the system SHALL treat rendering as an error

### Requirement: Built-In Template Functions
The system SHALL support the required built-in template functions.

#### Scenario: Comparison and logic functions render
- **WHEN** a template uses `eq`, `ne`, `lt`, `gt`, `le`, `ge`, `and`, `or`, or `not`
- **THEN** the system SHALL evaluate the function and render its result

#### Scenario: Output functions render
- **WHEN** a template uses `print`, `printf`, or `println`
- **THEN** the system SHALL evaluate the function and render its result

#### Scenario: Encoding functions render
- **WHEN** a template uses `html`, `js`, or `urlquery`
- **THEN** the system SHALL encode the input using the named function

#### Scenario: Collection functions render
- **WHEN** a template uses `len` or `index`
- **THEN** the system SHALL evaluate the collection operation and render its result

#### Scenario: Call function renders
- **WHEN** a template uses `call`
- **THEN** the system SHALL invoke the supplied callable value and render its result

### Requirement: Extended Template Functions
The system SHALL support the required extended template functions.

#### Scenario: String functions render
- **WHEN** a template uses `contains`, `hasPrefix`, `hasSuffix`, `replace`, `trim`, `upper`, `lower`, `title`, `split`, `splitList`, `join`, `repeat`, `nospace`, or `toString`
- **THEN** the system SHALL evaluate the string function and render its result

#### Scenario: Default and fallback functions render
- **WHEN** a template uses `default`, `empty`, `coalesce`, or `ternary`
- **THEN** the system SHALL evaluate the fallback function and render its result

#### Scenario: Base64 functions render
- **WHEN** a template uses `b64enc` or `b64dec`
- **THEN** the system SHALL encode or decode the supplied value using Base64

#### Scenario: Environment function renders
- **WHEN** a template uses `env`
- **THEN** the system SHALL read the named environment variable and render its value

#### Scenario: Math functions render
- **WHEN** a template uses `add`, `sub`, `mul`, `div`, `mod`, `max`, or `min`
- **THEN** the system SHALL evaluate the arithmetic function and render its result

#### Scenario: UUID function renders
- **WHEN** a template uses `uuidv4`
- **THEN** the system SHALL render a random UUID version 4 value

#### Scenario: JSONPath function renders matched text
- **WHEN** a template uses `jsonPath` with an expression such as `foo` or `//bar` and valid JSON data
- **THEN** the system SHALL render the matched node's inner text

#### Scenario: JSONPath function renders empty for empty data
- **WHEN** a template uses `jsonPath` with empty data
- **THEN** the system SHALL render an empty string

#### Scenario: JSONPath function renders empty for no match
- **WHEN** a template uses `jsonPath` and no node matches the expression
- **THEN** the system SHALL render an empty string

#### Scenario: GJSON path function renders nested values
- **WHEN** a template uses `gJsonPath` with dot notation such as `context.type` or `user.address.city` and valid JSON data
- **THEN** the system SHALL render the matched value

#### Scenario: GJSON path function renders array indexes
- **WHEN** a template uses `gJsonPath` with an array index such as `items.0` or `users.1.name` and valid JSON data
- **THEN** the system SHALL render the matched value

#### Scenario: GJSON path function renders array wildcard values
- **WHEN** a template uses `gJsonPath` with an array wildcard such as `items.#.id` and valid JSON data
- **THEN** the system SHALL render the matched values

#### Scenario: GJSON path function renders array count
- **WHEN** a template uses `gJsonPath` with an array count such as `items.#` and valid JSON data
- **THEN** the system SHALL render the array length

#### Scenario: GJSON path function renders empty for empty data
- **WHEN** a template uses `gJsonPath` with empty data
- **THEN** the system SHALL render an empty string

#### Scenario: GJSON path function fails for invalid JSON
- **WHEN** a template uses `gJsonPath` with data that is not valid JSON
- **THEN** the system SHALL treat rendering as an error

#### Scenario: GJSON path function renders empty for no match
- **WHEN** a template uses `gJsonPath` and no value matches the expression
- **THEN** the system SHALL render an empty string

#### Scenario: XML path function renders matched text
- **WHEN** a template uses `xmlPath` with an XPath expression and valid XML data
- **THEN** the system SHALL render the matched node's inner text

#### Scenario: XML path function renders empty for empty data
- **WHEN** a template uses `xmlPath` with empty data
- **THEN** the system SHALL render an empty string

#### Scenario: XML path function renders empty for no match
- **WHEN** a template uses `xmlPath` and no node matches the expression
- **THEN** the system SHALL render an empty string

#### Scenario: UUID v5 function renders deterministically
- **WHEN** a template uses `uuidv5` with the same input data across multiple renders
- **THEN** the system SHALL render the same OID-namespace UUID version 5 value each time

#### Scenario: Regex all submatches function renders capture list
- **WHEN** a template uses `regexFindAllSubmatch` with a pattern and string that match
- **THEN** the system SHALL return a list where index `0` is the full match and following indexes are capture groups from the first match

#### Scenario: Regex first submatch function renders first capture
- **WHEN** a template uses `regexFindFirstSubmatch` with a pattern and string that match and include capture groups
- **THEN** the system SHALL render the first capture group from the first match

#### Scenario: Regex first submatch function renders empty for no capture
- **WHEN** a template uses `regexFindFirstSubmatch` with no match or a matching pattern without capture groups
- **THEN** the system SHALL render an empty string

#### Scenario: HMAC SHA256 function renders hex digest
- **WHEN** a template uses `hmacSHA256` with a secret and data
- **THEN** the system SHALL render the hex-encoded HMAC-SHA256 digest

#### Scenario: Last index function detects final element
- **WHEN** a template uses `isLastIndex` with an index and array
- **THEN** the system SHALL render `true` only when the index is the last valid index in the array

#### Scenario: HTML escape string function renders escaped value
- **WHEN** a template uses `htmlEscapeString` with a string containing `<`, `>`, `&`, `"`, or `'`
- **THEN** the system SHALL render the string with those characters escaped

### Requirement: Redis Template Function
The system SHALL support `redisDo` in every template expression context.

#### Scenario: Redis function is available to conditions
- **WHEN** a behavior condition template uses `redisDo`
- **THEN** the system SHALL evaluate the Redis command and use the returned string while deciding whether the condition passes

#### Scenario: Redis function is available to response bodies
- **WHEN** a response body template uses `redisDo`
- **THEN** the system SHALL evaluate the Redis command and render the returned string in the response body

#### Scenario: Redis function is available to response headers
- **WHEN** a response header template uses `redisDo`
- **THEN** the system SHALL evaluate the Redis command and render the returned string in the response header

#### Scenario: Redis function is available to Redis action items
- **WHEN** a `redis` action item template uses `redisDo`
- **THEN** the system SHALL evaluate the nested Redis command while rendering that Redis action item

### Requirement: Redis Command Support
The system SHALL support the required Redis command set through `redisDo` and rendered `redis` action items.

#### Scenario: String commands execute
- **WHEN** a template or Redis action item executes `SET` or `GET`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: List write commands execute
- **WHEN** a template or Redis action item executes `RPUSH` or `LPUSH`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: List read commands execute
- **WHEN** a template or Redis action item executes `LRANGE`, `LPOP`, or `RPOP`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Hash commands execute
- **WHEN** a template or Redis action item executes `HSET`, `HGET`, `HGETALL`, or `HDEL`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Key commands execute
- **WHEN** a template or Redis action item executes `DEL`, `EXISTS`, or `KEYS`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Unsupported Redis command fails rendering
- **WHEN** a template or Redis action item executes a Redis command outside the supported command set
- **THEN** the system SHALL treat the operation as a template render error

### Requirement: Redis Return Formatting
The system SHALL render Redis command results as strings.

#### Scenario: Single-value Redis result renders as string
- **WHEN** a Redis command returns a single value
- **THEN** the system SHALL render that value as a string

#### Scenario: Empty Redis result renders as empty string
- **WHEN** a Redis command returns no value
- **THEN** the system SHALL render an empty string

#### Scenario: Array Redis result joins with delimiter
- **WHEN** a Redis command returns an array result
- **THEN** the system SHALL render the values joined with `;;`

#### Scenario: Split list converts Redis array string
- **WHEN** a template passes a Redis array result string to `splitList ";;"`
- **THEN** the system SHALL return a list of the delimited values

### Requirement: Reserved Internal Redis Keyspace
The system SHALL prevent template-accessible Redis commands from touching internal persistence keys matching `__hmock_internal:*`.

#### Scenario: Redis function blocks internal template key
- **WHEN** a template uses `redisDo` with a command that targets `__hmock_internal:templates`
- **THEN** the system SHALL treat the call as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: Redis function blocks internal template set key
- **WHEN** a template uses `redisDo` with a command that targets a template-set storage key matching `__hmock_internal:template_sets:*`
- **THEN** the system SHALL treat the call as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: Redis function blocks internal wildcard key
- **WHEN** a template uses `redisDo` with a key pattern matching `__hmock_internal:*`
- **THEN** the system SHALL treat the call as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: User keyspace remains available
- **WHEN** a template uses `redisDo` with a supported command that targets a key outside `__hmock_internal:*`
- **THEN** the system SHALL execute the command using the configured Redis backend
