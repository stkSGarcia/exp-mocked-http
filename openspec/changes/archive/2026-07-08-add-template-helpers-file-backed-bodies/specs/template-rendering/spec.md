## MODIFIED Requirements

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
