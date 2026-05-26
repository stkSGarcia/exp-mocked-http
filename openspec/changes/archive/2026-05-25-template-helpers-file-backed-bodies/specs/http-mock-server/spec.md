## ADDED Requirements

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
