## MODIFIED Requirements

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
