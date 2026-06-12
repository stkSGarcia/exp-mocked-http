## ADDED Requirements

### Requirement: Reserved Internal Redis Keyspace
The system SHALL prevent template-accessible Redis commands from touching internal persistence keys matching `__hmock_internal:*`.

#### Scenario: Redis function blocks internal template key
- **WHEN** a template uses `redisDo` with a command that targets `__hmock_internal:templates`
- **THEN** the system SHALL treat the call as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: Redis function blocks internal template set key
- **WHEN** a template uses `redisDo` with a command that targets a template-set storage key matching `__hmock_internal:template_sets:*`
- **THEN** the system SHALL treat the call as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: Redis function blocks internal wildcard key
- **WHEN** a template uses `redisDo` with a key pattern matching `__hmock_internal:*`
- **THEN** the system SHALL treat the call as a template render error
- **AND** the system SHALL NOT execute the Redis command

#### Scenario: User keyspace remains available
- **WHEN** a template uses `redisDo` with a supported command that targets a key outside `__hmock_internal:*`
- **THEN** the system SHALL execute the command using the configured Redis backend
