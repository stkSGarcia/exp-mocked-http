## ADDED Requirements

### Requirement: Redis backend configuration
The system SHALL provide Redis-compatible state storage configured by environment variables.

#### Scenario: Default Redis backend is memory
- **WHEN** the server starts without `HM_REDIS_TYPE` or `HM_REDIS_URL`
- **THEN** it uses an embedded in-memory Redis-compatible store and the effective Redis URL default is `redis://redis:6379`

#### Scenario: External Redis backend is configured
- **WHEN** `HM_REDIS_TYPE` is set to `redis` and `HM_REDIS_URL` is set
- **THEN** the server uses the configured URL for external Redis command execution

#### Scenario: In-memory Redis state is process local
- **WHEN** the server uses the `memory` Redis backend
- **THEN** data written through Redis commands is not persisted across process restarts

### Requirement: Redis template command helper
The system SHALL provide a `redisDo` template function for executing supported Redis commands from any rendered template expression.

#### Scenario: redisDo is available in conditions
- **WHEN** a behavior condition calls `redisDo`
- **THEN** the Redis command is executed while evaluating whether the behavior matches

#### Scenario: redisDo is available in response bodies
- **WHEN** a `reply_http.body` or loaded `reply_http.body_from_file` template calls `redisDo`
- **THEN** the Redis command result is available in the rendered response body

#### Scenario: redisDo is available in response headers
- **WHEN** a `reply_http.headers` value template calls `redisDo`
- **THEN** the Redis command result is available in the rendered response header value

#### Scenario: redisDo is available in redis actions
- **WHEN** a `redis` action item template calls `redisDo`
- **THEN** the nested Redis command is executed during rendering before the rendered action item command is executed

### Requirement: Redis command support
The system SHALL support the Redis commands `SET`, `GET`, `RPUSH`, `LPUSH`, `LRANGE`, `LPOP`, `RPOP`, `HSET`, `HGET`, `HGETALL`, `HDEL`, `DEL`, `EXISTS`, and `KEYS`.

#### Scenario: String commands execute
- **WHEN** templates or actions execute `SET key value` followed by `GET key`
- **THEN** `GET key` returns `value` as a string

#### Scenario: List push commands execute
- **WHEN** templates or actions execute `RPUSH queue a`, `RPUSH queue b`, and `LPUSH queue z`
- **THEN** the list value for `queue` is ordered as `z`, `a`, `b`

#### Scenario: List range command returns joined array results
- **WHEN** templates or actions execute `LRANGE queue 0 -1` for a list containing `z`, `a`, and `b`
- **THEN** the command result is the string `z;;a;;b`

#### Scenario: List pop commands execute
- **WHEN** templates or actions execute `LPOP queue` or `RPOP queue`
- **THEN** the command returns the removed list value as a string

#### Scenario: Hash commands execute
- **WHEN** templates or actions execute `HSET user name Ada`, `HGET user name`, `HGETALL user`, and `HDEL user name`
- **THEN** hash fields can be set, read, listed, and deleted through the Redis backend

#### Scenario: Key commands execute
- **WHEN** templates or actions execute `DEL key`, `EXISTS key`, or `KEYS pattern`
- **THEN** keys can be deleted, checked for existence, and listed by pattern through the Redis backend

#### Scenario: Single-value results render as strings
- **WHEN** a supported Redis command returns a single value
- **THEN** the command result renders as that value's string form

#### Scenario: Array results use delimiter
- **WHEN** a supported Redis command returns multiple values
- **THEN** the command result joins those values with `;;`

#### Scenario: Delimited results can become template lists
- **WHEN** a template pipes an array command result through `splitList` with delimiter `;;`
- **THEN** the rendered template can iterate or index the returned values as a list

### Requirement: Redis action
The system SHALL support a `redis` action containing an array of template strings.

#### Scenario: Redis action items execute in order
- **WHEN** a matched behavior executes a `redis` action with multiple items
- **THEN** the server renders and executes each item as an independent Redis command in array order

#### Scenario: Later redis action items see earlier writes
- **WHEN** a `redis` action writes state in one item and reads that state in a later item
- **THEN** the later item observes the earlier write

#### Scenario: Redis action continues to later actions
- **WHEN** a matched behavior executes a `redis` action followed by `sleep`, `send_http`, or `reply_http`
- **THEN** the server continues executing later actions after the Redis action completes

### Requirement: Outbound HTTP side-effect action
The system SHALL support a `send_http` action that makes an outbound HTTP request as a side effect.

#### Scenario: Required send_http fields
- **WHEN** a behavior defines a `send_http` action
- **THEN** the action requires `url` and `method`

#### Scenario: send_http renders request fields
- **WHEN** a matched behavior executes `send_http` with templated `url`, `headers`, and `body`
- **THEN** the server renders the URL, every header value, and the body using the request context and available template functions before sending the outbound request

#### Scenario: send_http supports file-backed body
- **WHEN** a matched behavior executes `send_http` with `body_from_file` and no non-empty inline `body`
- **THEN** the server sends the loaded file content rendered as the outbound request body template

#### Scenario: Inline send_http body takes precedence
- **WHEN** a `send_http` action configures both a non-empty `body` and `body_from_file`
- **THEN** the server renders and sends the inline `body`

#### Scenario: Outbound failure does not fail inbound response
- **WHEN** a `send_http` outbound request fails
- **THEN** the server logs the failure and continues executing the matched behavior without failing mock execution or changing the inbound response because of that failure

### Requirement: Mixed side-effect action execution
The system SHALL allow a behavior to mix `redis`, `send_http`, `sleep`, and `reply_http` actions in one ordered action list.

#### Scenario: Mixed actions execute in listed order
- **WHEN** a matched behavior contains `redis`, `send_http`, `sleep`, and `reply_http` actions
- **THEN** the server executes side-effect and sleep actions in list order until `reply_http` produces the inbound response

#### Scenario: Reply still ends action processing
- **WHEN** a matched behavior executes `reply_http`
- **THEN** the server returns that response and does not execute later actions in the same behavior
