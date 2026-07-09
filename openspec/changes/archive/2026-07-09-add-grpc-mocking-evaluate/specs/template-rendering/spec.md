## ADDED Requirements

> Extends: template-rendering/add-http-yaml-mock-server
> Extends: template-rendering/add-reusable-templates-inheritance-values-action-ordering

### Requirement: gRPC Template Variables
The system SHALL include gRPC-specific variables in the template context while rendering gRPC conditions, replies, and reply metadata.

#### Scenario: gRPC metadata can be read by templates
- **GIVEN** a gRPC request contains metadata header `x-request-id`
- **WHEN** a gRPC behavior renders a condition or reply template
- **THEN** `.GRPCHeader.Get "x-request-id"` returns the metadata value

### Requirement: Evaluation Template Context
The system SHALL build template context for `/api/v1/evaluate` from the merged simulated channel contexts and render conditions and supported dry-run actions using that context.

#### Scenario: Evaluation renders from simulated HTTP body
- **GIVEN** an evaluation request includes `context.http_context.body`
- **AND** a selected `reply_http` action references the HTTP body
- **WHEN** the mock is evaluated
- **THEN** the dry-run result contains the rendered body derived from the simulated context

#### Scenario: Evaluation renders ordered actions
- **GIVEN** an evaluation request includes multiple supported actions with `order` values
- **WHEN** matching and condition evaluation pass
- **THEN** the actions are rendered in ascending `order` before response results are returned
