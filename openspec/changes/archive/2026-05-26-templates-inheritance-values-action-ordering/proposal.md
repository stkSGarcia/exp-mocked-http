## Why

The mock server currently supports only flat, concrete behaviors with no code reuse between them. As mock suites grow, teams repeat the same response shapes, conditions, and action sequences across many behaviors — making maintenance brittle and verbose.

## What Changes

- Introduce a `Template` kind: named Go template fragments registered by key and callable via `{{template "key" .}}` inside any template expression.
- Introduce an `AbstractBehavior` kind: a behavior that defines `expect`, `actions`, and `values` but never matches requests directly — only usable as a parent for inheritance.
- Add `extend` field to `Behavior`: merges the parent's `expect`, `actions`, and `values` into the child using defined merge rules.
- Add `values` map field to `Behavior` and `AbstractBehavior`: arbitrary key-value data exposed as `.Values.<key>` in all template expressions, including conditions.
- Add `order` field to actions: actions are sorted ascending by `order` before execution; default is `0`; negative values are allowed; stable sort preserves relative order among ties.
- Extend validation: reject unknown `kind` values; enforce per-kind allowed fields (`Template` may only have `key`/`kind`/`template`; `AbstractBehavior` may not define `extend`); `key` required on all kinds.

## Capabilities

### New Capabilities

_(none — all changes extend the existing http-mock-server behavior loading and execution pipeline)_

### Modified Capabilities

- `http-mock-server`: Adds three recognized `kind` values, inheritance via `extend`, per-behavior `values` maps, reusable `Template` fragments, and action `order` sorting.

## Impact

- Behavior loading and validation logic must handle two new kinds and new fields.
- Template registration must happen before behaviors are evaluated so `{{template "key" .}}` calls resolve at render time.
- Merge logic for `extend` must be applied after all definitions are loaded (to support forward references).
- Template rendering context must be extended to expose `.Values`.
- Action execution must sort by `order` before running.
- No breaking changes to existing `Behavior` definitions (all new fields are optional; `kind` defaults remain `Behavior`).
