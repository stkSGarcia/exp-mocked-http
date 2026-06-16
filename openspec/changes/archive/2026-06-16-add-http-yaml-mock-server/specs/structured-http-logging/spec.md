## ADDED Requirements

### Requirement: Structured JSON Logs
The system SHALL emit logs as structured JSON objects.

#### Scenario: Log entry is JSON
- **WHEN** the system emits a log entry
- **THEN** the log entry SHALL be valid JSON

### Requirement: Log Level Filtering
The system SHALL honor `HM_LOG_LEVEL` values `debug`, `info`, `warn`, and `error`.

#### Scenario: Info log level emits request logs
- **WHEN** `HM_LOG_LEVEL` is `info`
- **THEN** the system SHALL emit request and response pair logs at `info`

#### Scenario: Higher log level suppresses info
- **WHEN** `HM_LOG_LEVEL` is `warn` or `error`
- **THEN** the system SHALL suppress `info` request and response pair logs

### Requirement: HTTP Request Response Logs
The system SHALL log each HTTP request and response pair at `info` when the configured log level allows it.

#### Scenario: Request response log fields are present
- **WHEN** the system completes handling an HTTP request
- **THEN** the info log SHALL include `http_path`, `http_method`, `http_host`, `http_req`, and `http_res`

#### Scenario: Unmatched request is logged
- **WHEN** the system returns the default 404 response for an unmatched request
- **THEN** the system SHALL log the request and response pair with the same required HTTP fields

### Requirement: Duplicate Key Warning Logs
The system SHALL log duplicate mock key overrides at warning level.

#### Scenario: Duplicate key warning is emitted
- **WHEN** a loaded behavior overrides an earlier behavior with the same `key`
- **THEN** the system SHALL emit a structured warning log describing the duplicate key override
