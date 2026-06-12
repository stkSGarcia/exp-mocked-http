## 1. Definition Classification and Validation

- [x] 1.1 Add constants or helpers for supported kinds: `Behavior`, `Template`, and `AbstractBehavior`, with omitted kind defaulting to `Behavior`.
- [x] 1.2 Enforce allowed fields for each kind and reject unknown kinds, `Template` behavior fields, and `Behavior` template fields.
- [x] 1.3 Keep non-empty `key` validation common across all kinds and add tests for missing, empty, duplicate, and invalid-kind definitions.
- [x] 1.4 Register `Template` definitions by key during assembly and exclude them from the active behavior list.
- [x] 1.5 Exclude `AbstractBehavior` definitions from request matching while allowing their `expect`, `actions`, and `values` fields for inheritance.

## 2. Inheritance Resolution

- [x] 2.1 Refactor `assemble_behaviors` so raw definitions are indexed before concrete behaviors are resolved.
- [x] 2.2 Implement recursive `extend` resolution for parents of kind `Behavior` or `AbstractBehavior`, independent of definition order.
- [x] 2.3 Add cycle detection for inheritance chains and raise a validation error when a cycle is found.
- [x] 2.4 Implement merge rules for `values`, `actions`, recursively merged `expect`, and child-preferred non-zero fields.
- [x] 2.5 Skip missing parent references and validate the child using only its own fields.
- [x] 2.6 Validate final concrete behaviors after inheritance, including at most one combined `reply_http` action.

## 3. Template Rendering and Values

- [x] 3.1 Store the named template registry where the template renderer can access it during request handling and tests.
- [x] 3.2 Add a `template` render helper that renders a registered template by key with the supplied context and raises a render error for missing keys.
- [x] 3.3 Extend the template preprocessing or function rewrite path so `{{ template "key" . }}` and `{{ template "key" .Values }}` render correctly.
- [x] 3.4 Ensure matched behavior `.Values` are present while evaluating conditions and while executing response, Redis, sleep-adjacent, and outbound HTTP templates.
- [x] 3.5 Add tests for named templates with full request context, named templates with `.Values`, undefined variables, and values in conditions and bodies.

## 4. Action Ordering

- [x] 4.1 Preserve parent-before-child action order in the merged action list before sorting.
- [x] 4.2 Sort prepared actions by `order` ascending, default missing `order` to `0`, allow negative values, and rely on stable sorting for equal order values.
- [x] 4.3 Ensure inherited and child actions participate in the same ordering pass before execution.
- [x] 4.4 Add tests for negative order, default order, stable equal-order behavior, and ordered inherited actions.

## 5. End-to-End Scenarios and Verification

- [x] 5.1 Add an integration-style test for the checkpoint template-and-inheritance example where `purple-teapot` inherits `expect` and actions from `teapot`.
- [x] 5.2 Add a test proving `Template` and `AbstractBehavior` entries never match requests directly.
- [x] 5.3 Add a test for skipped missing parent extension that succeeds when the child is valid and fails when inherited required fields are still missing.
- [x] 5.4 Run `uv run pytest`.
- [x] 5.5 Run `openspec status --change "add-behavior-templates-inheritance-values-ordering"` and confirm the change is ready for implementation.
