## ADDED Requirements

### Requirement: Mock HTTP CORS
The system SHALL optionally add global CORS headers to responses from the mock HTTP server.

#### Scenario: CORS disabled by default
- **WHEN** the server starts without `HM_CORS_ENABLED`
- **THEN** responses from the mock HTTP server SHALL NOT receive global CORS headers unless a mock defines them

#### Scenario: CORS headers are added when enabled
- **WHEN** `HM_CORS_ENABLED=true` and the mock HTTP server sends a response
- **THEN** the response SHALL include `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`

#### Scenario: Mock CORS headers are preserved
- **WHEN** `HM_CORS_ENABLED=true` and `reply_http.headers` defines a CORS header also set by the global middleware
- **THEN** the response SHALL use the mock-defined header value for that header

#### Scenario: Explicit OPTIONS behavior takes precedence
- **WHEN** `HM_CORS_ENABLED=true` and an `OPTIONS` request matches a loaded mock behavior
- **THEN** the system SHALL execute the matched mock behavior

#### Scenario: Unmatched OPTIONS request becomes preflight
- **WHEN** `HM_CORS_ENABLED=true` and an `OPTIONS` request matches no loaded behavior
- **THEN** the system SHALL return `200 OK` with an empty body and the global CORS headers

### Requirement: Binary HTTP Response Body
The system SHALL support binary response bodies loaded from files for `reply_http` actions.

#### Scenario: Binary response sends bytes as-is
- **WHEN** a selected behavior executes `reply_http` with `body_from_binary_file` and no non-empty `body`
- **THEN** the system SHALL send the snapshotted binary bytes without template rendering

#### Scenario: Binary response content length is computed from bytes
- **WHEN** a selected behavior sends a binary response body
- **THEN** the system SHALL set `Content-Length` to the binary byte length

#### Scenario: Binary response filename sets content disposition
- **WHEN** a selected behavior executes `reply_http` with `body_from_binary_file` and `binary_file_name`
- **THEN** the system SHALL add `Content-Disposition: inline; filename="<binary_file_name>"`

#### Scenario: Inline body takes precedence over binary file body
- **WHEN** a `reply_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline body uses binary file body
- **WHEN** a `reply_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL send the snapshotted binary file body

### Requirement: Binary Outbound HTTP Body
The system SHALL support binary request bodies loaded from files for `send_http` actions.

#### Scenario: POST binary file sends multipart form data
- **WHEN** a selected behavior executes `send_http` with method `POST` and `body_from_binary_file`
- **THEN** the outbound request SHALL send multipart form data using form field name `file`

#### Scenario: Multipart upload uses configured filename
- **WHEN** a `send_http` POST action defines `body_from_binary_file` and `binary_file_name`
- **THEN** the multipart file part SHALL use `binary_file_name` as the uploaded filename

#### Scenario: Multipart upload defaults filename to basename
- **WHEN** a `send_http` POST action defines `body_from_binary_file` and omits `binary_file_name`
- **THEN** the multipart file part SHALL use the basename of `body_from_binary_file` as the uploaded filename

#### Scenario: Multipart upload defaults content type
- **WHEN** a `send_http` POST action defines `body_from_binary_file` without an overriding content type header
- **THEN** the file part content type SHALL be `application/octet-stream`

#### Scenario: Non-POST binary file sends raw body
- **WHEN** a selected behavior executes `send_http` with a non-POST method and `body_from_binary_file`
- **THEN** the outbound request SHALL send the snapshotted binary bytes as the raw request body

#### Scenario: Inline outbound body takes precedence over binary file body
- **WHEN** a `send_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty outbound inline body uses binary file body
- **WHEN** a `send_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL send the snapshotted binary file body
