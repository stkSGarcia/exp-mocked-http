## ADDED Requirements

> Extends: template-rendering/add-stateful-actions

### Requirement: Internal Redis Keyspace Protection (adapts template-rendering/add-stateful-actions/redis-template-function)
The template renderer SHALL block `redisDo` calls from touching any Redis key in the internal keyspace `__hmock_internal:*`.

#### Scenario: Base template storage key is blocked
- **GIVEN** a template expression calls `redisDo` for `__hmock_internal:templates`
- **WHEN** the expression is rendered
- **THEN** the system SHALL fail rendering with a template render error
- **AND** it SHALL NOT execute the Redis command

#### Scenario: Template-set storage key is blocked
- **GIVEN** a template expression calls `redisDo` for an internal template-set storage key matching `__hmock_internal:*`
- **WHEN** the expression is rendered
- **THEN** the system SHALL fail rendering with a template render error
- **AND** it SHALL NOT execute the Redis command

### Requirement: Internal Keyspace Command Blocking (adapts template-rendering/add-stateful-actions/redis-command-support)
The system SHALL apply the internal keyspace block before executing supported Redis commands through `redisDo`.

#### Scenario: Supported command is blocked before execution
- **GIVEN** a template expression calls a supported Redis command through `redisDo`
- **AND** the command targets a key matching `__hmock_internal:*`
- **WHEN** the expression is rendered
- **THEN** the system SHALL treat the operation as a template render error
- **AND** it SHALL NOT execute the command against the configured Redis backend

