## 1. Project Setup

- [x] 1.1 Inspect the Python project/runtime files and identify whether dependencies for YAML parsing or testing need to be added.
- [x] 1.2 Create `hmock.py` as the server entry point runnable with `uv run --project /app hmock.py`.
- [x] 1.3 Add or update test scaffolding for unit and integration coverage of the mock server behavior.

## 2. Configuration and Logging

- [x] 2.1 Implement environment configuration for `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, and `HM_LOG_LEVEL` with documented defaults.
- [x] 2.2 Implement structured JSON logging with `debug`, `info`, `warn`, and `error` filtering.
- [x] 2.3 Log each HTTP request/response pair at `info` with `http_path`, `http_method`, `http_host`, `http_req`, and `http_res`.

## 3. YAML Loading and Validation

- [x] 3.1 Recursively discover `.yaml` and `.yml` files under `HM_TEMPLATES_DIR` in deterministic order.
- [x] 3.2 Load YAML objects from discovered files and merge them into one ordered behavior list.
- [x] 3.3 Validate behavior keys, default omitted `kind` to `Behavior`, and reject invalid definitions.
- [x] 3.4 Reject behaviors containing more than one `reply_http` action.
- [x] 3.5 Resolve duplicate keys so the last loaded behavior wins and emit a warning for each override.

## 4. HTTP Server and Matching

- [x] 4.1 Implement the HTTP listener and request handler for all HTTP methods supported by the Python server stack.
- [x] 4.2 Match requests by expected HTTP method and path in active behavior load order.
- [x] 4.3 Compile `:param` path patterns into anchored matches and expose captured values in request URL context.
- [x] 4.4 Return status `404 Not Found` with body exactly `not found` when no behavior matches.

## 5. Template Rendering

- [x] 5.1 Build the request template context with `.HTTPHeader`, `.HTTPBody`, `.HTTPPath`, and `.HTTPQueryString`.
- [x] 5.2 Implement template parsing with `{{ ... }}` delimiters and pre-parse replacement of `\r\n`, `\n`, and `\t` with spaces.
- [x] 5.3 Implement expression, pipeline, conditional, loop, assignment, raw string, and whitespace-trim support required by the spec.
- [x] 5.4 Implement built-in comparison, logic, output, encoding, collection, and invocation template functions.
- [x] 5.5 Implement extended string, fallback, base64, environment, math, and UUID template functions.
- [x] 5.6 Treat undefined variables and template render failures as errors.

## 6. Conditions and Actions

- [x] 6.1 Evaluate missing or empty conditions as passing.
- [x] 6.2 Evaluate non-empty conditions as templates that pass only when rendered output is exactly `true`.
- [x] 6.3 Skip a behavior when condition rendering fails and continue evaluating later behaviors.
- [x] 6.4 Execute matched behavior actions in listed order and stop evaluating later behaviors.
- [x] 6.5 Implement `sleep` actions with `ns`, `us`, `ms`, `s`, `m`, and `h` duration units.
- [x] 6.6 Implement `reply_http` actions with rendered status, headers, and body handling.
- [x] 6.7 Default `Content-Type` to `application/json` unless overridden and set `Content-Length` from rendered body length.

## 7. Verification

- [x] 7.1 Add tests for configuration defaults and environment overrides.
- [x] 7.2 Add tests for YAML discovery, loading order, validation failures, and duplicate-key override warnings.
- [x] 7.3 Add tests for exact path matching, `:param` captures, first passing behavior selection, and unmatched 404 responses.
- [x] 7.4 Add tests for condition pass/fail behavior and condition render failures.
- [x] 7.5 Add tests for template context, syntax, functions, undefined variables, and response header/body rendering.
- [x] 7.6 Add tests for `reply_http`, `sleep`, action execution order, and response defaults.
- [x] 7.7 Add tests or captured assertions for structured JSON request/response logging and log-level filtering.
- [x] 7.8 Run the full test suite and an end-to-end smoke test using a sample YAML mock file.
