## Context

`hmock.py` currently parses YAML mock files into concrete `Behavior` objects during loading, then matches and executes those behaviors directly. Templates are rendered from request context only, and actions execute in the loaded action list order.

Checkpoint 4 adds reusable definition fragments that span loading, template rendering, and execution. The design should preserve the existing runtime shape as much as possible: request matching should continue to operate over concrete behaviors, while templates, abstract behaviors, inheritance, and action ordering are resolved before or during effective behavior construction.

## Goals / Non-Goals

**Goals:**

- Support three mock definition kinds: `Behavior`, `Template`, and `AbstractBehavior`.
- Register named reusable templates and allow `{{ template "key" . }}` calls from all current render locations.
- Resolve `extend` references regardless of definition order, merge inherited fields deterministically, and keep abstract behaviors out of request matching.
- Add `.Values` to every render context, using merged behavior values for selected behaviors.
- Sort actions by optional `order` before execution while preserving stable ordering for equal order values.
- Keep validation errors early and explicit during mock loading.

**Non-Goals:**

- Add a complete YAML parser beyond the subset already supported by this project.
- Add cyclic inheritance support; cycles should be validation failures.
- Add template namespaces, file-backed template definitions, or hot reloading.
- Change HTTP route matching semantics, Redis command support, or outbound HTTP behavior except where values/templates/action ordering affect existing rendering.

## Decisions

1. Preserve concrete `Behavior` as the runtime matching unit.

   Load-time processing should classify raw YAML definitions, register `Template` definitions, resolve inheritance, and then return only concrete `Behavior` instances from `load_behaviors`. `AbstractBehavior` entries remain available as inheritance parents but are never included in the returned behavior list.

   Alternative considered: return multiple runtime definition types and teach request matching to skip non-concrete entries. That spreads kind checks into hot-path matching and execution without adding value.

2. Keep raw definitions by key until inheritance resolution completes.

   Loading should collect the last definition for each key, preserving the existing duplicate-key replacement warning behavior. Extension parents can then be resolved by key after all YAML files are read, so parent definitions work regardless of file or document order.

   Alternative considered: resolve inheritance as each file is loaded. That would make forward references difficult and would contradict the checkpoint requirement that parents are order independent.

3. Merge inheritance into a normalized raw definition before validation.

   Parent and child maps should be combined using the checkpoint rules: merge `values`, concatenate parent actions before child actions, recursively merge `expect`, and prefer child non-zero values for other fields. The normalized concrete behavior is then passed through the existing action/body-file validation, with extensions for kind-specific fields and action `order`.

   Alternative considered: store parent links on `Behavior` and merge during execution. That would make validation less reliable because missing inherited fields and duplicate replies would not be known until requests arrive.

4. Carry behavior values and named templates in render context.

   `Behavior` should include a `values` map, and `build_template_context` should accept an optional values map that is exposed as `.Values`. Named templates should be stored in a registry available to `render_template`, with the `template` action rendering a registered source with the explicitly supplied context.

   Alternative considered: inject values into the root context as top-level keys. That risks collisions with existing request fields and makes templates less explicit.

5. Sort actions once during effective behavior construction.

   Each action should be normalized to carry its original sequence index and `order` value. The effective action list can be sorted stably by `(order, sequence)`, including inherited actions, before the behavior reaches execution. Existing actions without `order` default to `0`, so current behavior is preserved for unsorted mocks.

   Alternative considered: sort inside `execute_behavior` for every request. That is simpler but repeats deterministic work and leaves tests to inspect unsorted loaded actions.

## Risks / Trade-offs

- Inheritance cycles could otherwise recurse indefinitely -> Track the resolution stack and raise `ValidationError` when a key repeats.
- Missing parent references intentionally fall back to the child only -> Validate the child after skipped inheritance so incomplete children still fail.
- `order` adds metadata beside action names -> Accept action dictionaries with one supported action plus optional `order`, while still rejecting multiple concrete action payloads.
- Template names share the same key space as behaviors -> Keep a single definition key registry for duplicate replacement, but validate kind-specific fields after replacement so duplicate keys remain predictable.
- Named templates can be recursively invoked -> Reuse existing template render errors and add recursion tests if practical; cycle detection can be deferred unless unbounded recursion appears in implementation.

## Migration Plan

Existing mock files that omit `kind`, `values`, `extend`, `template`, and `order` continue to load as concrete behaviors with default action order `0`. Existing action order is preserved because stable sorting keeps equal-order actions in their original effective order. Invalid new fields or invalid kinds become load-time validation errors.

Rollback is to avoid the new fields in YAML definitions; no data migration is required.

## Open Questions

None.
