## MODIFIED Requirements

### Requirement: Mock behavior validation
Each loaded behavior SHALL be validated: `key` is required and must be a non-empty string; `kind` defaults to `"Behavior"` when omitted; accepted `kind` values are `Behavior`, `AbstractBehavior`, and `Template` — any other `kind` SHALL be rejected; a behavior with more than one `reply_http` action SHALL be rejected. Valid action types are `sleep`, `reply_http`, `redis`, and `send_http`. Each kind enforces an allowed-field rule: `Template` MAY only contain `key`, `kind`, and `template`; `AbstractBehavior` MAY contain `key`, `kind`, `expect`, `actions`, and `values`; `Behavior` MAY contain `key`, `kind`, `extend`, `expect`, `actions`, and `values`. Fields not in the allowed set SHALL be rejected at load time.

#### Scenario: Missing key rejected
- **WHEN** a behavior definition omits `key`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Multiple reply_http rejected
- **WHEN** a behavior has two or more `reply_http` actions
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Kind defaults to Behavior
- **WHEN** a behavior definition omits `kind`
- **THEN** the behavior is treated as `kind: Behavior`

#### Scenario: Unknown kind rejected
- **WHEN** a behavior defines `kind: Widget`
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Template with disallowed field rejected
- **WHEN** a `Template` definition includes an `actions` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: AbstractBehavior with template field rejected
- **WHEN** an `AbstractBehavior` definition includes a `template` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: Behavior with template field rejected
- **WHEN** a `Behavior` definition includes a `template` field
- **THEN** the server rejects the definition with an error at startup

#### Scenario: redis action accepted
- **WHEN** a behavior includes a `redis` action
- **THEN** the server loads the behavior without error

#### Scenario: send_http action accepted
- **WHEN** a behavior includes a `send_http` action
- **THEN** the server loads the behavior without error

## ADDED Requirements

### Requirement: Template kind — reusable named fragments
The server SHALL support `kind: Template` items. Each `Template` SHALL be registered under its `key` and callable from any template expression as `{{template "key" <context>}}`. Templates MAY accept any context value, including `.Values`. Templates SHALL NOT be treated as matchable behaviors.

#### Scenario: Template callable from body
- **WHEN** a `Template` with key `color-template` and `template: '{"color": "{{.color}}"}'` is defined, and a behavior body contains `{{template "color-template" .Values}}` with `values: {color: purple}`
- **THEN** the response body contains `{"color": "purple"}`

#### Scenario: Template callable with full context
- **WHEN** a `Template` with key `path-info` contains `{{.HTTPPath}}` and a behavior body calls `{{template "path-info" .}}`
- **THEN** the rendered output contains the request path

#### Scenario: Template not matched as behavior
- **WHEN** only a `Template` definition is loaded with no `Behavior` definitions
- **THEN** all requests return HTTP 404

### Requirement: AbstractBehavior kind — non-matchable base behaviors
The server SHALL support `kind: AbstractBehavior` items. An `AbstractBehavior` MAY define `expect`, `actions`, and `values`. It SHALL never match incoming requests directly and SHALL be excluded from the request-matching loop.

#### Scenario: AbstractBehavior does not match requests
- **WHEN** only an `AbstractBehavior` definition exists for `GET /api`
- **THEN** `GET /api` returns HTTP 404

#### Scenario: AbstractBehavior usable as parent
- **WHEN** an `AbstractBehavior` defines `expect.http.method: GET` and `expect.http.path: /api`, and a `Behavior` extends it
- **THEN** the `Behavior` matches `GET /api`

### Requirement: Behavior extension via extend field
A `Behavior` MAY declare `extend: <parent-key>` to inherit `expect`, `actions`, and `values` from a parent `Behavior` or `AbstractBehavior`. The server SHALL resolve extension regardless of definition order. When the parent key does not exist, the server SHALL skip the extension and load the child with only its own fields; if the child then fails field-presence validation, the server SHALL reject it. Merge rules:
1. `values` maps are merged; child keys override parent keys.
2. Parent `actions` precede child `actions`.
3. `expect` is merged recursively; child fields override matching parent fields; missing child fields inherit parent values.
4. For scalar fields (`kind`, `key`), the child's non-falsy value wins; otherwise the parent value is used.

#### Scenario: Child inherits parent expect
- **WHEN** an `AbstractBehavior` defines `expect.http.method: GET` and `expect.http.path: /teapot`, and a `Behavior` extends it with no `expect` of its own
- **THEN** `GET /teapot` matches the child behavior

#### Scenario: Child values override parent values
- **WHEN** a parent defines `values: {color: red, size: large}` and the child defines `values: {color: blue}`
- **THEN** the merged values are `{color: blue, size: large}`

#### Scenario: Parent actions precede child actions
- **WHEN** a parent defines action `sleep 100ms` and the child defines action `reply_http 200`
- **THEN** the server sleeps before sending the response

#### Scenario: Child expect field overrides parent
- **WHEN** a parent defines `expect.http.path: /base` and the child defines `expect.http.path: /override`
- **THEN** only `GET /override` matches the child behavior

#### Scenario: Missing parent skips extension
- **WHEN** a `Behavior` declares `extend: nonexistent-key`
- **THEN** the server loads the behavior using only its own fields without error

#### Scenario: Forward reference resolved
- **WHEN** a child `Behavior` is defined before its `AbstractBehavior` parent in the YAML file
- **THEN** the child still inherits the parent's fields correctly

### Requirement: Values map for behaviors
`Behavior` and `AbstractBehavior` items MAY define a `values` field as an arbitrary string-keyed map. The server SHALL expose the merged values in all template expressions (conditions, bodies, headers) as `.Values.<key>`. When a child extends a parent, the merged values map is used.

#### Scenario: Values accessible in body
- **WHEN** a behavior defines `values: {color: blue}` and body template `{{.Values.color}}`
- **THEN** the response body is `blue`

#### Scenario: Values accessible in condition
- **WHEN** a behavior defines `values: {expected_token: secret}` and condition `{{.HTTPHeader.Get "X-Token" | eq .Values.expected_token}}`
- **THEN** the condition passes when `X-Token: secret` is present

#### Scenario: Merged values available in extended behavior
- **WHEN** a parent defines `values: {a: 1}` and a child defines `values: {b: 2}`, and the child's body template uses `{{.Values.a}}` and `{{.Values.b}}`
- **THEN** both values render correctly

### Requirement: Action ordering via order field
Each action MAY include an `order` field (integer, positive, negative, or zero). The server SHALL sort all actions (including inherited ones) by `order` ascending before execution. `order` SHALL default to `0` when absent. When two actions share the same `order`, the server SHALL preserve their original relative order (stable sort).

#### Scenario: Lower order executes first
- **WHEN** a behavior has a `reply_http` action with `order: 1` and a `sleep` action with `order: 0`
- **THEN** the server sleeps before sending the response

#### Scenario: Negative order executes before default
- **WHEN** an inherited `reply_http` has no order (defaults to 0) and a child adds `sleep` with `order: -1000`
- **THEN** the sleep executes before the reply

#### Scenario: Same-order actions preserve original relative order
- **WHEN** two actions share `order: 0`
- **THEN** they execute in the order they appear in the merged actions list

#### Scenario: Default order is zero
- **WHEN** an action has no `order` field
- **THEN** it is sorted as if `order: 0`
