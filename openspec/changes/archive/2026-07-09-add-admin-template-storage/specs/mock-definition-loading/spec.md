## ADDED Requirements

> Extends: mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering

### Requirement: Persistent API Template Loading
The system SHALL persist API-added base mocks and load them on startup.

#### Scenario: Persisted base templates survive restart
- **GIVEN** valid API-added base mocks were persisted before shutdown
- **WHEN** the system starts
- **THEN** the system SHALL load the persisted base mocks before serving requests

### Requirement: Persistent Template Set Loading
The system SHALL persist named template sets separately from the base template collection and load them on startup.

#### Scenario: Persisted template sets survive restart
- **GIVEN** valid named template sets were persisted before shutdown
- **WHEN** the system starts
- **THEN** the system SHALL load each persisted template set under its own set key
- **AND** loading one set SHALL NOT remove or overwrite any other set

### Requirement: Active Mock Merge
The system SHALL merge filesystem mocks, persisted API-added base mocks, and persisted template-set mocks into the active mock set using the existing duplicate-key rule.

#### Scenario: Last loaded mock wins
- **GIVEN** more than one loaded mock definition uses the same key
- **WHEN** the system builds the active mock set
- **THEN** the last loaded definition for that key SHALL be the active definition

### Requirement: Persisted Definition Validation
The system SHALL validate persisted mock definitions before serving requests. (adapts mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering/behavior-schema-validation)

#### Scenario: Invalid persisted definition is not served
- **GIVEN** persistent storage contains an invalid mock definition
- **WHEN** the system loads persisted definitions
- **THEN** the system SHALL treat the definition as invalid and SHALL NOT serve it as an active mock
