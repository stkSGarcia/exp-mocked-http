## MODIFIED Requirements

### Requirement: Template language support
The system MUST support the checkpoint template syntax and functions for conditions, response bodies, file-backed response bodies, and response headers.

#### Scenario: Supported syntax renders
- **WHEN** a template uses expressions, pipelines, conditionals, loops, assignment, raw strings, or whitespace trimming with `{{ ... }}` delimiters
- **THEN** the template renderer evaluates the syntax according to the mock-server template rules

#### Scenario: Template newlines and tabs are normalized
- **WHEN** a template contains `\r\n`, `\n`, or `\t` before parsing
- **THEN** the renderer replaces those characters with spaces before parsing

#### Scenario: Built-in and extended functions render
- **WHEN** a template uses a listed comparison, logic, output, encoding, collection, invocation, string, fallback, environment, math, or UUID function
- **THEN** the renderer evaluates the function and includes its result in the rendered output

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
