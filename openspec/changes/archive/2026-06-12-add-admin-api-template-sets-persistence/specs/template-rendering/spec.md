## ADDED Requirements

### Requirement: Reserved Redis Keyspace Protection
The system SHALL prevent `redisDo` from executing commands against the internal Redis keyspace `__hmock_internal:*`.

#### Scenario: Internal templates key is blocked
- **WHEN** a template calls `redisDo` with a command that targets `__hmock_internal:templates`
- **THEN** the system SHALL treat the call as a template render error and SHALL NOT execute the Redis command

#### Scenario: Internal template set key is blocked
- **WHEN** a template calls `redisDo` with a command that targets a template-set storage key under `__hmock_internal:*`
- **THEN** the system SHALL treat the call as a template render error and SHALL NOT execute the Redis command

#### Scenario: Internal key pattern is blocked
- **WHEN** a template calls `redisDo` with a key or key-pattern argument that matches `__hmock_internal:*`
- **THEN** the system SHALL treat the call as a template render error and SHALL NOT execute the Redis command

#### Scenario: Non-internal Redis key remains available
- **WHEN** a template calls `redisDo` with a supported command that does not target `__hmock_internal:*`
- **THEN** the system SHALL evaluate the command using the configured Redis backend
