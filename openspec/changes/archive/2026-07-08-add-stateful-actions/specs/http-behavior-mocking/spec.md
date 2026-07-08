## MODIFIED Requirements

### Requirement: Action Execution
The system SHALL execute the selected behavior's actions in their declared order and stop evaluating further behaviors.

#### Scenario: Sleep delays next action
- **WHEN** a selected behavior contains a `sleep` action with a supported duration
- **THEN** the system SHALL pause for that duration before executing the next action

#### Scenario: Unsupported sleep duration is invalid
- **WHEN** a `sleep` action uses a duration without one of `ns`, `us`, `ms`, `s`, `m`, or `h`
- **THEN** the system SHALL reject the action as invalid

#### Scenario: Reply action sends response
- **WHEN** a selected behavior executes `reply_http`
- **THEN** the system SHALL send the configured HTTP status, rendered headers, and rendered body

#### Scenario: Redis action renders command templates in order
- **WHEN** a selected behavior contains a `redis` action with multiple command template strings
- **THEN** the system SHALL render each command template independently and execute the rendered Redis commands in array order

#### Scenario: Outbound HTTP action renders request fields
- **WHEN** a selected behavior executes `send_http`
- **THEN** the system SHALL render the action's `url`, header values, and body using the same request context and template functions available to response bodies

#### Scenario: Outbound HTTP file body renders
- **WHEN** a selected behavior executes `send_http` with `body_from_file`
- **THEN** the system SHALL render the loaded file content as the outbound HTTP request body

#### Scenario: Outbound HTTP inline body takes precedence
- **WHEN** a `send_http` action defines both a non-empty `body` and `body_from_file`
- **THEN** the system SHALL render and send the inline `body`

#### Scenario: Outbound HTTP failure does not replace inbound response
- **WHEN** a selected behavior executes `send_http` and the outbound request fails
- **THEN** the system SHALL continue mock action execution and preserve the inbound response produced by the behavior

#### Scenario: Mixed actions execute in declared order
- **WHEN** a selected behavior mixes `redis`, `send_http`, `sleep`, and `reply_http` actions
- **THEN** the system SHALL execute those actions in the order declared by the behavior
