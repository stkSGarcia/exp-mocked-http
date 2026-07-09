## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions

### Requirement: Binary Response File Validation
The system SHALL validate `reply_http.body_from_binary_file` payloads before serving requests.

#### Scenario: Binary response path resolves relative to templates directory
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Missing binary response file is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary response file outside templates directory is rejected
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Binary Response Snapshot
The system SHALL store a stable binary snapshot for a loaded `reply_http.body_from_binary_file` configuration.

#### Scenario: Binary response is snapshotted at load time
- **WHEN** a loaded behavior defines `reply_http.body_from_binary_file`
- **THEN** the system SHALL store the file bytes for that loaded configuration

#### Scenario: Binary response is not template rendered
- **WHEN** a matched `reply_http` uses `body_from_binary_file`
- **THEN** the system SHALL send the stored binary bytes without template rendering the content

### Requirement: Binary Response Execution
The mock HTTP server SHALL use `reply_http.body_from_binary_file` as the response body only when `reply_http.body` is absent or empty.

#### Scenario: Empty body uses binary file
- **WHEN** a matched `reply_http` defines `body_from_binary_file` and has no `body` value
- **THEN** the server sends the binary file bytes as the response body

#### Scenario: Text body takes precedence over binary file
- **WHEN** a matched `reply_http` defines both a non-empty `body` and `body_from_binary_file`
- **THEN** the server sends the rendered text body instead of the binary file bytes

#### Scenario: Binary content length uses byte size
- **WHEN** a matched `reply_http` sends `body_from_binary_file`
- **THEN** the response `Content-Length` header is set to the binary byte size

#### Scenario: Binary filename adds content disposition
- **WHEN** a matched `reply_http` sends `body_from_binary_file` with `binary_file_name`
- **THEN** the response includes `Content-Disposition: inline; filename="<binary_file_name>"`

### Requirement: Binary Outbound File Validation
The system SHALL validate `send_http.body_from_binary_file` action payloads before serving requests. (adapts mock-definition-loading/add-stateful-actions/outbound-http-action-validation)

#### Scenario: Binary outbound path resolves relative to templates directory
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file`
- **THEN** the system SHALL resolve the path relative to `HM_TEMPLATES_DIR`

#### Scenario: Binary outbound file is snapshotted at load time
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file`
- **THEN** the system SHALL store a stable snapshot of the file bytes for that loaded configuration

#### Scenario: Missing binary outbound file is rejected
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file` and the resolved file does not exist
- **THEN** the system SHALL reject that behavior as invalid

#### Scenario: Binary outbound file outside templates directory is rejected
- **WHEN** a loaded behavior defines `send_http.body_from_binary_file` that resolves outside `HM_TEMPLATES_DIR`
- **THEN** the system SHALL reject that behavior as invalid

### Requirement: Binary Outbound Execution
The `send_http` action SHALL send binary file bytes without template rendering the binary content.

#### Scenario: POST sends multipart file
- **WHEN** a `send_http` action uses `body_from_binary_file` with method `POST`
- **THEN** the outbound request body is multipart form data containing the file in form field `file`

#### Scenario: POST filename uses configured binary filename
- **WHEN** a `send_http` action uses `body_from_binary_file` with method `POST` and `binary_file_name`
- **THEN** the outbound multipart file upload uses `binary_file_name` as the uploaded filename

#### Scenario: POST filename defaults to basename
- **WHEN** a `send_http` action uses `body_from_binary_file` with method `POST` and omits `binary_file_name`
- **THEN** the outbound multipart file upload uses the basename of `body_from_binary_file` as the uploaded filename

#### Scenario: POST file content type defaults to octet stream
- **WHEN** a `send_http` action uses `body_from_binary_file` with method `POST` and no header overrides the file content type
- **THEN** the outbound multipart file part uses `application/octet-stream`

#### Scenario: Non-POST sends raw binary body
- **WHEN** a `send_http` action uses `body_from_binary_file` with a method other than `POST`
- **THEN** the outbound request body is the raw binary file bytes
