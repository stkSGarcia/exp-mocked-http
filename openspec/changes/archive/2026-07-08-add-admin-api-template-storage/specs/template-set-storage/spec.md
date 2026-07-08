## ADDED Requirements

> Extends: mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering

### Requirement: Template Set Replacement (adapts mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering/behavior-schema-validation)
The admin server SHALL expose `POST /api/v1/template_sets/{setKey}` to create or replace the full named template set for `setKey` after validating the submitted mock definitions.

#### Scenario: Valid template set is stored
- **GIVEN** the request body contains valid mock definitions
- **WHEN** a client requests `POST /api/v1/template_sets/{setKey}`
- **THEN** the admin server SHALL persist the submitted mocks as the full set for `setKey`
- **AND** it SHALL return `200 OK` with the submitted mocks in the response body

#### Scenario: Template set replacement is complete
- **GIVEN** a template set already exists for `setKey`
- **WHEN** a client successfully posts a different set to `POST /api/v1/template_sets/{setKey}`
- **THEN** the stored set for `setKey` SHALL be replaced by exactly the submitted mocks

### Requirement: Template Set Isolation
The system SHALL persist named template sets separately from the base template collection and from each other.

#### Scenario: Set storage is isolated
- **GIVEN** template sets exist for `alpha` and `beta`
- **WHEN** the system loads template-set storage
- **THEN** mocks from `alpha` SHALL remain associated with `alpha`
- **AND** mocks from `beta` SHALL remain associated with `beta`
- **AND** neither set SHALL overwrite the base API-added template collection

### Requirement: Template Set Deletion
The admin server SHALL expose `DELETE /api/v1/template_sets/{setKey}` to delete the entire named template set for `setKey`.

#### Scenario: Delete one template set
- **GIVEN** template sets exist for `alpha` and `beta`
- **WHEN** a client requests `DELETE /api/v1/template_sets/alpha`
- **THEN** the admin server SHALL delete the entire `alpha` set
- **AND** it SHALL leave the `beta` set and base templates untouched
- **AND** it SHALL return `204 No Content`

### Requirement: Template Set Reload Visibility
The system SHALL make changes from mutating template-set admin requests visible to later requests within a bounded eventual-reload window.

#### Scenario: Template set mutation becomes visible
- **GIVEN** a client successfully creates, replaces, or deletes a template set through the admin API
- **WHEN** a later request is served after the reload window
- **THEN** request matching SHALL use the active mock set that reflects the template-set mutation

