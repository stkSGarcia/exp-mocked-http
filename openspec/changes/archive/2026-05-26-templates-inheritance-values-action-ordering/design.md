## Context

The server is a single-file Python HTTP mock (`hmock.py`) using Jinja2 for template rendering. YAML files are loaded into a flat list of behavior dicts. Validation is done in `_validate_behavior`. Matching is in `find_behavior`. Actions execute in `execute_actions`. The Jinja2 environment is a module-level singleton (`_JINJA`) built by `_make_jinja_env`. The preprocess step (`_preprocess`) translates Go-template syntax to Jinja2 syntax before rendering.

Currently, the system supports one `kind` value (`Behavior`) and has no inheritance, no shared fragments, no per-behavior values, and no action ordering.

## Goals / Non-Goals

**Goals:**
- Add `Template`, `AbstractBehavior`, and `Behavior` kinds with per-kind field validation.
- Support named template fragments registered at load time and callable inside any template expression.
- Support `extend` for inheriting `expect`, `actions`, and `values` from a parent.
- Expose per-behavior `values` maps as `.Values.<key>` in all template expressions.
- Sort actions by `order` field before execution.

**Non-Goals:**
- Multi-level inheritance chains (child → parent → grandparent).
- Runtime template reloading.
- Circular inheritance detection (undefined parents are silently skipped per spec).

## Decisions

### Decision 1: Expand the dot-stripping regex to cover all identifiers

**Current**: `_CTX_VAR_RE = re.compile(r"(?<![.\w])\.(HTTP\w+)")` only strips `.` from `.HTTPXxx` vars.

**Change to**: `r"(?<![.\w])\.(\w+)"` — strip leading dots from any standalone `.<identifier>`.

**Why**: When a Template is called with `.Values` as context (`{{template "key" .Values}}`), the sub-template uses `.color` to access a key. Stripping all leading dots maps `.color` → `color`, which Jinja2 can resolve from whatever dict is passed to `render(**ctx)`. The broader regex also handles `.Values` → `Values` without a special case.

**Risk**: If a template currently used `.<something>` where `<something>` is NOT a key in the context, it would have rendered as an error before and still would — no behavioral regression.

### Decision 2: Register templates in a module-level dict; render via a context-aware function

**`_TEMPLATES: dict[str, str]`** — maps template key → raw template string, populated during `load_behaviors`.

**`_render_tmpl(key, ctx)`** — Jinja2 global function that looks up the template string, runs it through `_preprocess`, and renders with the given context. When `ctx` is `None`, falls back to a thread-local holding the current request context (for `{{template "key" .}}`).

`render()` stores `context` in `threading.local()` before calling `tmpl.render()` so `_render_tmpl` can access it for the "full context" case.

**Why this over Jinja2's DictLoader + `{% include %}`**: `include` shares the parent scope and cannot accept a different context dict. Go's `{{template "key" .Values}}` explicitly passes a sub-context. The function approach supports both `.` (full context via thread-local) and sub-objects (e.g., `.Values`) uniformly.

**In `_preprocess`**: detect `template "key" <expr>` inside `{{ }}` blocks and emit `_render_tmpl("key", <expr-or-None>)`. Pattern: if inner text matches `template "<key>" <ctx-expr>`, convert `.` → `None`; otherwise apply the same dot-stripping to `<ctx-expr>`.

### Decision 3: Resolve inheritance after all items are loaded; filter to Behavior for matching

`load_behaviors` currently validates then merges. After this change:
1. Collect all items → validate per kind.
2. Register `Template` items in `_TEMPLATES`; exclude them from the behavior list.
3. Build a lookup dict of all `AbstractBehavior` and `Behavior` items by key.
4. For each `Behavior` with `extend`, resolve the parent (regardless of definition order) and apply merge rules.
5. Exclude `AbstractBehavior` items from the matchable list.

**Why post-load resolution**: parents may be defined after children in the YAML. A single pass over the full list (after all files are loaded) handles arbitrary ordering. Since the spec says to skip missing parents (not error), a simple dict lookup suffices — no topological sort needed.

**Merge rules** (implemented in a `_merge_behavior` helper):
- `values`: `{**parent_values, **child_values}` (child overrides).
- `actions`: `parent_actions + child_actions` (parent first).
- `expect`: recursive dict merge, child keys win.
- `kind`/`key`/other scalar fields: child's non-falsy value wins, else parent's.

### Decision 4: Inject `.Values` into context per behavior at match time

`find_behavior` augments the context for each candidate behavior before evaluating its condition:
```python
ctx = {**context, "Values": b.get("values") or {}}
```
Action execution receives this augmented context from the dispatch loop in `MockRequestHandler._dispatch`.

**Why per-behavior augmentation, not at build_context**: Values are specific to each behavior (merged at load time). Injecting them per candidate keeps `build_context` generic.

### Decision 5: Stable sort of actions by `order` before execution

`execute_actions` applies `sorted(actions, key=lambda a: a.get("order", 0))` with Python's stable sort before iterating. The `order` field is validated as a numeric type in `_validate_behavior`.

After inheritance merge, actions from parent and child are concatenated (parent first), then sorted. The stable sort preserves original relative order for ties.

## Risks / Trade-offs

- **Thread-local for template context**: makes `_render_tmpl` non-reentrant if two concurrent renders nest template calls. Python's GIL and the per-request handler threading model make this safe in the current architecture. → If threading model changes, switch to a context-local passed through the call stack.

- **Expanded dot-stripping regex**: any template expression using `.<word>` that was previously silently broken now maps to a local variable. → No regression for correct templates; broken templates stay broken.

- **Missing parent is silently skipped**: per spec. If a typo causes a missing parent, the child may load with missing `expect`/`actions`, which will then fail field-presence validation. → Acceptable; the spec explicitly requires this behavior.

## Open Questions

_(none — spec is fully prescriptive)_
