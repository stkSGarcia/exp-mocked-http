## 1. Template Helper Functions

- [x] 1.1 Add standard-library imports and helper utilities in `hmock.py` for JSON parsing, XML parsing, HMAC-SHA256, and deterministic UUID v5 generation.
- [x] 1.2 Implement `jsonPath(expr, data)` with empty-data and no-match handling for direct field lookup and recursive `//name` lookup.
- [x] 1.3 Implement `gJsonPath(expr, data)` with dot notation, nested fields, array indexes, array wildcard paths, array counts, empty-data handling, no-match handling, and invalid-JSON render errors.
- [x] 1.4 Implement `xmlPath(expr, data)` with XPath-style lookup, inner-text rendering, empty-data handling, and no-match handling.
- [x] 1.5 Implement `uuidv5`, `regexFindAllSubmatch`, `regexFindFirstSubmatch`, `hmacSHA256`, `isLastIndex`, and `htmlEscapeString`.
- [x] 1.6 Register all new helper functions in the existing `FUNCTIONS` map so conditions, inline bodies, headers, and file-backed bodies can use them.

## 2. File-Backed Response Body Loading

- [x] 2.1 Extend `reply_http` validation to accept optional string `body_from_file` while preserving existing `body`, `headers`, and `status_code` behavior.
- [x] 2.2 Resolve `body_from_file` relative to `HM_TEMPLATES_DIR`, reject paths outside the templates directory, reject missing or non-file paths, and load file contents during `load_behaviors`.
- [x] 2.3 Store the loaded body-file snapshot on the normalized action payload so later filesystem edits do not affect the running configuration.
- [x] 2.4 Keep duplicate-key replacement, YAML discovery order, and other validation behavior unchanged.

## 3. HTTP Reply Execution

- [x] 3.1 Update `execute_behavior` to select a non-empty inline `body` before falling back to the loaded file-backed body snapshot.
- [x] 3.2 Render file-backed body content with the same template context and helper functions as inline response bodies.
- [x] 3.3 Confirm every `reply_http.headers` value continues to render as a template with the shared request context.
- [x] 3.4 Preserve default `Content-Type`, computed `Content-Length`, render-error handling, and empty-body fallback behavior.

## 4. Tests

- [x] 4.1 Add renderer tests covering `jsonPath`, `gJsonPath`, `xmlPath`, `uuidv5`, regex helpers, `hmacSHA256`, `isLastIndex`, and `htmlEscapeString`.
- [x] 4.2 Add tests for `gJsonPath` invalid JSON render errors and empty/no-match returns for JSON and XML helpers.
- [x] 4.3 Add loader tests for `body_from_file` relative path resolution, missing file rejection, outside-root rejection, and load-time snapshot behavior.
- [x] 4.4 Add HTTP tests proving file-backed bodies render with request context and helper functions.
- [x] 4.5 Add HTTP tests proving inline non-empty `body` takes precedence and empty or omitted `body` uses `body_from_file`.
- [x] 4.6 Add or retain tests proving templated response headers render with the shared context.

## 5. Verification

- [x] 5.1 Run `uv run pytest`.
- [x] 5.2 Run any OpenSpec validation/status command available for the change and confirm the change is apply-ready.
