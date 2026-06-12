## ADDED Requirements

### Requirement: Template Context
The system SHALL render conditions, response bodies, and response headers using the same request template context.

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
