## ADDED Requirements

> Extends: http-behavior-mocking/add-template-helpers-file-backed-bodies

### Requirement: HTTP Reply Evaluation Result
The system SHALL reuse HTTP reply rendering behavior when producing side-effect-free `reply_http_action_performed` evaluation results.

#### Scenario: Evaluated HTTP reply includes rendered headers
- **GIVEN** matching and condition evaluation pass
- **AND** a `reply_http` action contains templated headers
- **WHEN** the mock is evaluated through `/api/v1/evaluate`
- **THEN** the `reply_http_action_performed` result includes rendered custom headers
- **AND** generated `Content-Type` and `Content-Length` headers

#### Scenario: Evaluated HTTP reply defaults content type
- **GIVEN** matching and condition evaluation pass
- **AND** a `reply_http` action omits content type
- **WHEN** the mock is evaluated through `/api/v1/evaluate`
- **THEN** the `reply_http_action_performed` result reports `content_type` as `application/json`
