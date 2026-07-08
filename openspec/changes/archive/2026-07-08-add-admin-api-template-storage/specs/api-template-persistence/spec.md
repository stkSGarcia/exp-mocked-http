## ADDED Requirements

> Extends: mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering

### Requirement: API Template Persistence
The system SHALL persist base templates added through the admin API so they survive process restarts.

#### Scenario: API-added templates survive restart
- **GIVEN** valid base templates were added through `POST /api/v1/templates`
- **WHEN** the process restarts
- **THEN** the system SHALL load the persisted API-added templates on startup
- **AND** those templates SHALL be included in the active mock set

### Requirement: Active Template Merge
The system SHALL merge persisted API-added base templates with filesystem mocks into one active mock set using the existing duplicate-key rule.

#### Scenario: Last loaded duplicate key wins
- **GIVEN** a filesystem mock and an API-persisted mock use the same template key
- **WHEN** the active mock set is loaded
- **THEN** the last loaded definition SHALL win for request matching
- **AND** the losing definition SHALL NOT be deleted from its source

### Requirement: API Template Delete Persistence
The system SHALL persist deletions of API-added base templates independently from filesystem mocks.

#### Scenario: Deleted API template remains deleted after restart
- **GIVEN** an API-persisted base template was deleted through the admin API
- **WHEN** the process restarts
- **THEN** the deleted API-added template SHALL NOT be loaded from persistent storage
- **AND** filesystem mocks with the same key SHALL still load normally

### Requirement: Base Template Reload Visibility
The system SHALL make changes from mutating base-template admin requests visible to later requests within a bounded eventual-reload window.

#### Scenario: Upsert becomes visible
- **GIVEN** a client successfully adds or updates base templates through `POST /api/v1/templates`
- **WHEN** a later request is served after the reload window
- **THEN** request matching SHALL use the updated active mock set

#### Scenario: Delete becomes visible
- **GIVEN** a client successfully deletes API-added base templates through the admin API
- **WHEN** a later request is served after the reload window
- **THEN** request matching SHALL use the active mock set without the deleted API-added templates

