## MODIFIED Requirements

> Extends: mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering

### Requirement: Active Mock Definition Loading
The system SHALL load filesystem mock definitions and persisted API-added mock definitions into one active mock set.

#### Scenario: Filesystem and API-persisted mocks are active
- **GIVEN** filesystem mock definitions exist
- **AND** persisted API-added mock definitions exist
- **WHEN** the system loads active mock definitions
- **THEN** the active mock set SHALL include mocks from both sources

#### Scenario: Duplicate keys use existing ordering
- **GIVEN** multiple loaded definitions share a template key
- **WHEN** the system builds the active mock set
- **THEN** the last loaded definition SHALL win according to the existing duplicate-key rule

### Requirement: Active Mock Definition Validation (adapts mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering/behavior-schema-validation)
The system SHALL validate filesystem and API-persisted mock definitions before serving requests.

#### Scenario: Invalid persisted mock does not become active
- **GIVEN** persistent storage contains an invalid API-added mock definition
- **WHEN** the system loads active mock definitions
- **THEN** the invalid definition SHALL NOT be served as an active mock
- **AND** the system SHALL surface a validation error through the loader or admin mutation path

