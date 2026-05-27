## 1. Binary File Payloads — reply_http

- [x] 1.1 In `_validate_behavior`, add path-security validation for `reply_http.body_from_binary_file` (same `realpath`/`startswith` guard as `body_from_file`)
- [x] 1.2 In `_validate_behavior`, open `body_from_binary_file` in `rb` mode and store the bytes in `cfg["_binary_snapshot"]`
- [x] 1.3 In `execute_reply_http`, detect `_binary_snapshot`; send binary bytes as-is, set `Content-Length` from `len(bytes)`, skip template rendering for the body
- [x] 1.4 In `execute_reply_http`, when `binary_file_name` is set, add `Content-Disposition: inline; filename="<name>"` to the response headers
- [x] 1.5 In `execute_reply_http`, honour precedence: use binary snapshot only when `body` is empty (same rule as `body_from_file`)

## 2. Binary File Payloads — send_http

- [x] 2.1 In `_validate_behavior`, add path-security validation and `rb` snapshot for `send_http.body_from_binary_file`, stored as `cfg["_binary_snapshot"]`
- [x] 2.2 In `execute_send_http`, when `_binary_snapshot` is present and `method == "POST"`, build a `multipart/form-data` request with field name `file`; use `binary_file_name` as the part filename, or `basename(body_from_binary_file)` if absent; default part content type to `application/octet-stream`
- [x] 2.3 In `execute_send_http`, when `_binary_snapshot` is present and method is not `POST`, send the raw binary bytes as the request body

## 3. CORS Middleware

- [x] 3.1 Add `HM_CORS_ENABLED` environment variable (default `false`) at the top of `hmock.py`
- [x] 3.2 In `MockRequestHandler._dispatch`, after writing the response, inject the four CORS headers (`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: *`, `Access-Control-Allow-Headers: *`, `Access-Control-Allow-Credentials: true`) when `HM_CORS_ENABLED=true`; mock-defined headers from `reply_http.headers` take precedence over middleware headers
- [x] 3.3 In `MockRequestHandler._dispatch`, when `HM_CORS_ENABLED=true` and the request method is `OPTIONS` and no behavior was matched, return `200 OK` with empty body plus the four CORS headers (preflight handling)

## 4. Hot Reload

- [x] 4.1 Add `HM_TEMPLATES_DIR_HOT_RELOAD` environment variable (default `true`) at the top of `hmock.py`
- [x] 4.2 Protect the global template/behavior state with a `threading.Lock`; wrap all reads and the atomic swap in `_trigger_reload` with that lock
- [x] 4.3 Implement a polling-based watcher: a background daemon thread that scans `HM_TEMPLATES_DIR` for mtime changes every ~1 second and calls `_trigger_reload` when a change is detected; activate when `HM_TEMPLATES_DIR_HOT_RELOAD=true` and `watchdog` is not importable
- [x] 4.4 Implement a `watchdog`-based watcher: if `watchdog` is importable, use `Observer` + `FileSystemEventHandler` for low-latency detection; call `_trigger_reload` on create/modify/delete events with a ~200ms debounce; activate in preference to polling when available
- [x] 4.5 In `_trigger_reload`, catch validation errors and log them without replacing the existing template state (preserve-on-error guarantee)
- [x] 4.6 At server startup, log an info-level message indicating whether hot reload is active and which mechanism (watchdog or polling) is in use; if disabled, log that too

## 5. omctl CLI

- [x] 5.1 Create `omctl.py` in the project root; implement `push` subcommand using `argparse` with flags `--directory`/`-d` (default `./demo_templates`), `--url`/`-u` (default `http://localhost:9998`), `--set-key`/`-k`; recursively load all `.yaml`/`.yml` files from the directory; POST combined YAML to the correct endpoint with `Content-Type: application/yaml`; exit 0 on 2xx, print error to stderr and exit non-zero otherwise
- [x] 5.2 In `omctl.py`, implement `delete` subcommand with flags `--url`/`-u` (default `http://localhost:9998`) and `--set-key`/`-k` (required); send `DELETE {url}/api/v1/template_sets/{set-key}`; exit 0 on 204, print error and exit non-zero otherwise
- [x] 5.3 Add `omctl` script entry point to `pyproject.toml` under `[project.scripts]`

## 6. Tests

- [x] 6.1 Add tests for `reply_http` binary file: response body equals raw file bytes, `Content-Length` is correct, `Content-Disposition` present when `binary_file_name` set, non-empty `body` wins over binary file
- [x] 6.2 Add tests for `send_http` binary: POST uses multipart with correct field name and filename, non-POST sends raw binary body, `binary_file_name` used as multipart filename, basename fallback
- [x] 6.3 Add tests for CORS: headers present on matched responses, headers present on 404, mock-defined CORS value overrides middleware, unmatched OPTIONS returns 200 with CORS headers, CORS disabled leaves OPTIONS as 404
- [x] 6.4 Add tests for hot reload: new file picked up, edited file reflected, deleted file removed, reload failure preserves previous state
- [x] 6.5 Add tests for `omctl`: push without set-key POSTs to `/api/v1/templates`, push with set-key POSTs to `/api/v1/template_sets/{key}`, delete sends DELETE and exits 0, missing set-key exits non-zero, server error exits non-zero
