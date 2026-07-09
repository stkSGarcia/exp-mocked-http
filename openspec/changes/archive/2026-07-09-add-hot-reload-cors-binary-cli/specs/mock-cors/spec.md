## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions

### Requirement: CORS Configuration
The system SHALL read `HM_CORS_ENABLED` from runtime configuration using a default of `false`.

#### Scenario: Default CORS disabled
- **WHEN** runtime configuration is loaded without `HM_CORS_ENABLED`
- **THEN** global mock HTTP CORS handling is disabled

#### Scenario: CORS enabled by environment
- **WHEN** runtime configuration is loaded with `HM_CORS_ENABLED=true`
- **THEN** global mock HTTP CORS handling is enabled

### Requirement: Global CORS Headers
The mock HTTP server SHALL add global CORS headers to every mock HTTP response when CORS is enabled.

#### Scenario: Headers added to matched mock response
- **GIVEN** CORS is enabled
- **WHEN** a mock HTTP request matches a behavior
- **THEN** the response includes `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`

#### Scenario: Headers added to unmatched response
- **GIVEN** CORS is enabled
- **WHEN** a mock HTTP request does not match a behavior
- **THEN** the response includes the global CORS headers

### Requirement: Mock Header Precedence
The mock HTTP server SHALL preserve mock-defined CORS header values when a matched `reply_http.headers` entry sets the same header as global CORS handling.

#### Scenario: Mock-defined CORS value wins
- **GIVEN** CORS is enabled
- **WHEN** a matched `reply_http` defines `Access-Control-Allow-Origin: https://example.test`
- **THEN** the response keeps `Access-Control-Allow-Origin: https://example.test`

### Requirement: CORS Preflight Fallback
The mock HTTP server SHALL try normal mock matching before treating unmatched `OPTIONS` requests as CORS preflight requests.

#### Scenario: Explicit OPTIONS mock wins
- **GIVEN** CORS is enabled
- **WHEN** an `OPTIONS` request matches a mock behavior
- **THEN** the server returns the matched mock response with applicable CORS headers

#### Scenario: Unmatched OPTIONS returns preflight
- **GIVEN** CORS is enabled
- **WHEN** an `OPTIONS` request does not match a mock behavior
- **THEN** the server returns `200 OK` with an empty body and the global CORS headers

#### Scenario: Unmatched OPTIONS without CORS remains not found
- **GIVEN** CORS is disabled
- **WHEN** an `OPTIONS` request does not match a mock behavior
- **THEN** the server returns the normal unmatched response
