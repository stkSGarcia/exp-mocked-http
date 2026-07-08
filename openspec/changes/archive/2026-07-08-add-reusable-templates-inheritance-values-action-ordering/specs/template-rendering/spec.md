## ADDED Requirements

### Requirement: Named Template Rendering
The system SHALL support named reusable templates registered from mock definitions.

#### Scenario: Named template renders with root context
- **WHEN** a template expression invokes `{{ template "key" . }}` and a template named `key` is registered
- **THEN** the system SHALL render the registered template source with the current render context

#### Scenario: Named template renders with values context
- **WHEN** a template expression invokes `{{ template "key" .Values }}` and a template named `key` is registered
- **THEN** the system SHALL render the registered template source with the behavior values map as its context

#### Scenario: Named template accepts arbitrary context
- **WHEN** a template expression invokes a registered named template with any resolved context value
- **THEN** the system SHALL render the registered template source using that value as the root context for the nested render

#### Scenario: Missing named template fails rendering
- **WHEN** a template expression invokes `{{ template "missing" . }}` and no template named `missing` is registered
- **THEN** the system SHALL treat rendering as an error

## MODIFIED Requirements

### Requirement: Template Context
The system SHALL render conditions, response bodies, response headers, Redis action items, and outbound HTTP action fields using the same request and behavior template context.

#### Scenario: Header context is available
- **WHEN** a template uses `.HTTPHeader.Get "Header-Name"`
- **THEN** the system SHALL provide the matching request header value

#### Scenario: Body context is available
- **WHEN** a template uses `.HTTPBody`
- **THEN** the system SHALL provide the raw request body as a string

#### Scenario: Path context is available
- **WHEN** a template uses `.HTTPPath`
- **THEN** the system SHALL provide the full request URL path including the query string when present

#### Scenario: Query string context is available
- **WHEN** a template uses `.HTTPQueryString`
- **THEN** the system SHALL provide the raw query string without the leading `?`

#### Scenario: Values context is available
- **WHEN** a selected behavior has effective `values`
- **THEN** every template render for that behavior SHALL expose those values as `.Values`

#### Scenario: Merged inherited values are available
- **WHEN** a selected behavior extends a parent with `values`
- **THEN** every template render for that behavior SHALL expose the merged parent and child values as `.Values`
