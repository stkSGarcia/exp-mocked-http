# persistent-storage

## Purpose

TBD

## Requirements

### Requirement: Persist API-added mocks in Redis
The server SHALL persist all base API-added mocks (from `POST /api/v1/templates`) under a reserved Redis key (`__hmock_internal:templates`) as a JSON-serialized list. On startup, the server SHALL load this key and merge its contents with filesystem mocks. The last-loaded-wins duplicate-key rule applies: filesystem mocks load first, then API-persisted mocks.

#### Scenario: API mocks survive restart
- **WHEN** mocks are added via `POST /api/v1/templates` and the server restarts with `HM_REDIS_TYPE=redis`
- **THEN** the added mocks are active after restart without re-posting

#### Scenario: In-memory backend loses API mocks on restart
- **WHEN** `HM_REDIS_TYPE=memory` and mocks are added via the admin API, then the server restarts
- **THEN** the added mocks are no longer present

#### Scenario: API mocks merged after filesystem mocks
- **WHEN** a filesystem mock and an API mock share the same key
- **THEN** the API mock is active (it was loaded last and wins)

### Requirement: Persist template sets in Redis
The server SHALL persist each template set under a dedicated Redis key (`__hmock_internal:tset:<setKey>`). On startup, the server SHALL load all `__hmock_internal:tset:*` keys and merge each set's mocks into the active set, in set-key sorted order, after the base API mocks.

#### Scenario: Template set survives restart
- **WHEN** a template set is created via `POST /api/v1/template_sets/myset` and the server restarts with `HM_REDIS_TYPE=redis`
- **THEN** the set's mocks are active after restart

#### Scenario: Multiple sets loaded in key-sorted order
- **WHEN** sets `aaa` and `zzz` are both persisted
- **THEN** `aaa`'s mocks load before `zzz`'s mocks; if they share a key, `zzz`'s version wins

#### Scenario: Deleting a set removes only that set's key
- **WHEN** `DELETE /api/v1/template_sets/myset` is called
- **THEN** only `__hmock_internal:tset:myset` is deleted; other `__hmock_internal:tset:*` keys are unaffected

### Requirement: Reload after mutating admin requests
After any mutating admin operation (POST or DELETE on templates or template sets), the server SHALL rebuild the active mock set and make the change visible to the primary mock server within a bounded reload window (≤ 1 second).

#### Scenario: New mock visible after POST within reload window
- **WHEN** a mock is added via `POST /api/v1/templates`
- **THEN** within 1 second the primary server matches requests against the new mock

#### Scenario: Deleted mock invisible after DELETE within reload window
- **WHEN** a mock is deleted via `DELETE /api/v1/templates/{templateKey}`
- **THEN** within 1 second the primary server no longer matches requests against that mock
