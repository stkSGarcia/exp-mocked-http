## ADDED Requirements

### Requirement: Persistent Admin Mock Loading
The system SHALL persist API-added mock definitions across process restarts and load them into the active mock definition stream.

#### Scenario: Persisted base API mocks load on startup
- **WHEN** the server starts and the persistent store contains base API-added mocks
- **THEN** the system SHALL load those mocks and include them in the active mock set

#### Scenario: Persisted template sets load on startup
- **WHEN** the server starts and the persistent store contains one or more template sets
- **THEN** the system SHALL load every persisted template set and include its mock definitions in the active mock set

#### Scenario: Persisted mocks merge with filesystem mocks
- **WHEN** filesystem mocks and persisted mocks are both available
- **THEN** the system SHALL merge them into one active mock set

#### Scenario: Duplicate keys use last loaded definition
- **WHEN** multiple filesystem or persisted mock definitions use the same `key`
- **THEN** the system SHALL keep the last loaded definition for that key and remove earlier definitions from the effective list

### Requirement: Persisted Mock Load Order
The system SHALL load persisted admin-managed mocks in a deterministic order after filesystem mocks.

#### Scenario: Base API mocks load after filesystem mocks
- **WHEN** a filesystem mock and a base API-added mock use the same `key`
- **THEN** the base API-added mock SHALL be the last loaded definition for that key

#### Scenario: Template sets load after base API mocks
- **WHEN** a base API-added mock and a template-set mock use the same `key`
- **THEN** the template-set mock SHALL be the last loaded definition for that key when its set is loaded after the base API mock collection

#### Scenario: Template sets load by set key
- **WHEN** multiple template sets are persisted
- **THEN** the system SHALL load template sets in lexicographic order by set key while preserving definition order within each set

### Requirement: Template Set Isolation
The system SHALL keep persisted template sets isolated by set key.

#### Scenario: Replacing one set preserves other sets
- **WHEN** a template set is created or replaced for one `{setKey}`
- **THEN** the system SHALL leave every other persisted template set unchanged

#### Scenario: Deleting one set preserves other sets
- **WHEN** a template set is deleted for one `{setKey}`
- **THEN** the system SHALL leave every other persisted template set unchanged

#### Scenario: Clearing base API mocks preserves template sets
- **WHEN** all base API-added mocks are deleted
- **THEN** the system SHALL leave every persisted template set unchanged
