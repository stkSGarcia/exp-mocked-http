## ADDED Requirements

> Extends: `http-yaml-mock-server/add-template-helpers-file-backed-bodies`

### Requirement: Binary file loading
The system SHALL resolve `body_from_binary_file` relative to the configured templates directory, reject paths outside that directory, and capture the file bytes in the compiled runtime so requests use a stable snapshot. (adapts `http-yaml-mock-server/add-template-helpers-file-backed-bodies`)

#### Scenario: Binary snapshot is stable
- **GIVEN** a configuration containing a readable `body_from_binary_file` is loaded
- **WHEN** the underlying file changes without a runtime reload
- **THEN** requests continue using the bytes captured by the loaded configuration

#### Scenario: Binary path escapes templates directory
- **WHEN** `body_from_binary_file` resolves outside the templates directory
- **THEN** runtime compilation fails with a validation error

#### Scenario: Binary file cannot be read
- **WHEN** `body_from_binary_file` does not identify a readable file
- **THEN** runtime compilation fails with an error naming the configured path

### Requirement: Binary reply body
When a `reply_http` action selects `body_from_binary_file`, the system SHALL send the captured bytes unchanged, SHALL NOT template-render them, and SHALL set `Content-Length` to the binary byte count.

#### Scenario: Empty inline body selects binary file
- **GIVEN** `reply_http` defines `body_from_binary_file` and omits `body` or sets `body` to an empty value
- **WHEN** the action executes
- **THEN** the response body equals the captured binary bytes
- **AND** `Content-Length` equals the number of bytes

#### Scenario: Non-empty inline body takes precedence
- **GIVEN** `reply_http` defines both `body_from_binary_file` and a non-empty `body`
- **WHEN** the action executes
- **THEN** the rendered inline body is sent instead of the binary file

### Requirement: Binary reply filename
When a selected binary `reply_http` body defines a non-empty `binary_file_name`, the system SHALL add `Content-Disposition: inline; filename="<binary_file_name>"`.

#### Scenario: Configured inline filename
- **GIVEN** a binary reply is selected and `binary_file_name` is `report.pdf`
- **WHEN** the response is built
- **THEN** it includes `Content-Disposition: inline; filename="report.pdf"`

#### Scenario: Filename omitted
- **GIVEN** a binary reply is selected and `binary_file_name` is omitted
- **WHEN** the response is built
- **THEN** the system does not synthesize a `Content-Disposition` header

### Requirement: Binary outbound POST
When a `send_http` action using method `POST` selects `body_from_binary_file`, the system SHALL send multipart form data with one file part named `file`.

#### Scenario: Configured upload filename
- **GIVEN** a binary `POST` action defines `binary_file_name`
- **WHEN** the outbound request is sent
- **THEN** the multipart file part uses field name `file`
- **AND** its uploaded filename is `binary_file_name`

#### Scenario: Default upload filename
- **GIVEN** a binary `POST` action omits `binary_file_name`
- **WHEN** the outbound request is sent
- **THEN** the multipart file part uses the basename of `body_from_binary_file` as its uploaded filename

#### Scenario: Default file media type
- **GIVEN** a binary `POST` action does not configure a content type header
- **WHEN** the multipart request is encoded
- **THEN** the file part content type is `application/octet-stream`

#### Scenario: Configured file media type
- **GIVEN** a binary `POST` action configures a `Content-Type` header
- **WHEN** the multipart request is encoded
- **THEN** the configured value is used as the file part content type
- **AND** the request envelope retains its generated `multipart/form-data` boundary

### Requirement: Binary outbound raw body
When a non-`POST` `send_http` action selects `body_from_binary_file`, the system SHALL send the captured binary bytes as the raw request body.

#### Scenario: PUT sends raw bytes
- **GIVEN** a `send_http` action uses method `PUT` and selects a binary file
- **WHEN** the outbound request is sent
- **THEN** the request body equals the captured bytes without multipart encoding

#### Scenario: Inline outbound body takes precedence
- **GIVEN** `send_http` defines both `body_from_binary_file` and a non-empty `body`
- **WHEN** the outbound request is sent
- **THEN** the rendered inline body is sent instead of the binary file
