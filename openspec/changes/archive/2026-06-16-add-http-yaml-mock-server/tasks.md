## 1. Project Entry Point And Test Harness

- [x] 1.1 Create top-level `hmock.py` with configuration loading for `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, and `HM_LOG_LEVEL`.
- [x] 1.2 Add a pytest-based test harness that can import `hmock.py` and exercise loader, renderer, matcher, logger, and HTTP server behavior.
- [x] 1.3 Add fixtures for temporary template directories, YAML mock files, captured logs, and an ephemeral HTTP server port.

## 2. Mock Definition Loading

- [x] 2.1 Implement recursive `.yaml` and `.yml` discovery under `HM_TEMPLATES_DIR` with deterministic file ordering.
- [x] 2.2 Implement YAML parsing and merging of top-level mock objects into one ordered behavior stream.
- [x] 2.3 Implement behavior validation for required non-empty string `key`, default `kind: Behavior`, action shape, and at most one `reply_http` action.
- [x] 2.4 Implement duplicate-key replacement where the last loaded behavior wins and warning logs describe overrides.
- [x] 2.5 Add tests for configuration defaults and overrides, recursive discovery, ignored non-YAML files, schema validation, ordered merge, and duplicate-key replacement.

## 3. Template Rendering

- [x] 3.1 Implement request template context for `.HTTPHeader.Get`, `.HTTPBody`, `.HTTPPath`, `.HTTPQueryString`, and captured path parameter access.
- [x] 3.2 Implement template preprocessing that replaces `\r\n`, `\n`, and `\t` with spaces before parsing.
- [x] 3.3 Implement parsing and rendering for `{{ ... }}` expressions, pipelines, conditionals, ranges, assignments, raw strings, and trim delimiters.
- [x] 3.4 Implement strict undefined-variable handling so missing context values produce render errors.
- [x] 3.5 Implement built-in functions for comparison, logic, output, encoding, collections, and invocation.
- [x] 3.6 Implement extended functions for strings, fallback helpers, Base64, environment variables, math, and UUID v4 generation.
- [x] 3.7 Add renderer tests covering each supported syntax form, required context variable, render error behavior, and function category.

## 4. HTTP Matching And Action Execution

- [x] 4.1 Implement HTTP server startup in `hmock.py` using the configured host and port.
- [x] 4.2 Implement method and path matching against `expect.http.method` and `expect.http.path`, excluding query strings from route matching.
- [x] 4.3 Implement `:param` path segment matching and capture propagation into the template context.
- [x] 4.4 Implement load-order behavior evaluation with condition rendering where only exactly `true` passes and render errors are non-matches.
- [x] 4.5 Implement ordered action execution with `sleep` duration parsing for `ns`, `us`, `ms`, `s`, `m`, and `h`.
- [x] 4.6 Implement `reply_http` responses with required status code, rendered headers and body, default `Content-Type: application/json`, computed `Content-Length`, and default empty body.
- [x] 4.7 Implement unmatched request handling with status `404 Not Found` and body exactly `not found`.
- [x] 4.8 Add tests for exact matching, method mismatch, query handling, named path parameters, condition routing, sleep duration validation, reply defaults, templated responses, and unmatched 404 responses.

## 5. Structured Logging

- [x] 5.1 Implement structured JSON logging with levels `debug`, `info`, `warn`, and `error`.
- [x] 5.2 Implement log-level filtering so `info` request logs are suppressed when `HM_LOG_LEVEL` is `warn` or `error`.
- [x] 5.3 Log each handled HTTP request/response pair at `info` with `http_path`, `http_method`, `http_host`, `http_req`, and `http_res`.
- [x] 5.4 Add tests for JSON log shape, log-level filtering, request/response fields, unmatched request logs, and duplicate-key warning logs.

## 6. End-To-End Verification

- [x] 6.1 Add an end-to-end test for the basic `/ping` YAML example returning `200 OK`, `Content-Type: text/plain`, and `Content-Length: 2`.
- [x] 6.2 Add an end-to-end test for condition routing using `X-Token` to return either `200 OK` or `401 unauthorized`.
- [x] 6.3 Verify the server starts with `uv run --project /app hmock.py` in the target layout or document any local test equivalent required by the repository.
- [x] 6.4 Run the full test suite and fix any regressions before marking implementation complete.
