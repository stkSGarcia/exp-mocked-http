## Why

The current template system provides only basic variable substitution and sprig functions, leaving users unable to extract structured data from JSON/XML request bodies, generate deterministic IDs, or load large response bodies from separate files. These additions make it practical to write realistic, data-driven mocks without embedding logic in YAML.

## What Changes

- Add `jsonPath(expr, data)` template function: XPath-style JSON querying
- Add `gJsonPath(expr, data)` template function: dot-notation JSON querying with array index and wildcard support
- Add `xmlPath(expr, data)` template function: XPath querying over XML data
- Add `uuidv5(data)` template function: deterministic UUID v5 generation (OID namespace)
- Add `regexFindAllSubmatch(pattern, str)` template function: returns all capture groups from first regex match
- Add `regexFindFirstSubmatch(pattern, str)` template function: returns first capture group from first regex match
- Add `hmacSHA256(secret, data)` template function: hex-encoded HMAC-SHA256 digest
- Add `isLastIndex(index, array)` template function: true when index is the last valid index
- Add `htmlEscapeString(str)` template function: HTML-escape `<`, `>`, `&`, `"`, `'`
- Add `body_from_file` field to `reply_http`: load response body from a file path relative to `HM_TEMPLATES_DIR`
- Clarify that every `reply_http.headers` value is rendered as a template

## Capabilities

### New Capabilities
<!-- none — all changes extend the existing http-mock-server capability -->

### Modified Capabilities
- `http-mock-server`: Extended template function set, `body_from_file` field on `reply_http`, and explicit requirement for header template rendering

## Impact

- Template engine initialization: register nine new functions
- `reply_http` action handler: add `body_from_file` loading logic at config-load time (snapshot), fall back to `body` when `body_from_file` is empty
- Header rendering: confirm each header value passes through the template engine
- Dependencies: `github.com/google/uuid` (uuidv5), an XML XPath library (e.g. `github.com/antchfx/xmlquery`), a JSON path library (e.g. `github.com/antchfx/jsonquery` for jsonPath; `github.com/tidwall/gjson` for gJsonPath)
