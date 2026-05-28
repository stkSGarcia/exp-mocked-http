## ADDED Requirements

### Requirement: Mock behavior validation accepts publish_kafka and publish_amqp action types
The server SHALL accept `publish_kafka` and `publish_amqp` as valid action types in `Behavior` and `AbstractBehavior` definitions, alongside the existing `sleep`, `reply_http`, `redis`, and `send_http` types.

#### Scenario: publish_kafka action accepted
- **WHEN** a behavior includes a `publish_kafka` action
- **THEN** the server loads the behavior without error

#### Scenario: publish_amqp action accepted
- **WHEN** a behavior includes a `publish_amqp` action
- **THEN** the server loads the behavior without error

## MODIFIED Requirements

### Requirement: Mock behavior validation
Each loaded behavior SHALL be validated: `key` is required and must be a non-empty string; `kind` defaults to `"Behavior"` when omitted; accepted `kind` values are `Behavior`, `AbstractBehavior`, and `Template` — any other `kind` SHALL be rejected; a behavior with more than one `reply_http` action SHALL be rejected. Valid action types are `sleep`, `reply_http`, `redis`, `send_http`, `publish_kafka`, and `publish_amqp`. Each kind enforces an allowed-field rule: `Template` MAY only contain `key`, `kind`, and `template`; `AbstractBehavior` MAY contain `key`, `kind`, `expect`, `actions`, and `values`; `Behavior` MAY contain `key`, `kind`, `extend`, `expect`, `actions`, and `values`. Fields not in the allowed set SHALL be rejected at load time.

#### Scenario: Missing key rejected
- **WHEN** a behavior definition omits `key`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Multiple reply_http rejected
- **WHEN** a behavior has two or more `reply_http` actions
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Kind defaults to Behavior
- **WHEN** a behavior definition omits `kind`
- **THEN** the behavior is treated as `kind: Behavior`

#### Scenario: Unknown kind rejected
- **WHEN** a behavior defines `kind: Widget`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Template with disallowed field rejected
- **WHEN** a `Template` definition includes an `actions` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: AbstractBehavior with template field rejected
- **WHEN** an `AbstractBehavior` definition includes a `template` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Behavior with template field rejected
- **WHEN** a `Behavior` definition includes a `template` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: redis action accepted
- **WHEN** a behavior includes a `redis` action
- **THEN** the server loads the behavior without error

#### Scenario: send_http action accepted
- **WHEN** a behavior includes a `send_http` action
- **THEN** the server loads the behavior without error

#### Scenario: publish_kafka action accepted
- **WHEN** a behavior includes a `publish_kafka` action
- **THEN** the server loads the behavior without error

#### Scenario: publish_amqp action accepted
- **WHEN** a behavior includes a `publish_amqp` action
- **THEN** the server loads the behavior without error
