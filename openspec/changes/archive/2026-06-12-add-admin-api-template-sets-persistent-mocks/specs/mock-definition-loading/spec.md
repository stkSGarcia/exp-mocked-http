## ADDED Requirements

### Requirement: Persisted API Mock Loading
The system SHALL load persisted API-added mock definitions at startup and merge them with filesystem-loaded mock definitions into one active set.

#### Scenario: Persisted base mocks load on startup
- **WHEN** the server starts and base API-added mocks are present in persistent storage
- **THEN** the system SHALL load those mocks into the active mock set

#### Scenario: Persisted template sets load on startup
- **WHEN** the server starts and one or more template sets are present in persistent storage
- **THEN** the system SHALL load every persisted template set into the active mock set

#### Scenario: Filesystem and persisted mocks merge
- **WHEN** filesystem-loaded mocks, base API-added mocks, and template-set mocks are all present
- **THEN** the system SHALL merge them into one active mock definition stream

#### Scenario: Duplicate persisted key uses last loaded definition
- **WHEN** multiple loaded definitions from filesystem storage, base API storage, or template sets use the same `key`
- **THEN** the system SHALL keep the last loaded definition for that key and remove the earlier definition from the effective list

### Requirement: API Mock Persistence
The system SHALL persist mock definitions created or updated through the admin API so they can be loaded by later server instances using the same persistent backend.

#### Scenario: Base API mocks survive restart
- **WHEN** valid base API-added mocks have been persisted and the server is restarted with the same persistent backend
- **THEN** the restarted server SHALL load those mocks into the active mock set

#### Scenario: Template sets survive restart
- **WHEN** a valid template set has been persisted and the server is restarted with the same persistent backend
- **THEN** the restarted server SHALL load that template set into the active mock set

### Requirement: Template Set Isolation
The system SHALL store and load each named template set independently.

#### Scenario: Replacing one set does not affect another
- **WHEN** a client replaces template set `a`
- **THEN** the system SHALL leave persisted template set `b` unchanged

#### Scenario: Deleting one set does not affect another
- **WHEN** a client deletes template set `a`
- **THEN** the system SHALL leave persisted template set `b` unchanged

#### Scenario: Deleting base templates does not affect sets
- **WHEN** a client deletes all base API-added mocks
- **THEN** the system SHALL leave every persisted template set unchanged

### Requirement: Admin Mutation Reload Visibility
The system SHALL make successful admin mutations visible to subsequent mock requests within a bounded eventual-reload window.

#### Scenario: Upsert becomes visible after success
- **WHEN** an admin upsert request returns success
- **THEN** later mock requests SHALL observe the updated active mock set within the reload window

#### Scenario: Delete becomes visible after success
- **WHEN** an admin delete request returns success
- **THEN** later mock requests SHALL observe the deleted mock or set within the reload window

#### Scenario: Failed mutation keeps previous active set
- **WHEN** an admin mutation fails validation
- **THEN** the system SHALL keep serving the previously active mock set
