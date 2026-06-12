## Why

Mock definitions now need reuse and specialization without duplicating whole behaviors. Checkpoint 4 adds reusable template fragments, behavior inheritance, per-behavior values, and explicit action ordering so complex mocks can stay declarative and predictable.

## What Changes

- Add three accepted behavior kinds: `Behavior`, `Template`, and `AbstractBehavior`; reject any other `kind`.
- Add `Template` entries that register reusable template fragments by `key` and can be invoked with Go-template `{{ template "key" . }}` syntax.
- Add `AbstractBehavior` entries that may define expectations, actions, and values but never match requests directly.
- Add `extend` support so a concrete `Behavior` can inherit from another `Behavior` or an `AbstractBehavior`, with parent references resolved regardless of definition order.
- Add arbitrary `values` maps for `Behavior` and `AbstractBehavior`, expose merged values as `.Values`, and use child values to override parent values.
- Define inheritance merge rules for values, actions, expectations, and other fields.
- Add optional action `order`, sort inherited and local actions before execution, and preserve input order for equal order values.
- Tighten validation for allowed fields per kind, required non-empty keys, template restrictions, and at most one `reply_http` per final concrete behavior.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `http-yaml-mock-server`: Extend mock loading, validation, matching, template rendering, and action execution semantics for reusable templates, inheritance, values, and explicit action ordering.

## Impact

- Affects `hmock.py` YAML parsing and validation, template registration, behavior resolution, active behavior selection, request context creation, and action execution order.
- Adds test coverage for kind validation, template-only entries, abstract behavior non-matching, extension merge rules, skipped missing parents, `.Values` rendering in bodies and conditions, action ordering stability, and final `reply_http` cardinality validation.
