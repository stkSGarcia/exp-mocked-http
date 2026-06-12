## ADDED Requirements

### Requirement: File-Backed HTTP Response Body
The system SHALL support response bodies loaded from files for `reply_http` actions.

#### Scenario: File-backed body renders
- **WHEN** a selected behavior executes `reply_http` with `body_from_file`
- **THEN** the system SHALL render the loaded file content as the HTTP response body

#### Scenario: File-backed body uses request template context
- **WHEN** a loaded response body file contains template expressions
- **THEN** the system SHALL render those expressions with the same request context and template functions available to inline response bodies

#### Scenario: Inline body takes precedence
- **WHEN** a `reply_http` action defines both a non-empty `body` and `body_from_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline body uses file-backed body
- **WHEN** a `reply_http` action defines `body_from_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL render and send the loaded file-backed body

### Requirement: Templated HTTP Response Headers
The system SHALL render every configured `reply_http.headers` value as a template.

#### Scenario: Header value uses request context
- **WHEN** a selected behavior executes `reply_http` with a header value containing a template expression
- **THEN** the system SHALL render the header value using the same request context and template functions available to response bodies
