# redis-state

## Purpose

TBD

## Requirements

### Requirement: Redis backend configuration
The server SHALL read `HM_REDIS_TYPE` (default `memory`) and `HM_REDIS_URL` (default `redis://redis:6379`) at startup. When `HM_REDIS_TYPE=memory`, an embedded in-memory Redis-compatible store SHALL be used and data SHALL be lost on restart. When `HM_REDIS_TYPE=redis`, the server SHALL connect to the external Redis instance at `HM_REDIS_URL`.

#### Scenario: Default in-memory backend
- **WHEN** `HM_REDIS_TYPE` is not set
- **THEN** the server starts with an in-memory Redis store with no external connection

#### Scenario: External Redis backend
- **WHEN** `HM_REDIS_TYPE=redis` and `HM_REDIS_URL=redis://localhost:6379`
- **THEN** the server connects to that Redis instance

#### Scenario: In-memory data lost on restart
- **WHEN** `HM_REDIS_TYPE=memory` and a key is set, then the server restarts
- **THEN** the key is no longer present

### Requirement: redisDo template function
The server SHALL provide a `redisDo(cmd, *args)` template function usable in conditions, bodies, headers, and `redis` action items. It SHALL execute the given Redis command synchronously against the configured backend and return the result as a string. Single-value results SHALL be returned as strings. Array results SHALL be joined with `;;` as the delimiter.

#### Scenario: GET returns stored value
- **WHEN** `redisDo "SET" "k" "v"` is called followed by `{{ redisDo "GET" "k" }}`
- **THEN** the second call returns `"v"`

#### Scenario: Array result joined with ;;
- **WHEN** `LRANGE` returns `["a", "b", "c"]`
- **THEN** `redisDo "LRANGE" "mylist" "0" "-1"` returns `"a;;b;;c"`

#### Scenario: splitList recovers array
- **WHEN** `redisDo "LRANGE" "mylist" "0" "-1" | splitList ";;"` is used in a template
- **THEN** the result is a list with one element per original value

#### Scenario: redisDo available in conditions
- **WHEN** a condition is `{{ redisDo "GET" "flag" | eq "on" }}` and the Redis key `flag` holds `"on"`
- **THEN** the condition evaluates to `true` and the behavior matches

#### Scenario: redisDo available in response body
- **WHEN** a body template contains `{{ redisDo "GET" "counter" }}`
- **THEN** the response body contains the current value of `counter` from Redis

### Requirement: Supported redisDo commands
`redisDo` SHALL support the following commands: `SET`, `GET`, `RPUSH`, `LPUSH`, `LRANGE`, `LPOP`, `RPOP`, `HSET`, `HGET`, `HGETALL`, `HDEL`, `DEL`, `EXISTS`, `KEYS`. `redisDo` SHALL reject any command whose first argument (the Redis key) matches the prefix `__hmock_internal:` by raising a template render error without executing the command.

#### Scenario: SET and GET
- **WHEN** `redisDo "SET" "key" "value"` is called
- **THEN** `redisDo "GET" "key"` returns `"value"`

#### Scenario: RPUSH and LRANGE
- **WHEN** `redisDo "RPUSH" "mylist" "a"` and `redisDo "RPUSH" "mylist" "b"` are called
- **THEN** `redisDo "LRANGE" "mylist" "0" "-1"` returns `"a;;b"`

#### Scenario: HSET and HGET
- **WHEN** `redisDo "HSET" "myhash" "field" "val"` is called
- **THEN** `redisDo "HGET" "myhash" "field"` returns `"val"`

#### Scenario: DEL removes key
- **WHEN** `redisDo "DEL" "key"` is called after setting a value
- **THEN** `redisDo "EXISTS" "key"` returns `"0"`

#### Scenario: KEYS returns matching keys
- **WHEN** keys `foo`, `bar`, `baz` exist and `redisDo "KEYS" "*"` is called
- **THEN** all three keys appear in the `;;`-joined result

#### Scenario: Reserved keyspace blocked
- **WHEN** `redisDo "SET" "__hmock_internal:templates" "x"` is called in a template
- **THEN** a template render error occurs and the Redis command is not executed

#### Scenario: Reserved keyspace prefix checked for all commands
- **WHEN** `redisDo "GET" "__hmock_internal:tset:foo"` is called in a template
- **THEN** a template render error occurs and the Redis command is not executed

#### Scenario: Non-reserved keys unaffected
- **WHEN** `redisDo "SET" "my_app_key" "value"` is called
- **THEN** the command executes normally and returns the Redis response

### Requirement: redis action
The `redis` action SHALL be an ordered array of Jinja2 template strings. The server SHALL render each item in order using the full request context (including `redisDo`). The rendered output of each item SHALL be discarded; the purpose of each item is to invoke `redisDo` as a side effect.

#### Scenario: Multiple redis items execute in order
- **WHEN** a behavior has `redis: ['{{ redisDo "RPUSH" "log" HTTPBody }}', '{{ redisDo "SET" "last" HTTPBody }}']`
- **THEN** after handling a request both `log` and `last` are set in Redis, with `log` updated first

#### Scenario: redis items have access to request context
- **WHEN** a `redis` item template references `HTTPBody`
- **THEN** the request body value is used when the command is executed

#### Scenario: redis and reply_http can coexist in one behavior
- **WHEN** a behavior has both a `redis` action and a `reply_http` action
- **THEN** all Redis commands run and the HTTP response is sent
