## Context

The current `hmock.py` implementation already loads YAML behaviors, renders inline templates, executes `reply_http`, and renders response header values. The checkpoint extends that foundation with richer helper functions and response bodies sourced from files under `HM_TEMPLATES_DIR`.

The main constraint is preserving the single-file, testable server shape while adding enough structure to snapshot file-backed bodies at load time and keep template helper failures predictable.

## Goals / Non-Goals

**Goals:**
- Expose the new helper functions in every template render context used by conditions, response bodies, response headers, and file-backed body templates.
- Support `reply_http.body_from_file` relative to `HM_TEMPLATES_DIR` with load-time file reading and stable per-configuration snapshots.
- Preserve existing inline `body` behavior and use `body_from_file` only when inline `body` is missing or empty.
- Keep template errors explicit: invalid JSON for `gJsonPath` fails rendering, while empty data or missing matches return an empty string where specified.
- Cover the new behavior with focused renderer, loader, and HTTP tests.

**Non-Goals:**
- Hot reload or per-request file reads for `body_from_file`.
- A complete implementation of every JSONPath, gjson, or XPath dialect edge case beyond the checkpoint examples.
- Changing the YAML schema beyond adding `reply_http.body_from_file`.
- Changing route matching, condition routing, logging, or response default semantics.

## Decisions

1. **Snapshot file-backed bodies during behavior loading.**

   `load_behaviors` should pass `HM_TEMPLATES_DIR` context into validation/normalization so each `reply_http.body_from_file` path can be resolved, read, and stored on the action payload before serving starts. This gives stable behavior for the loaded configuration and avoids request-time filesystem access.

   Alternative considered: read the file for every request. That would make live edits visible immediately, but it would violate the requested stable snapshot behavior and make failures appear during unrelated requests.

2. **Resolve `body_from_file` as a relative template path.**

   Treat `body_from_file` as relative to `HM_TEMPLATES_DIR` and normalize it with `Path.resolve()`. Reject paths that do not resolve beneath the templates directory, are missing, or are not regular files. Store the loaded content separately from the original path, such as `body_from_file_content`, so execution does not need to know about filesystem paths.

   Alternative considered: allow absolute paths. Keeping paths template-root relative matches YAML discovery and avoids accidental reads outside the configured mock fixture tree.

3. **Choose body source at execution time with inline-body precedence.**

   `execute_behavior` should use inline `body` when it is present and non-empty. Otherwise it should render the loaded file content if `body_from_file` was configured, falling back to an empty body when neither source is present.

   Alternative considered: reject actions that set both fields. The checkpoint explicitly defines precedence, so allowing both is part of the contract.

4. **Implement helper functions as small focused adapters.**

   Add helper functions to the existing `FUNCTIONS` map:
   - `jsonPath` parses JSON and supports simple field selection plus recursive `//name` lookup, returning matched scalar/text content or an empty string.
   - `gJsonPath` parses JSON and supports dot fields, numeric array indexes, `#` array counts, and `#` wildcards such as `items.#.id`.
   - `xmlPath` uses the standard XML parser for XPath-like element lookup and returns element text or an empty string.
   - `uuidv5`, regex helpers, `hmacSHA256`, `isLastIndex`, and `htmlEscapeString` use standard-library primitives.

   Alternative considered: add broad third-party query libraries. The examples are narrow enough for local implementations, and avoiding dependencies keeps the single-file tool easy to run.

## Risks / Trade-offs

- Limited query dialect support could surprise users with complex JSONPath/gjson/XPath expressions -> Document behavior through tests matching the supported checkpoint examples and return empty strings for unsupported misses where specified.
- Invalid `gJsonPath` input can surface as a 500 during response rendering -> Add tests proving invalid JSON raises `TemplateError` and is handled by existing response-render error handling.
- Path traversal in `body_from_file` could read unintended files -> Resolve paths against `HM_TEMPLATES_DIR` and reject files outside that root.
- Snapshot storage duplicates large response bodies in memory -> Accept this trade-off for deterministic mocks and local test workloads.

## Migration Plan

This is a backward-compatible extension. Existing YAML mocks continue to use inline `body`; new mocks can opt into `body_from_file`. Rollback is removing the helper implementations, file-backed body normalization, and related tests.

## Open Questions

None.
