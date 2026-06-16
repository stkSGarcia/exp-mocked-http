## Why

Mock definitions need richer request-derived template helpers and a way to keep larger response payloads in separate files. This change makes HTTP mocks easier to keep readable while supporting JSON, XML, regex, deterministic IDs, HMAC signatures, index checks, HTML escaping, and file-backed response bodies.

## What Changes

- Add template helper functions for JSONPath-style JSON lookup, gjson-style JSON lookup, XPath XML lookup, deterministic UUID v5 generation, regex capture extraction, HMAC-SHA256, last-index checks, and HTML string escaping.
- Add `reply_http.body_from_file` support that loads response template content relative to `HM_TEMPLATES_DIR`, snapshots it during configuration loading, and renders it at request time.
- Define precedence between `reply_http.body` and `reply_http.body_from_file`: use the file-backed body only when `body` is absent or empty.
- Render file-backed response body templates with the same request context and helper functions as inline response bodies.
- Render every `reply_http.headers` value as a template.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `template-rendering`: Adds richer helper functions available in all template render contexts.
- `http-behavior-mocking`: Adds file-backed `reply_http` response body selection and confirms templated response headers.
- `mock-definition-loading`: Adds validation and load-time snapshot behavior for `reply_http.body_from_file`.

## Impact

- Affects `hmock.py` template function registration, render behavior, mock loading/validation, and HTTP reply execution.
- Adds tests for new helper functions, file-backed response body loading/rendering, body precedence, header templating, invalid JSON errors, missing matches, and snapshot semantics.
- May require additional Python dependencies or small local implementations for JSONPath/gjson/XPath behavior if the standard library is insufficient.
