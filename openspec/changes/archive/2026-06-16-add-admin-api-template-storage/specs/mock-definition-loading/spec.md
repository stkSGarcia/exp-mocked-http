## ADDED Requirements

> Extends: mock-definition-loading

### Requirement: Persistent API-Managed Definition Sources
The system SHALL load persisted API-managed mock definitions alongside filesystem mock definitions.

#### Scenario: Persisted base mocks load on startup
- **WHEN** the process starts and base API-managed mocks exist in persistent storage
- **THEN** the mock loader SHALL include those mocks in the active definition stream with filesystem-loaded mocks

#### Scenario: Persisted template sets load on startup
- **WHEN** the process starts and named template sets exist in persistent storage
- **THEN** the mock loader SHALL include each persisted set in the active definition stream while preserving set identity for later replacement or deletion

#### Scenario: Filesystem and persisted mocks merge
- **WHEN** filesystem mocks, base API-managed mocks, and template-set mocks are loaded
- **THEN** the mock loader SHALL merge them into one active set before request matching

#### Scenario: Duplicate key replacement still applies
- **WHEN** merged filesystem and API-managed definitions contain duplicate keys
- **THEN** the mock loader SHALL apply the existing duplicate-key rule where the last loaded definition wins

### Requirement: Template Set Isolation
The system SHALL keep each persisted template set isolated by set key.

#### Scenario: Deleting one set preserves others
- **WHEN** a persisted template set is deleted
- **THEN** the system SHALL leave all other persisted template sets and base API-managed mocks unchanged

#### Scenario: Replacing one set preserves others
- **WHEN** a persisted template set is replaced
- **THEN** the system SHALL replace only the mocks for that set key and SHALL leave other persisted template sets unchanged
