## ADDED Requirements

> Extends: template-rendering/add-stateful-actions
> Extends: template-rendering/add-admin-api-template-storage
> Extends: http-behavior-mocking/add-stateful-actions

### Requirement: Binary Reply File Bodies
The mock HTTP server SHALL support `reply_http.body_from_binary_file` as a templates-directory-relative path to a binary response body and SHALL keep a stable binary snapshot for the loaded configuration.

#### Scenario: Binary reply bytes are sent as-is
- **GIVEN** a loaded mock behavior has `reply_http.body_from_binary_file` pointing to a binary file
- **AND** `reply_http.body` is empty or absent
- **WHEN** the behavior is selected for request handling
- **THEN** the response body SHALL contain the binary bytes as-is
- **AND** the server SHALL NOT template-render the binary content

#### Scenario: Binary snapshot is stable
- **GIVEN** a loaded configuration includes a `reply_http.body_from_binary_file`
- **WHEN** the referenced binary file changes before the configuration is reloaded
- **THEN** responses from that loaded configuration SHALL continue using the binary bytes captured for that loaded configuration

### Requirement: Binary Reply Metadata
For `reply_http.body_from_binary_file` responses, the mock HTTP server SHALL set `Content-Length` from the binary size and SHALL add `Content-Disposition: inline; filename=\"<binary_file_name>\"` when `reply_http.binary_file_name` is set.

#### Scenario: Content length reflects binary size
- **GIVEN** a loaded mock behavior uses `reply_http.body_from_binary_file`
- **AND** `reply_http.body` is empty or absent
- **WHEN** the behavior is selected for request handling
- **THEN** the response `Content-Length` SHALL equal the number of binary bytes sent

#### Scenario: Binary file name adds content disposition
- **GIVEN** a loaded mock behavior uses `reply_http.body_from_binary_file`
- **AND** `reply_http.binary_file_name` is `report.pdf`
- **WHEN** the behavior is selected for request handling
- **THEN** the response SHALL include `Content-Disposition: inline; filename=\"report.pdf\"`

### Requirement: Reply Body Precedence
When both `reply_http.body_from_binary_file` and `reply_http.body` are set, the mock HTTP server SHALL use the binary file only when `reply_http.body` is empty.

#### Scenario: Non-empty text body wins
- **GIVEN** a loaded mock behavior defines both `reply_http.body_from_binary_file` and a non-empty `reply_http.body`
- **WHEN** the behavior is selected for request handling
- **THEN** the response body SHALL come from `reply_http.body`

#### Scenario: Empty text body allows binary file
- **GIVEN** a loaded mock behavior defines `reply_http.body_from_binary_file`
- **AND** `reply_http.body` is empty
- **WHEN** the behavior is selected for request handling
- **THEN** the response body SHALL come from the binary file

### Requirement: Binary Send HTTP Bodies
The mock HTTP server SHALL support `send_http.body_from_binary_file` as a templates-directory-relative path to a binary outbound request body and `send_http.binary_file_name` as an optional upload filename.

#### Scenario: POST sends multipart file upload
- **GIVEN** a selected behavior includes a `send_http` action with method `POST`
- **AND** the action defines `body_from_binary_file`
- **WHEN** the server executes the action
- **THEN** the outbound request SHALL be multipart form data
- **AND** the file part field name SHALL be `file`
- **AND** the upload filename SHALL be `binary_file_name` when present or the basename of `body_from_binary_file` otherwise

#### Scenario: POST file part has default content type
- **GIVEN** a selected behavior includes a `send_http` `POST` action with `body_from_binary_file`
- **AND** no configured headers override the file part content type
- **WHEN** the server executes the action
- **THEN** the outbound file part content type SHALL be `application/octet-stream`

#### Scenario: Non-POST sends raw binary body
- **GIVEN** a selected behavior includes a `send_http` action with a method other than `POST`
- **AND** the action defines `body_from_binary_file`
- **WHEN** the server executes the action
- **THEN** the outbound request body SHALL be the binary bytes as-is
