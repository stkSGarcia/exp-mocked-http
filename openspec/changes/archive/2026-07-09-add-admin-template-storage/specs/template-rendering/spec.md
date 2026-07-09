## ADDED Requirements

> Extends: template-rendering/add-stateful-actions

### Requirement: Reserved Redis Keyspace
The template renderer SHALL block `redisDo` from executing commands against `__hmock_internal:*` keys.

#### Scenario: Internal base template key is blocked
- **WHEN** a template expression calls `redisDo` with a command targeting `__hmock_internal:templates`
- **THEN** the system SHALL treat the operation as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: Internal template set key is blocked
- **WHEN** a template expression calls `redisDo` with a command targeting an internal template-set storage key under `__hmock_internal:*`
- **THEN** the system SHALL treat the operation as a template render error
- **AND** the system SHALL NOT execute the Redis command

### Requirement: Redis Function Safety
The system SHALL continue to support `redisDo` in every template expression context for non-internal keys while reserving the internal persistence keyspace. (adapts template-rendering/add-stateful-actions/redis-template-function)

#### Scenario: Non-internal redis key remains available
- **WHEN** a template expression calls `redisDo` with a supported command targeting a key outside `__hmock_internal:*`
- **THEN** the system SHALL evaluate the Redis command according to the existing `redisDo` behavior
