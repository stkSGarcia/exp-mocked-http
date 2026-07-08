## MODIFIED Requirements

> Extends: template-rendering/add-stateful-actions

### Requirement: Redis Template Function
The system SHALL support `redisDo` in every template expression context except when the Redis command touches the internal `__hmock_internal:*` keyspace.

#### Scenario: Redis function is available to response bodies
- **WHEN** a response body template uses `redisDo` for a non-internal key
- **THEN** the system SHALL evaluate the Redis command and render the returned string in the response body

#### Scenario: Redis function is available to response headers
- **WHEN** a response header template uses `redisDo` for a non-internal key
- **THEN** the system SHALL evaluate the Redis command and render the returned string in the response header

#### Scenario: Redis function is available to redis action items
- **WHEN** a `redis` action item template uses `redisDo` for a non-internal key
- **THEN** the system SHALL evaluate the nested Redis command while rendering that Redis action item

#### Scenario: Redis function blocks internal keys
- **WHEN** any template expression uses `redisDo` for a key matching `__hmock_internal:*`
- **THEN** the system SHALL treat the operation as a template render error
- **AND** it SHALL NOT execute the Redis command

### Requirement: Redis Command Support
The system SHALL support the required Redis command set through `redisDo` and rendered `redis` action items while refusing commands that target the internal `__hmock_internal:*` keyspace.

#### Scenario: Hash commands execute for non-internal keys
- **WHEN** a template or Redis action item executes `HSET`, `HGET`, `HGETALL`, or `HDEL` against a non-internal key
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Unsupported Redis command fails rendering
- **WHEN** a template or Redis action item executes a Redis command outside the supported command set
- **THEN** the system SHALL treat the operation as a template render error

#### Scenario: Supported Redis command for internal key fails rendering
- **WHEN** a template or Redis action item executes a supported command against a key matching `__hmock_internal:*`
- **THEN** the system SHALL treat the operation as a template render error
- **AND** it SHALL NOT execute the command against the configured Redis backend

