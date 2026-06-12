## ADDED Requirements

### Requirement: Mock Server CORS
The system SHALL optionally add global CORS behavior to mock HTTP server responses through `HM_CORS_ENABLED`.

#### Scenario: CORS disabled by default
- **WHEN** the server starts without `HM_CORS_ENABLED`
- **THEN** the system SHALL NOT add global CORS headers to mock HTTP server responses

#### Scenario: CORS headers are added when enabled
- **WHEN** `HM_CORS_ENABLED=true` and the mock server sends any response
- **THEN** the response SHALL include `Access-Control-Allow-Origin: *`
- **AND** the response SHALL include `Access-Control-Allow-Methods: *`
- **AND** the response SHALL include `Access-Control-Allow-Headers: *`
- **AND** the response SHALL include `Access-Control-Allow-Credentials: true`

#### Scenario: Mock-defined CORS headers are preserved
- **WHEN** `HM_CORS_ENABLED=true` and a matching `reply_http.headers` defines a CORS header
- **THEN** the system SHALL preserve the mock-defined header value instead of replacing it with the global CORS value

#### Scenario: Explicit OPTIONS behavior wins
- **WHEN** `HM_CORS_ENABLED=true` and an `OPTIONS` request matches a configured behavior
- **THEN** the system SHALL execute the matched behavior normally and include applicable CORS headers

#### Scenario: Unmatched OPTIONS becomes preflight response
- **WHEN** `HM_CORS_ENABLED=true` and an `OPTIONS` request does not match any configured behavior
- **THEN** the system SHALL return `200 OK` with an empty body and the global CORS headers

#### Scenario: Unmatched non-OPTIONS remains not found
- **WHEN** `HM_CORS_ENABLED=true` and a non-`OPTIONS` request does not match any configured behavior
- **THEN** the system SHALL return the normal unmatched request response with applicable CORS headers

### Requirement: Binary HTTP Response Body
The system SHALL support binary response bodies for `reply_http` actions.

#### Scenario: Binary response body sends bytes as-is
- **WHEN** a selected behavior executes `reply_http` with `body_from_binary_file` and no non-empty `body`
- **THEN** the system SHALL send the snapshotted binary bytes as the HTTP response body without template rendering

#### Scenario: Binary response content length uses byte size
- **WHEN** a selected behavior sends a binary response body
- **THEN** the system SHALL set `Content-Length` to the binary byte size

#### Scenario: Binary response filename adds content disposition
- **WHEN** a selected behavior sends a binary response body and `binary_file_name` is set
- **THEN** the system SHALL include `Content-Disposition: inline; filename="<binary_file_name>"`

#### Scenario: Inline body takes precedence over binary response file
- **WHEN** a `reply_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline body uses binary response file
- **WHEN** a `reply_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL send the binary file body

### Requirement: Binary Outbound HTTP Body
The system SHALL support binary outbound request bodies for `send_http` actions.

#### Scenario: POST binary file sends multipart upload
- **WHEN** a selected behavior executes `send_http` with method `POST`, `body_from_binary_file`, and no non-empty `body`
- **THEN** the outbound request SHALL use multipart form data with form field name `file`

#### Scenario: POST binary upload filename defaults to basename
- **WHEN** a `send_http` POST uses `body_from_binary_file` without `binary_file_name`
- **THEN** the multipart file part filename SHALL be the basename of `body_from_binary_file`

#### Scenario: POST binary upload uses configured filename
- **WHEN** a `send_http` POST uses `body_from_binary_file` with `binary_file_name`
- **THEN** the multipart file part filename SHALL be the configured `binary_file_name`

#### Scenario: POST binary upload default content type
- **WHEN** a `send_http` POST sends a binary file and action headers do not override the file content type
- **THEN** the multipart file part content type SHALL be `application/octet-stream`

#### Scenario: Non-POST binary file sends raw request body
- **WHEN** a selected behavior executes `send_http` with a method other than `POST`, `body_from_binary_file`, and no non-empty `body`
- **THEN** the outbound request body SHALL be the snapshotted binary bytes without multipart wrapping

#### Scenario: Inline body takes precedence over binary outbound file
- **WHEN** a `send_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`
