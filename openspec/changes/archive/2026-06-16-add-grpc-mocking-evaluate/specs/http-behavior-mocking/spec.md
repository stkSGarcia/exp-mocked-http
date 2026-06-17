## ADDED Requirements

> Extends: http-behavior-mocking/add-http-yaml-mock-server

### Requirement: HTTP Dry-Run Reply Projection
The system SHALL project `reply_http` actions into dry-run evaluation results using the same response defaults as real HTTP replies.

#### Scenario: Default content type is projected
- **GIVEN** dry-run evaluation renders a `reply_http` action without a `Content-Type` header
- **WHEN** the evaluation response is built
- **THEN** the `reply_http_action_performed` result SHALL set `content_type` to `application/json`
- **AND** include `Content-Type: application/json` in `headers`

#### Scenario: Explicit content type is projected
- **GIVEN** dry-run evaluation renders a `reply_http` action with a `Content-Type` header
- **WHEN** the evaluation response is built
- **THEN** the `reply_http_action_performed` result SHALL preserve that content type

#### Scenario: Content length is projected
- **GIVEN** dry-run evaluation renders a `reply_http` body
- **WHEN** the evaluation response is built
- **THEN** the `reply_http_action_performed` result SHALL include `Content-Length` in `headers`

#### Scenario: Status code is string
- **GIVEN** dry-run evaluation renders a `reply_http` action
- **WHEN** the evaluation response is built
- **THEN** the `reply_http_action_performed.status_code` value SHALL be a string
