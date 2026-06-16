## ADDED Requirements

> Extends: template-rendering

### Requirement: Reserved Redis Keyspace Protection
The system SHALL prevent `redisDo` from touching Redis keys under the internal `__hmock_internal:*` keyspace.

#### Scenario: Internal template storage key is blocked
- **WHEN** a template render evaluates `redisDo` with a command targeting `__hmock_internal:templates`
- **THEN** rendering SHALL fail as a template render error and the Redis command SHALL NOT execute

#### Scenario: Internal template-set storage key is blocked
- **WHEN** a template render evaluates `redisDo` with a command targeting an internal template-set storage key under `__hmock_internal:*`
- **THEN** rendering SHALL fail as a template render error and the Redis command SHALL NOT execute

#### Scenario: Non-internal key is allowed
- **WHEN** a template render evaluates `redisDo` with a supported command targeting a key outside `__hmock_internal:*`
- **THEN** the system SHALL execute the command according to existing Redis command support behavior
