## 1. Definition Model And Validation

- [x] 1.1 Extend the behavior data model to carry effective `values` and any template registry reference needed during rendering.
- [x] 1.2 Add kind validation for `Behavior`, `Template`, and `AbstractBehavior`, including defaulting missing `kind` to `Behavior`.
- [x] 1.3 Enforce kind-specific allowed fields and reject invalid fields such as `template` on `Behavior`, behavior fields on `Template`, and `extend` on `AbstractBehavior`.
- [x] 1.4 Validate `values` as an arbitrary mapping for `Behavior` and `AbstractBehavior`, and reject non-map values.
- [x] 1.5 Update action validation to allow optional `order` metadata while still requiring exactly one concrete supported action per action entry.

## 2. Loading, Templates, And Inheritance

- [x] 2.1 Update mock loading to collect raw definitions by key across all discovered YAML files while preserving duplicate-key replacement warnings and final effective order.
- [x] 2.2 Register `Template` definitions by key and exclude them from the returned behavior list.
- [x] 2.3 Resolve `Behavior.extend` after all definitions are loaded, allowing parents to be defined before or after children.
- [x] 2.4 Merge inherited definitions using checkpoint rules for `values`, `actions`, recursive `expect`, and child-preferred scalar fields.
- [x] 2.5 Skip missing parent extensions, then validate the child-only definition so required concrete fields still fail when absent.
- [x] 2.6 Detect extension cycles and raise `ValidationError`.
- [x] 2.7 Exclude `AbstractBehavior` definitions from request matching while keeping them available as inheritance parents.

## 3. Rendering And Action Ordering

- [x] 3.1 Add `.Values` to every template context used by conditions, response bodies, response headers, Redis action items, outbound HTTP fields, and file-backed bodies.
- [x] 3.2 Implement named template invocation with `{{ template "key" . }}` and support passing `.Values` or any other resolved context as the nested root context.
- [x] 3.3 Return a template render error when a named template is missing.
- [x] 3.4 Normalize action `order` values to integers with a default of `0`, accepting negative values.
- [x] 3.5 Sort inherited and child actions together by ascending `order` while preserving original relative order for equal values.

## 4. Tests And Verification

- [x] 4.1 Add loader validation tests for valid and invalid kinds, allowed fields, required keys, template-only fields, abstract behavior fields, and `values` map validation.
- [x] 4.2 Add inheritance tests covering order-independent parent resolution, missing-parent fallback, recursive `expect` merge, child value override, inherited actions, and cycle rejection.
- [x] 4.3 Add rendering tests for `.Values` in conditions, responses, headers, Redis actions, outbound HTTP actions, and named template calls with root and values contexts.
- [x] 4.4 Add action ordering tests for default order, negative order, stable equal-order ties, and inherited action sorting.
- [x] 4.5 Run the full test suite with `uv run pytest`.
