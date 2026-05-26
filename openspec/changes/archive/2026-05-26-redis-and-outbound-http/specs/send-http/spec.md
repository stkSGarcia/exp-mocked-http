## ADDED Requirements

### Requirement: send_http action
The `send_http` action SHALL make an outbound HTTP request as a side effect when a behavior is matched. The action SHALL accept the following fields: `url` (string, required — rendered as a template), `method` (string, required), `headers` (string map, optional — each value rendered as a template), `body` (string, optional — rendered as a template), `body_from_file` (string, optional — path resolved relative to `HM_TEMPLATES_DIR`, loaded at startup and rendered at request time). Outbound request failures SHALL NOT affect mock execution or the inbound response.

#### Scenario: Outbound request is sent
- **WHEN** a behavior with `send_http: {url: "http://example.com/hook", method: POST, body: "{{ HTTPBody }}"}` handles a request
- **THEN** an HTTP POST is made to `http://example.com/hook` with the request body as its body

#### Scenario: Failure does not affect inbound response
- **WHEN** the `send_http` target URL is unreachable or returns an error
- **THEN** the mock server still sends its configured `reply_http` response with the expected status code

#### Scenario: URL rendered as template
- **WHEN** `url: "http://hooks.example.com/{{ HTTPHeader.Get "X-Tenant" }}"` and request has `X-Tenant: acme`
- **THEN** the outbound request is made to `http://hooks.example.com/acme`

#### Scenario: Headers rendered as templates
- **WHEN** `headers: {Authorization: "Bearer {{ redisDo \"GET\" \"token\" }}"}`
- **THEN** the outbound request includes the `Authorization` header with the Redis-resolved value

#### Scenario: body_from_file used for outbound body
- **WHEN** `body_from_file: payloads/webhook.json` is set and `body` is empty
- **THEN** the file contents (rendered as a template) are used as the outbound request body

#### Scenario: body takes precedence when both set
- **WHEN** both `body` and `body_from_file` are set
- **THEN** `body_from_file` is used only when `body` is empty (same precedence rule as reply_http)

### Requirement: send_http and reply_http can coexist
A behavior MAY include both `send_http` and `reply_http` actions. The outbound request SHALL be dispatched before the inbound response is written but SHALL NOT block the response.

#### Scenario: Both actions execute
- **WHEN** a behavior has `send_http` followed by `reply_http` in its actions list
- **THEN** the outbound request is dispatched and the configured HTTP response is returned to the caller
