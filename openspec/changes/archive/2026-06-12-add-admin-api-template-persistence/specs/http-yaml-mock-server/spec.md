## ADDED Requirements

> Extends: http-yaml-mock-server/add-http-yaml-mock-server

### Requirement: Persisted definition startup loading
The system SHALL load persisted base API definitions and all persisted named template sets during startup and combine them with filesystem definitions before serving mock requests.

#### Scenario: Persisted definitions survive restart
- **GIVEN** valid base API definitions and named template sets were persisted before shutdown
- **WHEN** the process starts again using the same Redis store
- **THEN** those definitions are included in the active mock set without another admin request

#### Scenario: No persisted definitions exist
- **GIVEN** the internal persistence records do not exist
- **WHEN** the process starts
- **THEN** filesystem definitions load normally
- **AND** the absence of persisted definitions does not prevent startup

### Requirement: Definition source merge precedence
The system SHALL merge definition sources in deterministic load order and apply the existing last-loaded-wins duplicate-key rule across filesystem definitions, base API definitions, and named template sets.

#### Scenario: Later source overrides duplicate key
- **GIVEN** two loaded sources define the same key
- **WHEN** the active definitions are assembled
- **THEN** only the definition from the source loaded later in the deterministic order is active
- **AND** the duplicate override is logged consistently with filesystem duplicate handling

#### Scenario: Unique keys from every source remain active
- **GIVEN** filesystem, base API, and named-set sources contain distinct keys
- **WHEN** the active definitions are assembled
- **THEN** definitions from every source are available to request matching and template resolution

### Requirement: Shared validation and rendering semantics
The system SHALL apply the existing definition validation, behavior inheritance, named-template registration, action ordering, and request-time rendering semantics to API-persisted definitions.

#### Scenario: Persisted definition uses existing composition
- **GIVEN** persisted definitions contain valid templates, abstract behaviors, and extending behaviors
- **WHEN** the active definitions are assembled
- **THEN** they resolve and execute using the same composition rules as filesystem definitions

#### Scenario: Persisted file-backed body is constrained
- **GIVEN** an API-persisted definition references `body_from_file`
- **WHEN** the definition is assembled
- **THEN** the existing templates-directory path and file validation rules apply

> Extends: http-yaml-mock-server/add-template-helpers-file-backed-bodies

### Requirement: Reserved Redis keyspace protection
The `redisDo` template function SHALL reject any Redis command that targets a key or key pattern beginning with `__hmock_internal:`. The rejection SHALL occur before the Redis backend executes the command and SHALL surface as a template render error.

#### Scenario: Block direct internal key access
- **GIVEN** a template calls `redisDo` with a command targeting `__hmock_internal:templates`
- **WHEN** the template is rendered
- **THEN** rendering fails with a template render error
- **AND** the Redis backend does not execute the command

#### Scenario: Block template-set internal key access
- **GIVEN** a template calls `redisDo` with a command targeting an internal template-set storage key
- **WHEN** the template is rendered
- **THEN** rendering fails with a template render error
- **AND** the persisted set remains unchanged

#### Scenario: Block an internal key pattern
- **GIVEN** a template calls `redisDo` with a key-pattern command targeting `__hmock_internal:*`
- **WHEN** the template is rendered
- **THEN** rendering fails with a template render error
- **AND** the Redis backend does not execute the command

#### Scenario: Allow non-reserved Redis access
- **GIVEN** a template calls `redisDo` with a supported command whose keys do not begin with `__hmock_internal:`
- **WHEN** the template is rendered
- **THEN** the command executes with the existing Redis behavior
