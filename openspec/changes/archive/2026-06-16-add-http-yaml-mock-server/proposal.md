## Why

Developers need a lightweight local mock service that can replay HTTP behavior from versioned YAML definitions without writing custom server code for every test scenario. This revision establishes the HTTP-only foundation for a future multi-protocol mock server.

## What Changes

- Add `hmock.py` as an executable mock server entry point started with `uv run --project /app hmock.py`.
- Load `.yaml` and `.yml` mock definition files recursively from `HM_TEMPLATES_DIR`, merge them in order, validate required behavior fields, and handle duplicate keys with last-definition-wins semantics.
- Serve HTTP traffic on `HM_HTTP_HOST` and `HM_HTTP_PORT`, matching behaviors by method, path, optional named path parameters, and template conditions.
- Execute ordered `reply_http` and `sleep` actions, including templated response headers and bodies.
- Provide a Go-template-like expression renderer for conditions and response templates with the required built-in and extended functions.
- Emit structured JSON logs that honor `HM_LOG_LEVEL` and include request/response details for each HTTP exchange.

## Capabilities

### New Capabilities
- `mock-definition-loading`: Covers environment-driven template discovery, YAML mock schema validation, behavior ordering, and duplicate-key handling.
- `http-behavior-mocking`: Covers HTTP request matching, path parameters, condition routing, action execution, response defaults, and unmatched responses.
- `template-rendering`: Covers template syntax, context variables, render error handling, and built-in/extended functions used by conditions and response fields.
- `structured-http-logging`: Covers JSON log output, log-level filtering, duplicate-key warnings, and per-request HTTP log fields.

### Modified Capabilities

None.

## Impact

- Adds a new top-level `hmock.py` application file.
- Requires runtime support for YAML parsing, HTTP serving, template evaluation, duration parsing, and structured JSON logging.
- Defines user-facing behavior through environment variables, YAML mock definitions, HTTP responses, and log output.
