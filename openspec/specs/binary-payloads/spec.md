# binary-payloads

## Purpose

TBD

## Requirements

### Requirement: reply_http body_from_binary_file field
The `reply_http` action SHALL accept a `body_from_binary_file` field whose value is a file path resolved relative to `HM_TEMPLATES_DIR`. The server SHALL load and snapshot the binary file bytes at configuration-load time. At request time, the binary bytes SHALL be sent as-is without template rendering.

#### Scenario: Binary file served as response body
- **WHEN** `body_from_binary_file: assets/image.png` is set and the file exists
- **THEN** the response body contains the exact bytes from the file

#### Scenario: Binary content not template-rendered
- **WHEN** a binary file contains bytes that look like a template expression
- **THEN** the bytes are sent as-is without rendering

#### Scenario: body_from_binary_file rejected if path outside templates dir
- **WHEN** `body_from_binary_file: ../../etc/passwd` resolves outside `HM_TEMPLATES_DIR`
- **THEN** the server rejects the behavior at load time with an error

### Requirement: reply_http Content-Length from binary size
When `body_from_binary_file` is used, the server SHALL set `Content-Length` from the byte length of the binary file snapshot.

#### Scenario: Content-Length matches binary size
- **WHEN** `body_from_binary_file` points to a 1024-byte file
- **THEN** the response includes `Content-Length: 1024`

### Requirement: reply_http binary_file_name field
The `reply_http` action SHALL accept an optional `binary_file_name` field. When set, the server SHALL add `Content-Disposition: inline; filename="<binary_file_name>"` to the response.

#### Scenario: Content-Disposition added when binary_file_name set
- **WHEN** `binary_file_name: report.pdf` is set alongside `body_from_binary_file`
- **THEN** the response includes `Content-Disposition: inline; filename="report.pdf"`

#### Scenario: No Content-Disposition when binary_file_name absent
- **WHEN** `body_from_binary_file` is set but `binary_file_name` is absent
- **THEN** the response does not include a `Content-Disposition` header (unless set elsewhere)

### Requirement: reply_http body_from_binary_file precedence over body
When both `body` and `body_from_binary_file` are set on a `reply_http` action, `body_from_binary_file` SHALL be used only when `body` is empty.

#### Scenario: Non-empty body wins over binary file
- **WHEN** both `body: "hello"` and `body_from_binary_file: file.bin` are set
- **THEN** the response body is `hello` (text body takes precedence)

#### Scenario: Empty body falls back to binary file
- **WHEN** `body` is empty and `body_from_binary_file` is set
- **THEN** the binary file bytes are used as the response body

### Requirement: send_http body_from_binary_file for POST (multipart)
The `send_http` action SHALL accept `body_from_binary_file` and `binary_file_name` fields. When `method` is `POST`, the binary file SHALL be sent as `multipart/form-data` with field name `file`.

#### Scenario: POST sends binary as multipart
- **WHEN** `send_http` has `method: POST` and `body_from_binary_file: data/payload.bin`
- **THEN** the outbound request uses `Content-Type: multipart/form-data` and includes the file under field `file`

#### Scenario: binary_file_name used as multipart filename
- **WHEN** `binary_file_name: upload.bin` is set
- **THEN** the multipart part's filename is `upload.bin`

#### Scenario: Basename used as filename when binary_file_name absent
- **WHEN** `body_from_binary_file: data/payload.bin` is set without `binary_file_name`
- **THEN** the multipart part's filename is `payload.bin`

#### Scenario: Default content type for multipart part is application/octet-stream
- **WHEN** no header overrides the file part's content type
- **THEN** the multipart part uses `Content-Type: application/octet-stream`

### Requirement: send_http body_from_binary_file for non-POST (raw body)
When `send_http` has a method other than `POST` and `body_from_binary_file` is set, the binary bytes SHALL be sent as the raw request body.

#### Scenario: PUT sends raw binary body
- **WHEN** `send_http` has `method: PUT` and `body_from_binary_file: data/payload.bin`
- **THEN** the outbound request body contains the raw binary bytes
