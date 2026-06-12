## ADDED Requirements

### Requirement: Reserved Redis Keyspace
The system SHALL prevent user templates and behavior Redis actions from accessing the internal Redis keyspace `__hmock_internal:*`.

#### Scenario: Redis template function blocks internal templates key
- **WHEN** a template calls `redisDo` with a Redis command targeting `__hmock_internal:templates`
- **THEN** the system SHALL fail the call as a template render error and SHALL NOT execute the Redis command

#### Scenario: Redis template function blocks internal template-set keys
- **WHEN** a template calls `redisDo` with a Redis command targeting a key matching `__hmock_internal:*`
- **THEN** the system SHALL fail the call as a template render error and SHALL NOT execute the Redis command

#### Scenario: Redis action blocks internal keyspace
- **WHEN** a rendered `redis` action command targets a key matching `__hmock_internal:*`
- **THEN** the system SHALL fail that rendered command as a template render error and SHALL NOT execute the Redis command
