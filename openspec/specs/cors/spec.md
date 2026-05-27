# cors

## Purpose

TBD

## Requirements

### Requirement: CORS enabled via environment variable
The server SHALL read `HM_CORS_ENABLED` at startup. When the value is `true`, the server SHALL add CORS headers to every response from the mock HTTP server. When the value is `false` (default), no CORS headers are added by the server unless defined in a mock's `reply_http.headers`.

#### Scenario: Default disables CORS
- **WHEN** the server starts with no `HM_CORS_ENABLED` set
- **THEN** CORS headers are not added to responses by the server

#### Scenario: Explicit true enables CORS
- **WHEN** `HM_CORS_ENABLED=true`
- **THEN** every response includes the four CORS headers

### Requirement: Global CORS headers on every response
When `HM_CORS_ENABLED=true`, the server SHALL add the following headers to every response from the mock HTTP server:
- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: *`
- `Access-Control-Allow-Headers: *`
- `Access-Control-Allow-Credentials: true`

#### Scenario: CORS headers present on matched response
- **WHEN** `HM_CORS_ENABLED=true` and a request matches a behavior
- **THEN** the response includes all four CORS headers

#### Scenario: CORS headers present on 404 response
- **WHEN** `HM_CORS_ENABLED=true` and no behavior matches the request
- **THEN** the 404 response includes all four CORS headers

### Requirement: Mock-defined CORS headers take precedence
When `HM_CORS_ENABLED=true` and a mock's `reply_http.headers` includes a CORS header, the mock-defined value SHALL override the global CORS header value.

#### Scenario: Mock header overrides middleware header
- **WHEN** `HM_CORS_ENABLED=true` and a behavior sets `Access-Control-Allow-Origin: https://example.com`
- **THEN** the response contains `Access-Control-Allow-Origin: https://example.com` (not `*`)

### Requirement: Unmatched OPTIONS treated as CORS preflight
When `HM_CORS_ENABLED=true`, an OPTIONS request that does not match any loaded behavior SHALL be handled as a CORS preflight: the server SHALL return `200 OK` with an empty body and the four global CORS headers.

#### Scenario: Unmatched OPTIONS returns 200 with CORS headers
- **WHEN** `HM_CORS_ENABLED=true` and an OPTIONS request arrives with no matching behavior
- **THEN** the server returns `200 OK`, empty body, and all four CORS headers

#### Scenario: Matched OPTIONS behavior takes priority
- **WHEN** `HM_CORS_ENABLED=true` and an OPTIONS request matches a loaded behavior
- **THEN** the matched behavior's response is used (not the preflight 200), and CORS headers are still added

#### Scenario: CORS disabled OPTIONS falls through to 404
- **WHEN** `HM_CORS_ENABLED=false` and an OPTIONS request arrives with no matching behavior
- **THEN** the server returns `404` as it would for any other unmatched request
