## 1. Validation — extend per-kind allowed fields

- [x] 1.1 In `_validate_behavior`, add a check that rejects any `kind` value not in `{"Behavior", "AbstractBehavior", "Template"}` (after applying the default)
- [x] 1.2 Define allowed-field sets per kind and reject extra fields: `Template` → `{key, kind, template}`; `AbstractBehavior` → `{key, kind, expect, actions, values}`; `Behavior` → `{key, kind, extend, expect, actions, values}`
- [x] 1.3 Validate that `Template` includes a non-empty `template` field; validate that `Behavior` does not set `template`
- [x] 1.4 Move the `reply_http` count check to apply only to `Behavior` and `AbstractBehavior` (skip for `Template`)
- [x] 1.5 Add tests covering rejection of unknown kind, disallowed fields per kind, and Template missing `template`

## 2. Template kind — registration and rendering

- [x] 2.1 Add module-level `_TEMPLATES: dict[str, str]` to store registered template fragments
- [x] 2.2 Add a thread-local `_render_tl = threading.local()` to hold the current render context
- [x] 2.3 In `render()`, store the context in `_render_tl.context` before calling `tmpl.render(**context)`
- [x] 2.4 Implement `_render_tmpl(key, ctx)` function: looks up `_TEMPLATES[key]`, preprocesses the template string, renders with `ctx` if it is a dict, or with `_render_tl.context` if `ctx` is `None`; returns the rendered string (raises on error so the parent render fails)
- [x] 2.5 Register `_render_tmpl` as a global in `_JINJA` (in `_make_jinja_env`)
- [x] 2.6 Expand `_CTX_VAR_RE` from `r"(?<![.\w])\.(HTTP\w+)"` to `r"(?<![.\w])\.(\w+)"` so `.Values`, `.color`, and other sub-context vars get their leading dots stripped
- [x] 2.7 In `_preprocess`'s `transform` function, detect inner text matching `template "<key>" <expr>` and convert it to `_render_tmpl("<key>", <processed-expr>)`: map `.` → `None`; strip leading dots from other exprs (e.g., `.Values` → `Values`)
- [x] 2.8 Add tests: template called with `.` (full context), template called with `.Values` (sub-context), undefined template key renders empty string

## 3. Load pipeline — separate kinds and register templates

- [x] 3.1 In `load_behaviors`, after collecting and validating all items, separate them into three groups: `templates`, `abstract_behaviors`, and `behaviors` based on `kind`
- [x] 3.2 Register each `Template` item into `_TEMPLATES` (key → template string); `Template` items are excluded from the behavior lists
- [x] 3.3 Build a lookup dict `all_parents` mapping key → item for all `AbstractBehavior` and `Behavior` items (for `extend` resolution)
- [x] 3.4 Apply duplicate-key-wins logic separately for matchable behaviors (AbstractBehavior and Behavior), maintaining the existing warning log
- [x] 3.5 Compile path patterns only for `Behavior` items (AbstractBehaviors are excluded from matching)

## 4. Inheritance — extend merge logic

- [x] 4.1 Implement `_merge_behavior(parent: dict, child: dict) -> dict` following the merge rules: values maps merged child-over-parent, actions concatenated parent-first, expect merged recursively child-wins, scalar fields child-wins-or-fallback-parent
- [x] 4.2 In `load_behaviors`, after building `all_parents`, iterate each `Behavior` that has `extend`; look up the parent key in `all_parents`; if found, call `_merge_behavior`; if not found, log a debug message and continue with only the child's own fields
- [x] 4.3 Ensure inheritance is resolved after all files are loaded so forward references work
- [x] 4.4 Add tests: child inherits expect when no child expect defined; child values override parent values; parent actions precede child actions; child expect field overrides parent; missing parent is silently skipped; forward reference resolves correctly

## 5. Values in template context

- [x] 5.1 In `find_behavior`, before evaluating the condition for each candidate behavior, augment the context with `Values`: `ctx = {**context, "Values": b.get("values") or {}}`
- [x] 5.2 In `MockRequestHandler._dispatch`, after finding a behavior, build the augmented context with the matched behavior's `values` before calling `execute_actions`
- [x] 5.3 Add tests: `.Values.<key>` accessible in body; `.Values.<key>` accessible in condition; merged values from inheritance are exposed

## 6. Action ordering

- [x] 6.1 In `execute_actions`, apply `sorted(actions, key=lambda a: int(a.get("order", 0)))` with Python's built-in stable sort before iterating
- [x] 6.2 Add tests: lower order runs first; negative order runs before default; same-order actions preserve relative order; action with no `order` defaults to 0

## 7. End-to-end tests

- [x] 7.1 Add an integration test for the full template + inheritance example from the spec: `Template` fragments, `AbstractBehavior` with `reply_http`, `Behavior` extending with `values`, verify body contains rendered template output
- [x] 7.2 Add an integration test for ordered inherited actions: parent `reply_http` at order 0, child `sleep` at order -1000 — verify sleep executes before response
- [x] 7.3 Add an integration test for `.Values` in a condition: `AbstractBehavior` with `expected_token` value, `Behavior` extending with overridden token — verify matching only when header matches
