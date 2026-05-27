## Why

The mock HTTP server needs operational features for real-world use: developers need live template reloading during development, frontend teams need CORS headers to test cross-origin flows, and test suites need to serve binary files (images, PDFs, archives). The `omctl` CLI rounds this out by making remote admin operations scriptable without curl.

## What Changes

- Add hot reload: filesystem changes under the templates directory are picked up automatically when `HM_TEMPLATES_DIR_HOT_RELOAD=true` (default true)
- Add CORS support: when `HM_CORS_ENABLED=true`, inject permissive CORS headers on every response and handle unmatched OPTIONS as preflight
- Add binary file payloads: `reply_http` and `send_http` gain `body_from_binary_file` and `binary_file_name` fields
- Add `omctl` CLI: `omctl push` uploads a local directory of YAML templates to the admin API; `omctl delete` removes a named template set

## Capabilities

### New Capabilities

- `hot-reload`: Automatic filesystem watching to reload templates without server restart
- `cors`: CORS header middleware and preflight handling on the mock HTTP server
- `binary-payloads`: Binary file body support for `reply_http` responses and `send_http` outbound requests
- `omctl`: CLI tool for remote admin operations (`push`, `delete`)

### Modified Capabilities

- `http-mock-server`: Response pipeline extended with CORS middleware and binary body support
- `send-http`: `send_http` action gains binary file upload support

## Impact

- `hmock.py`: template watcher thread, CORS middleware, binary body loading for reply and send
- `pyproject.toml` / packaging: new `omctl` entry point script
- `templates/` schema: two new fields on `reply_http` and `send_http` blocks
- Admin API (`admin-api` spec): no behavior change, but `omctl push/delete` adds a CLI consumer
- New dependency: filesystem watch library (e.g., `watchdog`) or polling loop for hot reload
