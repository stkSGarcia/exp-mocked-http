## Context

The server is currently a single Python entry point, `hmock.py`, that loads YAML objects, validates each object as a concrete behavior, prepares file-backed bodies, matches requests against active behaviors, renders templates through the compatibility layer, and executes actions in list order. Checkpoint 4 changes the mock definition model: YAML entries may now be reusable named templates, abstract base behaviors, or concrete behaviors, and concrete behaviors may inherit fields from earlier or later definitions.

The important constraints are that inheritance must be resolved independently of definition order, `Template` and `AbstractBehavior` entries must never match requests directly, named templates must be callable from every template-rendering context, and action ordering must remain deterministic after inherited and child actions are combined.

## Goals / Non-Goals

**Goals:**

- Accept only `Behavior`, `Template`, and `AbstractBehavior` as behavior definition kinds, with omitted kind still defaulting to `Behavior`.
- Register `Template` entries under their `key` and make them available through `{{ template "key" . }}` with any rendering context, including `.Values`.
- Support `AbstractBehavior` definitions as reusable bases that can carry `expect`, `actions`, and `values` but are excluded from request matching.
- Resolve `extend` references from concrete behaviors to either `Behavior` or `AbstractBehavior` parents, regardless of YAML definition order.
- Merge values, actions, expectations, and other fields using the checkpoint merge rules, then validate the final concrete behavior.
- Expose merged `.Values` in conditions, response bodies, response headers, Redis action templates, outbound HTTP templates, and named templates.
- Sort final actions by `order` before execution while preserving original relative order for actions with the same order.

**Non-Goals:**

- Supporting multi-parent inheritance or inheritance from `Template` entries.
- Detecting missing parents as a fatal error when the child remains valid on its own.
- Adding new action types beyond the existing `sleep`, `redis`, `send_http`, and `reply_http` actions.
- Replacing the existing template compatibility layer with a separate template engine.

## Decisions

- Split YAML loading into definition collection, named-template registration, inheritance resolution, and final behavior validation.

  The current `assemble_behaviors` validates every object immediately. The new flow should first classify entries by kind, enforce allowed fields for each kind, register templates by key, and index behavior-like definitions by key. A second pass can resolve each concrete `Behavior`, merge inherited data, prepare actions, and append only final concrete behaviors to the active list.

- Resolve inheritance recursively with cycle detection.

  Parents can appear after children, so resolution cannot depend on list order. A recursive resolver keyed by definition `key` can produce a merged behavior for each `Behavior`. Track the active resolution stack and fail validation on cycles, because cycles cannot produce deterministic merged fields.

- Treat missing parents as a skipped extension.

  If `extend` names a missing key, load and validate the child using only its own fields. This matches checkpoint reference rules while still allowing normal validation to fail if the child lacks required fields after the skipped extension.

- Use deep map merge only where the checkpoint calls for it.

  `values` should merge as maps with child keys overriding parent keys. `expect` should merge recursively so child nested fields override matching parent nested fields while missing child fields inherit. `actions` should concatenate parent actions before child actions. Other fields should use the child's non-zero value when present and otherwise keep the parent value.

- Sort actions after inheritance and preparation, not during raw YAML parsing.

  Sorting after merge ensures inherited actions and local actions participate in the same ordering pass. Python's stable sort can preserve original relative order for equal `order` values. Action execution can then continue to iterate the prepared list without knowing whether actions were inherited.

- Implement named templates as a template function backed by the loaded template registry.

  Register a `template` global/filter in the existing compatibility environment that looks up the named template string and renders it with the provided context object. The function should preserve the active template registry and Redis backend so named templates behave the same as inline templates. Missing named templates should raise a render error.

- Keep `.Values` on the per-request render context.

  Request matching already copies context before evaluating conditions. Add each resolved behavior's merged values to that context for conditions, then set the same values on the execution context before running actions. Passing `.Values` into named templates should simply pass the map as the template context.

## Risks / Trade-offs

- Recursive inheritance can accidentally permit cycles if not guarded. Mitigation: track currently resolving keys and raise a clear validation error for cyclic `extend` chains.
- Named templates rendered with arbitrary contexts make context shape more dynamic. Mitigation: route named template rendering through the same strict renderer so undefined variables remain errors.
- Missing-parent skip behavior can hide typos when a child is independently valid. Mitigation: keep this behavior because it is required, but add tests proving missing parents are skipped only until normal validation catches remaining required-field gaps.
- Sorting by `order` changes the current list-order behavior for existing mocks that add `order`. Mitigation: default `order` to `0` and use stable sorting so existing mocks without `order` retain their current relative order.
