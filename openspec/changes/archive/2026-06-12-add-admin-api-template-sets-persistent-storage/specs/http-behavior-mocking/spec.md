## ADDED Requirements

### Requirement: Active Mock Reload Visibility
The system SHALL serve mock requests from the latest active mock set after admin mutations are reloaded.

#### Scenario: Added template becomes matchable
- **WHEN** an admin mutation adds a mock definition and the bounded reload window has elapsed
- **THEN** a later matching mock request SHALL be evaluated against that added definition

#### Scenario: Updated template replaces previous active behavior
- **WHEN** an admin mutation updates a mock definition with a key that already exists and the bounded reload window has elapsed
- **THEN** a later matching mock request SHALL use the latest active definition selected by the duplicate-key merge rule

#### Scenario: Deleted base template stops matching
- **WHEN** an admin mutation deletes a base API-added mock and no filesystem mock or template-set mock with the same key remains active after the bounded reload window
- **THEN** a later request that only matched the deleted mock SHALL return the unmatched HTTP response

#### Scenario: Filesystem template remains after API delete
- **WHEN** an admin mutation deletes a base API-added mock with the same key as a filesystem mock and the bounded reload window has elapsed
- **THEN** a later matching mock request SHALL still be able to select the filesystem mock
