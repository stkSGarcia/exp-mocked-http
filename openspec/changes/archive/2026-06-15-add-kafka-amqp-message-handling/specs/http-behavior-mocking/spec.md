## MODIFIED Requirements

### Requirement: Action Execution
The system SHALL execute the selected behavior's actions in stable ascending `order` and stop evaluating further behaviors.

#### Scenario: Sleep delays next action
- **WHEN** a selected behavior contains a `sleep` action with a supported duration
- **THEN** the system SHALL pause for that duration before executing the next ordered action

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

#### Scenario: Kafka publish action renders message fields
- **WHEN** a selected HTTP behavior executes `publish_kafka`
- **THEN** the system SHALL render the action's `topic` and payload using the same request context and template functions available to response bodies

#### Scenario: AMQP publish action renders message fields
- **WHEN** a selected HTTP behavior executes `publish_amqp`
- **THEN** the system SHALL render the action's `exchange`, `routing_key`, and payload using the same request context and template functions available to response bodies

#### Scenario: Mixed actions with equal order execute in declared order
- **WHEN** a selected behavior mixes `redis`, `send_http`, `publish_kafka`, `publish_amqp`, `sleep`, and `reply_http` actions and those actions have the same effective `order`
- **THEN** the system SHALL execute those actions in the order declared by the effective behavior

#### Scenario: Actions are sorted by ascending order
- **WHEN** a selected behavior contains actions with different `order` values
- **THEN** the system SHALL execute lower order values before higher order values

#### Scenario: Missing action order defaults to zero
- **WHEN** a selected behavior contains an action without `order`
- **THEN** the system SHALL treat that action's order as `0`

#### Scenario: Negative action order is accepted
- **WHEN** a selected behavior contains an action with a negative `order`
- **THEN** the system SHALL execute that action before actions with greater order values

#### Scenario: Equal action order is stable
- **WHEN** a selected behavior contains multiple actions with the same effective `order`
- **THEN** the system SHALL preserve those actions' original relative order

#### Scenario: Inherited actions are included in ordering
- **WHEN** a selected behavior includes actions inherited from a parent and actions declared on the child
- **THEN** the system SHALL sort all inherited and child actions together by effective `order`
