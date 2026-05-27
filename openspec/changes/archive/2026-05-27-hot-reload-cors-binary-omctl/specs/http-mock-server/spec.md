## MODIFIED Requirements

### Requirement: Server startup via environment configuration
The server SHALL read configuration from environment variables at startup: `HM_TEMPLATES_DIR` (default `./templates`), `HM_HTTP_PORT` (default `9999`), `HM_HTTP_HOST` (default `0.0.0.0`), `HM_LOG_LEVEL` (default `info`, values: `debug`, `info`, `warn`, `error`), `HM_TEMPLATES_DIR_HOT_RELOAD` (default `true`), and `HM_CORS_ENABLED` (default `false`).

#### Scenario: Default configuration startup
- **WHEN** the server starts with no environment variables set
- **THEN** it listens on `0.0.0.0:9999`, scans `./templates` for mock files, and starts with hot reload active and CORS disabled

#### Scenario: Custom port and host
- **WHEN** `HM_HTTP_PORT=8080` and `HM_HTTP_HOST=127.0.0.1` are set
- **THEN** the server listens on `127.0.0.1:8080`

#### Scenario: Hot reload disabled at startup
- **WHEN** `HM_TEMPLATES_DIR_HOT_RELOAD=false`
- **THEN** the server does not watch for filesystem changes after startup

#### Scenario: CORS enabled at startup
- **WHEN** `HM_CORS_ENABLED=true`
- **THEN** the server adds CORS headers to every response

### Requirement: reply_http action
The `reply_http` action SHALL send an HTTP response with the configured `status_code`, `headers` (each value rendered as a template), and `body` (rendered as a template). It SHALL also accept `body_from_binary_file` (path relative to `HM_TEMPLATES_DIR`, binary bytes loaded at startup, sent as-is) and `binary_file_name` (optional filename for `Content-Disposition`). `Content-Type` SHALL default to `application/json` unless overridden. `Content-Length` SHALL be set from the rendered body length or the binary file size.

#### Scenario: Default Content-Type
- **WHEN** `reply_http` has no `headers` field
- **THEN** response includes `Content-Type: application/json`

#### Scenario: Content-Length set automatically
- **WHEN** `body: "hello"` (5 bytes)
- **THEN** response includes `Content-Length: 5`

#### Scenario: Header override
- **WHEN** `headers: {Content-Type: text/plain}`
- **THEN** response `Content-Type` is `text/plain`

#### Scenario: Binary file body served
- **WHEN** `body_from_binary_file: assets/image.png` is set
- **THEN** the response body contains the exact bytes from the file and Content-Length is set from its size

#### Scenario: binary_file_name adds Content-Disposition
- **WHEN** `binary_file_name: photo.jpg` is set
- **THEN** the response includes `Content-Disposition: inline; filename="photo.jpg"`
