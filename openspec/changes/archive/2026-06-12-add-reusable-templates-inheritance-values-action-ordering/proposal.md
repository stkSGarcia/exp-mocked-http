## Why

Mock definitions need a way to share reusable fragments and base behavior without duplicating full mocks across files. Adding templates, inherited behavior, explicit values, and deterministic action ordering makes complex mock suites easier to maintain while keeping request matching predictable.

## What Changes

- Add `Template` and `AbstractBehavior` as valid `kind` values alongside concrete `Behavior`.
- Allow reusable named templates to be registered from YAML definitions and invoked with Go template `{{ template "key" . }}` syntax.
- Add `extend` so a `Behavior` can inherit from an `AbstractBehavior` or another `Behavior`, with recursive `expect` merging, value merging, and inherited actions.
- Add arbitrary `values` maps to behaviors and expose merged values as `.Values` in every template render context.
- Add optional per-action `order` fields, sort selected behavior actions by ascending order before execution, and preserve stable ordering for ties.
- Tighten kind-specific validation, including allowed fields, required keys, invalid kinds, and the existing single-`reply_http` rule after inheritance.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mock-definition-loading`: Expand mock definition schema validation, template registration, abstract behavior handling, inheritance resolution, values merging, and effective behavior loading.
- `template-rendering`: Expose `.Values` in template contexts and support named reusable templates with caller-provided context.
- `http-behavior-mocking`: Execute inherited and locally defined actions using explicit stable action ordering.

## Impact

- Affects YAML mock definition parsing, validation, and effective behavior construction in `hmock.py`.
- Affects request template context creation for conditions, response bodies, response headers, Redis actions, and outbound HTTP actions.
- Affects action execution ordering for all behavior action types.
- Requires focused tests for schema validation, template registration/rendering, inheritance merge behavior, and ordered action execution.
