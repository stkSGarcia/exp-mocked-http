## Why

The project needs a runnable first slice of a multi-protocol mock server so mock behavior can be defined declaratively and exercised locally. This change delivers the HTTP request mocking revision as a single `hmock.py` entry point driven by YAML mock definitions.

## What Changes

- Add an executable `hmock.py` server started with `uv run --project /app hmock.py`.
- Load YAML mock definitions from `HM_TEMPLATES_DIR`, recursively scanning `.yaml` and `.yml` files.
- Validate behavior definitions, including required unique keys and at most one `reply_http` action per behavior.
- Match HTTP requests by method, path patterns with `:param` captures, and optional template conditions.
- Render template expressions for conditions, response headers, and response bodies with request context.
- Execute ordered `reply_http` and `sleep` actions, returning the first matching behavior response.
- Return `404 Not Found` with body exactly `not found` when no behavior matches.
- Emit structured JSON logs and honor the configured log level.

## Capabilities

### New Capabilities

- `http-yaml-mock-server`: Defines YAML-driven HTTP request mocking, template rendering, action execution, duplicate-key handling, and request/response logging.

### Modified Capabilities

None.

## Impact

- Adds the main Python runtime file `hmock.py`.
- Adds YAML parsing, HTTP serving, template evaluation, duration parsing, and structured logging behavior.
- Introduces environment-based configuration through `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, and `HM_LOG_LEVEL`.
- May require Python dependencies for YAML loading and template/function support if they are not already available in the project environment.
