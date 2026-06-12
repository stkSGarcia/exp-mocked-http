## Why

Mock definitions need to express common payload-routing and response-shaping logic without embedding custom Python. The current HTTP mock server already renders templates, but checkpoint 2 requires richer helpers, reusable file-backed response bodies, and fully templated headers so realistic mocks can stay declarative.

## What Changes

- Add template helper functions for JSON, XML, regex, deterministic UUID, HMAC, list-index checks, and HTML escaping.
- Add `reply_http.body_from_file` for loading response body templates from files under `HM_TEMPLATES_DIR`.
- Define precedence when both `body` and `body_from_file` are configured: use the file only when `body` is empty.
- Render file-backed bodies at request time using the same request context and template helpers as inline response bodies.
- Require `reply_http.headers` values to render as templates with the expanded helper set.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `http-yaml-mock-server`: Extend HTTP mock templating and `reply_http` response body behavior.

## Impact

- Affects `hmock.py` template rendering, YAML loading or validation for `reply_http`, and HTTP response generation.
- Adds test coverage for helper rendering, invalid JSON render errors, file-backed response bodies, body precedence, template snapshots, and templated headers.
- May require Python dependencies or small internal helpers for JSONPath, XML XPath, UUID v5, HMAC-SHA256, and HTML escaping.
