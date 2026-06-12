## MODIFIED Requirements

### Requirement: Unmatched HTTP Request
The system SHALL return a 404 response for requests with no matching behavior, except for CORS preflight fallback requests when mock-server CORS is enabled.

#### Scenario: No matching behavior
- **WHEN** no loaded behavior matches the request method, path, and condition and the request is not an unmatched CORS preflight fallback
- **THEN** the system SHALL return status `404 Not Found` with response body exactly `not found`

#### Scenario: Unmatched OPTIONS without CORS
- **WHEN** `HM_CORS_ENABLED` is disabled and no loaded behavior matches an `OPTIONS` request
- **THEN** the system SHALL return status `404 Not Found` with response body exactly `not found`

## ADDED Requirements

### Requirement: Mock Server CORS
The system SHALL add global CORS headers to mock-server responses when `HM_CORS_ENABLED` is enabled.

#### Scenario: CORS headers are added to matched response
- **WHEN** `HM_CORS_ENABLED` is enabled and a request matches a behavior
- **THEN** the response SHALL include `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`

#### Scenario: CORS headers are not added when disabled
- **WHEN** `HM_CORS_ENABLED` is disabled and a request matches a behavior
- **THEN** the system SHALL NOT add global CORS headers to the response

#### Scenario: Explicit OPTIONS behavior wins
- **WHEN** `HM_CORS_ENABLED` is enabled and an `OPTIONS` request matches a loaded behavior
- **THEN** the system SHALL execute the matched behavior instead of returning the unmatched preflight fallback

#### Scenario: Unmatched OPTIONS returns preflight response
- **WHEN** `HM_CORS_ENABLED` is enabled and no loaded behavior matches an `OPTIONS` request
- **THEN** the system SHALL return `200 OK` with an empty body and the global CORS headers

#### Scenario: Mock-defined CORS header value wins
- **WHEN** `HM_CORS_ENABLED` is enabled and a selected `reply_http.headers` entry sets a header with the same name as a global CORS header
- **THEN** the response SHALL keep the mock-defined header value for that header

#### Scenario: Mock-defined CORS header comparison is case insensitive
- **WHEN** `HM_CORS_ENABLED` is enabled and a selected `reply_http.headers` entry sets a CORS header using different letter casing
- **THEN** the response SHALL keep the mock-defined header value for that header

### Requirement: Binary File-Backed HTTP Response Body
The system SHALL support response bodies loaded from binary files for `reply_http` actions.

#### Scenario: Binary file-backed response sends raw bytes
- **WHEN** a selected behavior executes `reply_http` with `body_from_binary_file` and no non-empty inline `body`
- **THEN** the system SHALL send the loaded binary bytes as the HTTP response body without template rendering

#### Scenario: Binary response content length is computed from bytes
- **WHEN** a selected behavior executes `reply_http` using `body_from_binary_file`
- **THEN** the system SHALL set `Content-Length` to the binary body size in bytes

#### Scenario: Inline response body takes precedence over binary file
- **WHEN** a `reply_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Empty inline response body uses binary file
- **WHEN** a `reply_http` action defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **THEN** the system SHALL send the loaded binary body

#### Scenario: Binary response filename adds content disposition
- **WHEN** a selected behavior executes `reply_http` using `body_from_binary_file` and defines `binary_file_name`
- **THEN** the system SHALL add `Content-Disposition: inline; filename="<binary_file_name>"`

#### Scenario: Binary response content is not rendered
- **WHEN** a binary response file contains bytes that look like template expressions
- **THEN** the system SHALL send those bytes unchanged

### Requirement: Binary Outbound HTTP Action Body
The system SHALL support outbound request bodies loaded from binary files for `send_http` actions.

#### Scenario: Binary POST uses multipart form data
- **WHEN** a selected behavior executes `send_http` with method `POST`, `body_from_binary_file`, and no non-empty inline `body`
- **THEN** the system SHALL send the binary file as multipart form data using form field name `file`

#### Scenario: Multipart upload uses configured filename
- **WHEN** a binary `send_http` POST defines `binary_file_name`
- **THEN** the multipart file part SHALL use that value as the uploaded filename

#### Scenario: Multipart upload uses source basename by default
- **WHEN** a binary `send_http` POST omits `binary_file_name`
- **THEN** the multipart file part SHALL use the basename of `body_from_binary_file` as the uploaded filename

#### Scenario: Multipart upload content type defaults
- **WHEN** a binary `send_http` POST does not provide a content-type override for the file part
- **THEN** the multipart file part content type SHALL be `application/octet-stream`

#### Scenario: Multipart upload content type can be overridden
- **WHEN** a binary `send_http` POST provides a content-type override in the action headers
- **THEN** the multipart file part SHALL use the configured content type

#### Scenario: Binary non-POST sends raw bytes
- **WHEN** a selected behavior executes `send_http` with a non-`POST` method, `body_from_binary_file`, and no non-empty inline `body`
- **THEN** the system SHALL send the loaded binary bytes as the raw outbound request body

#### Scenario: Inline outbound body takes precedence over binary file
- **WHEN** a `send_http` action defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Binary outbound body is not rendered
- **WHEN** an outbound binary file contains bytes that look like template expressions
- **THEN** the system SHALL send those bytes unchanged
