## ADDED Requirements

### Requirement: CORS configuration
The system SHALL read `HM_CORS_ENABLED` as a boolean setting with a default value of `false`.

#### Scenario: CORS disabled by default
- **WHEN** `HM_CORS_ENABLED` is omitted
- **THEN** the mock server does not add global CORS headers or synthesize preflight responses

#### Scenario: Invalid CORS setting
- **WHEN** `HM_CORS_ENABLED` is not a supported boolean value
- **THEN** configuration loading fails with an error naming `HM_CORS_ENABLED`

### Requirement: Global CORS response headers
When CORS is enabled, every response from the mock HTTP server SHALL include default values for `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`.

#### Scenario: Matched response receives CORS headers
- **GIVEN** CORS is enabled
- **WHEN** a request matches a mock behavior
- **THEN** the response includes all four global CORS headers

#### Scenario: Error response receives CORS headers
- **GIVEN** CORS is enabled
- **WHEN** a non-`OPTIONS` request has no matching behavior
- **THEN** the `404 Not Found` response includes all four global CORS headers

### Requirement: Mock-defined CORS precedence
The system SHALL preserve headers configured by `reply_http`, and a mock-defined CORS header SHALL override the corresponding global CORS default using case-insensitive header-name comparison.

#### Scenario: Mock header overrides middleware
- **GIVEN** CORS is enabled and a matching `reply_http` defines `access-control-allow-origin: https://client.example`
- **WHEN** the mock response is sent
- **THEN** the response contains the mock-defined origin value
- **AND** it does not contain a second `Access-Control-Allow-Origin` value

### Requirement: OPTIONS matching and preflight fallback
The mock server SHALL attempt normal behavior matching for every `OPTIONS` request before applying the CORS preflight fallback.

#### Scenario: Explicit OPTIONS behavior wins
- **GIVEN** CORS is enabled and an `OPTIONS` behavior matches the request
- **WHEN** the request is handled
- **THEN** the configured behavior determines the status and body
- **AND** global CORS defaults are added without replacing mock-defined CORS headers

#### Scenario: Unmatched OPTIONS becomes preflight
- **GIVEN** CORS is enabled and no behavior matches an `OPTIONS` request
- **WHEN** the request is handled
- **THEN** the server returns `200 OK`
- **AND** the response body is empty
- **AND** the response includes all four global CORS headers

#### Scenario: Disabled CORS keeps normal miss behavior
- **GIVEN** CORS is disabled and no behavior matches an `OPTIONS` request
- **WHEN** the request is handled
- **THEN** the server returns the normal `404 Not Found` response
