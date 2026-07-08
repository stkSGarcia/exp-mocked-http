## ADDED Requirements

> Extends: mock-definition-loading/add-stateful-actions
> Extends: http-behavior-mocking/add-stateful-actions

### Requirement: CORS Runtime Configuration
The mock HTTP server SHALL read `HM_CORS_ENABLED` as a boolean runtime configuration value with default `false`.

#### Scenario: Default disables CORS
- **GIVEN** `HM_CORS_ENABLED` is absent from the environment
- **WHEN** the server reads runtime configuration
- **THEN** global CORS handling SHALL be disabled

### Requirement: Global CORS Headers
When `HM_CORS_ENABLED` is enabled, the mock HTTP server SHALL add global CORS headers to every response: `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, and `Access-Control-Allow-Credentials: true`.

#### Scenario: Headers added to matched mock response
- **GIVEN** `HM_CORS_ENABLED` is enabled
- **WHEN** a request matches a mock behavior and the server returns a response
- **THEN** the response SHALL include the global CORS headers

#### Scenario: CORS disabled omits global headers
- **GIVEN** `HM_CORS_ENABLED` is disabled
- **WHEN** the server returns a mock response
- **THEN** the server SHALL NOT add global CORS headers unless the mock definition provides them

### Requirement: Mock CORS Header Precedence
When `HM_CORS_ENABLED` is enabled and middleware and a mock response both set the same CORS header, the mock HTTP server SHALL keep the mock-defined header value.

#### Scenario: Mock-defined CORS value wins
- **GIVEN** `HM_CORS_ENABLED` is enabled
- **AND** a matched mock response defines `Access-Control-Allow-Origin: https://example.test`
- **WHEN** the server returns that response
- **THEN** `Access-Control-Allow-Origin` SHALL be `https://example.test`
- **AND** other missing global CORS headers SHALL still be added

### Requirement: CORS Preflight Fallback
When `HM_CORS_ENABLED` is enabled, the mock HTTP server SHALL first try normal mock matching, including explicit `OPTIONS` behaviors, and SHALL treat unmatched `OPTIONS` requests as CORS preflight responses with `200 OK`, an empty body, and the global CORS headers.

#### Scenario: Explicit OPTIONS mock wins
- **GIVEN** `HM_CORS_ENABLED` is enabled
- **AND** a mock behavior matches an `OPTIONS` request
- **WHEN** the server handles that request
- **THEN** the server SHALL return the matched mock behavior response

#### Scenario: Unmatched OPTIONS returns preflight
- **GIVEN** `HM_CORS_ENABLED` is enabled
- **AND** no mock behavior matches an `OPTIONS` request
- **WHEN** the server handles that request
- **THEN** the server SHALL return `200 OK`
- **AND** the response body SHALL be empty
- **AND** the response SHALL include the global CORS headers

#### Scenario: Unmatched OPTIONS without CORS follows normal unmatched behavior
- **GIVEN** `HM_CORS_ENABLED` is disabled
- **AND** no mock behavior matches an `OPTIONS` request
- **WHEN** the server handles that request
- **THEN** the server SHALL use the normal unmatched-request behavior
