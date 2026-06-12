## 1. Template Helper Functions

- [x] 1.1 Add JSON parsing helpers for `jsonPath` and `gJsonPath`, including empty-data handling, missing-match handling, nested fields, indexes, wildcards, counts, and invalid JSON render errors for `gJsonPath`.
- [x] 1.2 Add XML XPath helper support for `xmlPath`, including empty-data and missing-match handling.
- [x] 1.3 Add deterministic `uuidv5`, regex submatch, `hmacSHA256`, `isLastIndex`, and `htmlEscapeString` helpers to the template environment as globals and filters.
- [x] 1.4 Add focused unit tests proving the new helpers work in inline templates and preserve existing helper behavior.

## 2. File-Backed Response Bodies

- [x] 2.1 Extend behavior loading so `reply_http.body_from_file` resolves relative to `HM_TEMPLATES_DIR`, reads UTF-8 content, and stores a stable snapshot on the loaded reply configuration.
- [x] 2.2 Reject or fail clearly when `body_from_file` resolves outside `HM_TEMPLATES_DIR` or cannot be read.
- [x] 2.3 Update response building so a non-empty inline `body` takes precedence and an empty or missing `body` falls back to the loaded file snapshot.
- [x] 2.4 Render file-backed body snapshots at request time with the same request context and template helpers as inline bodies.

## 3. Headers and Response Integration

- [x] 3.1 Ensure every configured `reply_http.headers` value continues to render as a template after the helper expansion.
- [x] 3.2 Preserve default `Content-Type`, configured `Content-Type` override, and `Content-Length` calculation for inline and file-backed bodies.
- [x] 3.3 Add tests for templated headers using new helpers and for content length generated from a rendered file-backed body.

## 4. Verification

- [x] 4.1 Add integration-style tests for `body_from_file` resolution, snapshot behavior, body precedence, and empty-body fallback.
- [x] 4.2 Run the project test suite with `uv run pytest`.
- [x] 4.3 Run OpenSpec validation/status checks for `add-template-helpers-file-backed-bodies`.
