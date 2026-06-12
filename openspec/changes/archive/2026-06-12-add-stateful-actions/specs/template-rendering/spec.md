## ADDED Requirements

### Requirement: Redis Template Function
The system SHALL support `redisDo` in every template expression context.

#### Scenario: Redis function is available to conditions
- **WHEN** a behavior condition template uses `redisDo`
- **THEN** the system SHALL evaluate the Redis command and use the returned string while deciding whether the condition passes

#### Scenario: Redis function is available to response bodies
- **WHEN** a response body template uses `redisDo`
- **THEN** the system SHALL evaluate the Redis command and render the returned string in the response body

#### Scenario: Redis function is available to response headers
- **WHEN** a response header template uses `redisDo`
- **THEN** the system SHALL evaluate the Redis command and render the returned string in the response header

#### Scenario: Redis function is available to Redis action items
- **WHEN** a `redis` action item template uses `redisDo`
- **THEN** the system SHALL evaluate the nested Redis command while rendering that Redis action item

### Requirement: Redis Command Support
The system SHALL support the required Redis command set through `redisDo` and rendered `redis` action items.

#### Scenario: String commands execute
- **WHEN** a template or Redis action item executes `SET` or `GET`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: List write commands execute
- **WHEN** a template or Redis action item executes `RPUSH` or `LPUSH`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: List read commands execute
- **WHEN** a template or Redis action item executes `LRANGE`, `LPOP`, or `RPOP`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Hash commands execute
- **WHEN** a template or Redis action item executes `HSET`, `HGET`, `HGETALL`, or `HDEL`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Key commands execute
- **WHEN** a template or Redis action item executes `DEL`, `EXISTS`, or `KEYS`
- **THEN** the system SHALL execute the command against the configured Redis backend

#### Scenario: Unsupported Redis command fails rendering
- **WHEN** a template or Redis action item executes a Redis command outside the supported command set
- **THEN** the system SHALL treat the operation as a template render error

### Requirement: Redis Return Formatting
The system SHALL render Redis command results as strings.

#### Scenario: Single-value Redis result renders as string
- **WHEN** a Redis command returns a single value
- **THEN** the system SHALL render that value as a string

#### Scenario: Empty Redis result renders as empty string
- **WHEN** a Redis command returns no value
- **THEN** the system SHALL render an empty string

#### Scenario: Array Redis result joins with delimiter
- **WHEN** a Redis command returns an array result
- **THEN** the system SHALL render the values joined with `;;`

#### Scenario: Split list converts Redis array string
- **WHEN** a template passes a Redis array result string to `splitList ";;"`
- **THEN** the system SHALL return a list of the delimited values
