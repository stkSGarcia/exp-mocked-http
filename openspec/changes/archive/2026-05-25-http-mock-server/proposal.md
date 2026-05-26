## Why

We need a local HTTP mock server that can be configured via YAML files, allowing developers to simulate HTTP services without running real backends. This enables fast, deterministic testing and development workflows.

## What Changes

- Introduce `hmock.py`: a single-file HTTP mock server driven by YAML mock definitions
- Support recursive scanning of a templates directory for `.yaml`/`.yml` mock files
- Implement HTTP request matching by method and path (including `:param` named parameters)
- Support conditional matching via Go-style template expressions
- Execute ordered action sequences (`reply_http`, `sleep`) per matched behavior
- Render response bodies and headers as templates with request context variables
- Emit structured JSON logs per request/response pair

## Capabilities

### New Capabilities

- `http-mock-server`: Core mock server that loads YAML behavior definitions, matches incoming HTTP requests by method/path/condition, and executes response actions with template rendering

### Modified Capabilities

## Impact

- New file: `hmock.py` at project root
- Runtime dependency on Python with `uv` for project management
- YAML parsing library required (e.g., PyYAML)
- No changes to existing code (greenfield implementation)
