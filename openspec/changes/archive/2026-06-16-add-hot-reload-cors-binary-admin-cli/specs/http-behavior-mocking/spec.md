## ADDED Requirements

> Extends: http-behavior-mocking

### Requirement: CORS Response Handling
The system SHALL add global CORS headers to mock HTTP server responses when `HM_CORS_ENABLED` is `true`.

#### Scenario: CORS headers are added to matched responses
- **GIVEN** `HM_CORS_ENABLED` is `true`
- **WHEN** a request matches a behavior and the behavior sends a response
- **THEN** the response SHALL include `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`

#### Scenario: Mock CORS headers are preserved
- **GIVEN** `HM_CORS_ENABLED` is `true` and a matched `reply_http.headers` defines a CORS header
- **WHEN** middleware would otherwise set the same CORS header
- **THEN** the mock-defined header value SHALL be preserved

#### Scenario: Explicit OPTIONS behavior wins
- **GIVEN** `HM_CORS_ENABLED` is `true`
- **WHEN** an `OPTIONS` request matches a configured behavior
- **THEN** the system SHALL execute the matched behavior normally

#### Scenario: Unmatched OPTIONS becomes preflight
- **GIVEN** `HM_CORS_ENABLED` is `true`
- **WHEN** an `OPTIONS` request has no matching behavior
- **THEN** the system SHALL return `200 OK` with an empty body
- **AND** the response SHALL include the global CORS headers

#### Scenario: Unmatched non-OPTIONS still returns not found
- **GIVEN** `HM_CORS_ENABLED` is `true`
- **WHEN** a non-`OPTIONS` request has no matching behavior
- **THEN** the system SHALL return the normal unmatched-request response with global CORS headers

### Requirement: Binary HTTP Response Body
The system SHALL support binary response bodies loaded from `reply_http.body_from_binary_file`.

#### Scenario: Binary response sends raw bytes
- **GIVEN** a selected behavior executes `reply_http` with `body_from_binary_file`
- **WHEN** the response is sent
- **THEN** the system SHALL send the snapshotted binary bytes as-is
- **AND** the system SHALL NOT template-render the binary content

#### Scenario: Binary response content length is byte size
- **GIVEN** a selected behavior executes `reply_http` with `body_from_binary_file`
- **WHEN** the response is sent
- **THEN** the system SHALL set `Content-Length` to the binary byte size

#### Scenario: Binary response filename sets disposition
- **GIVEN** a selected behavior executes `reply_http` with `body_from_binary_file` and `binary_file_name`
- **WHEN** the response is sent
- **THEN** the system SHALL add `Content-Disposition: inline; filename="<binary_file_name>"`

#### Scenario: Inline body takes precedence over binary body
- **GIVEN** a `reply_http` action defines both a non-empty `body` and `body_from_binary_file`
- **WHEN** the response body is selected
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline body uses binary body
- **GIVEN** a `reply_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **WHEN** the response body is selected
- **THEN** the system SHALL send the snapshotted binary body

### Requirement: Binary Outbound HTTP Body
The system SHALL support binary request bodies loaded from `send_http.body_from_binary_file`.

#### Scenario: POST binary body uses multipart form data
- **GIVEN** a selected behavior executes `send_http` with method `POST` and `body_from_binary_file`
- **WHEN** the outbound request is sent
- **THEN** the system SHALL send the binary file as multipart form data using field name `file`

#### Scenario: Multipart filename uses configured binary name
- **GIVEN** a `send_http` action has method `POST`, `body_from_binary_file`, and `binary_file_name`
- **WHEN** the multipart request is built
- **THEN** the file part filename SHALL be `binary_file_name`

#### Scenario: Multipart filename defaults to basename
- **GIVEN** a `send_http` action has method `POST` and `body_from_binary_file` without `binary_file_name`
- **WHEN** the multipart request is built
- **THEN** the file part filename SHALL be the basename of `body_from_binary_file`

#### Scenario: Multipart content type defaults to octet stream
- **GIVEN** a `send_http` action has method `POST` and `body_from_binary_file`
- **WHEN** headers do not override the file part content type
- **THEN** the file part content type SHALL default to `application/octet-stream`

#### Scenario: Non-POST binary body uses raw bytes
- **GIVEN** a selected behavior executes `send_http` with a non-`POST` method and `body_from_binary_file`
- **WHEN** the outbound request is sent
- **THEN** the system SHALL send the snapshotted binary bytes as the raw request body

#### Scenario: Inline outbound body takes precedence over binary body
- **GIVEN** a `send_http` action defines both a non-empty `body` and `body_from_binary_file`
- **WHEN** the outbound request body is selected
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty outbound body uses binary body
- **GIVEN** a `send_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **WHEN** the outbound request body is selected
- **THEN** the system SHALL send the snapshotted binary body according to the outbound method
