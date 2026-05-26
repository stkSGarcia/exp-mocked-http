## 1. Project Setup

- [x] 1.1 Create `pyproject.toml` with `jinja2` and `pyyaml` dependencies
- [x] 1.2 Create empty `hmock.py` with shebang and top-level `main()` entry point
- [x] 1.3 Create `templates/` directory with a sample YAML mock file for manual testing

## 2. Configuration and Logging

- [x] 2.1 Read and validate env vars: `HM_TEMPLATES_DIR`, `HM_HTTP_PORT`, `HM_HTTP_HOST`, `HM_LOG_LEVEL`
- [x] 2.2 Implement structured JSON logger that honors `HM_LOG_LEVEL`

## 3. YAML Loading and Validation

- [x] 3.1 Implement recursive YAML scanner (sorted `os.walk`, `.yaml`/`.yml` files)
- [x] 3.2 Parse each file as a list of behavior dicts and merge into one ordered list
- [x] 3.3 Validate each behavior: `key` required and non-empty, `kind` defaults to `"Behavior"`, reject >1 `reply_http` action
- [x] 3.4 Implement duplicate-key detection: last-wins replacement with warning log

## 4. Path Matching

- [x] 4.1 Compile each behavior's `expect.http.path` from `:param` syntax to a named-group regex at load time
- [x] 4.2 Implement `match_path(pattern, path)` returning captured params dict or None

## 5. Template Engine

- [x] 5.1 Configure Jinja2 environment with `StrictUndefined` and `{{ }}` delimiters
- [x] 5.2 Register extended functions: `contains`, `hasPrefix`, `hasSuffix`, `replace`, `trim`, `upper`, `lower`, `title`, `split`, `splitList`, `join`, `repeat`, `nospace`, `toString`, `default`, `empty`, `coalesce`, `ternary`, `b64enc`, `b64dec`, `env`, `add`, `sub`, `mul`, `div`, `mod`, `max`, `min`, `uuidv4`
- [x] 5.3 Implement `render(template_str, context)` that replaces `\r\n`, `\n`, `\t` with spaces before parsing, then renders; returns `(result, error)`
- [x] 5.4 Implement `HeaderMap` class with `.Get(name)` method usable from templates

## 6. Request Matching and Condition Evaluation

- [x] 6.1 Implement `build_context(request)` returning dict with `.HTTPHeader`, `.HTTPBody`, `.HTTPPath`, `.HTTPQueryString`
- [x] 6.2 Implement `find_behavior(behaviors, method, path, context)` iterating in order: check method+path match, then render condition and check for exact `"true"`, return first match or None
- [x] 6.3 Handle condition render errors by skipping the behavior (no match)

## 7. Action Execution

- [x] 7.1 Implement `execute_sleep(action)`: parse duration string with unit support (`ns`, `us`, `ms`, `s`, `m`, `h`), sleep accordingly
- [x] 7.2 Implement `execute_reply_http(action, context, handler)`: render body and each header value as templates, default `Content-Type: application/json`, set `Content-Length`, write response
- [x] 7.3 Implement `execute_actions(actions, context, handler)` iterating the action list in order

## 8. HTTP Server

- [x] 8.1 Implement `MockRequestHandler(BaseHTTPRequestHandler)` with `do_METHOD` routing for all HTTP methods
- [x] 8.2 On each request: build context, call `find_behavior`, execute actions or return 404 with body `not found`
- [x] 8.3 Log each request/response pair at `info` with `http_path`, `http_method`, `http_host`, `http_req`, `http_res`
- [x] 8.4 Start `HTTPServer` on configured host/port in `main()`

## 9. Validation and Testing

- [x] 9.1 Verify `GET /ping` example from spec returns `200`, `Content-Type: text/plain`, `Content-Length: 2`, body `OK`
- [x] 9.2 Verify condition routing example: `X-Token: t1234` returns 200, wrong token returns 401
- [x] 9.3 Verify 404 response body is exactly `not found`
- [x] 9.4 Verify duplicate key warning is logged and last definition wins
- [x] 9.5 Verify `sleep` action delays response by the specified duration
