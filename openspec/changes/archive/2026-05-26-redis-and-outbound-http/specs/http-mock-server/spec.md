## MODIFIED Requirements

### Requirement: Mock behavior validation
Each loaded behavior SHALL be validated: `key` is required and must be a non-empty string; `kind` defaults to `"Behavior"` when omitted; a behavior with more than one `reply_http` action SHALL be rejected. Valid action types are `sleep`, `reply_http`, `redis`, and `send_http`.

#### Scenario: Missing key rejected
- **WHEN** a behavior definition omits `key`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Multiple reply_http rejected
- **WHEN** a behavior has two or more `reply_http` actions
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Kind defaults to Behavior
- **WHEN** a behavior definition omits `kind`
- **THEN** the behavior is treated as `kind: Behavior`

#### Scenario: redis action accepted
- **WHEN** a behavior includes a `redis` action
- **THEN** the server loads the behavior without error

#### Scenario: send_http action accepted
- **WHEN** a behavior includes a `send_http` action
- **THEN** the server loads the behavior without error
