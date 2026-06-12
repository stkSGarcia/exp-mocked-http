## Why

The mock server cannot currently observe template-directory changes without a restart, serve browser clients with a global CORS policy, transport binary fixtures, or manage remote templates from a command-line client. These gaps make local integration workflows slower and prevent several common HTTP test cases.

## Related Work

### Related Changes

- `add-admin-api-template-persistence` introduced persistent base templates, named template sets, and immediate mutation visibility through the admin server. This change complements that work with an `omctl` client and preserves its reload behavior while adding filesystem hot reload.
- `add-template-helpers-file-backed-bodies` introduced stable text file-backed bodies. This change extends the same load-time snapshot model to binary reply and outbound request bodies.
- `add-stateful-actions-redis-http-side-effects` introduced outbound `send_http` actions. This change broadens those actions to support binary multipart and raw request payloads.

### Related Specs

- `admin-template-management/add-admin-api-template-persistence` implements the admin template endpoints and named-set deletion semantics. The new CLI reuses those endpoints, payload models, and idempotent `204 No Content` deletion behavior.
- `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering` defines behavior actions and runtime assembly. Hot reload and binary snapshots build on that compiled runtime model.
- `http-yaml-mock-server/add-template-helpers-file-backed-bodies` implements text file-backed response and outbound bodies. Binary payload support adapts its directory confinement, load-time validation, precedence, and snapshot rules.

## What Changes

- Add `HM_TEMPLATES_DIR_HOT_RELOAD`, defaulting to `true`, to control automatic visibility of template-directory creations, edits, and deletions.
- Add `HM_CORS_ENABLED`, defaulting to `false`, to apply global CORS headers and answer unmatched `OPTIONS` requests as empty `200 OK` preflights while preserving explicit mock behavior and mock-defined header values.
- Add `body_from_binary_file` and optional `binary_file_name` fields to `reply_http` and `send_http`.
- Return binary reply bytes without template rendering, with an accurate `Content-Length` and optional inline `Content-Disposition`.
- Send binary `POST` actions as multipart form data under field `file`; send binary data for other methods as the raw request body.
- Add an `omctl` command-line entry point with `push` and `delete` subcommands for the existing admin template API.
- Accept `application/yaml` template payloads on the admin API endpoints used by `omctl`.

## Capabilities

### New Capabilities

- `template-hot-reload`: Configuration and runtime rules for observing or deferring template-directory filesystem changes.
- `cors-response-policy`: Global mock-server CORS headers, unmatched preflight handling, and mock-header precedence.
- `binary-http-payloads`: Stable binary file snapshots for `reply_http` and `send_http`, including multipart upload behavior.
- `admin-cli`: `omctl push` and `omctl delete` commands for remote admin template management.

### Modified Capabilities

None.

## Impact

- `hmock.py`: configuration, runtime reload checks, response middleware, binary file loading, outbound request encoding, and CLI implementation or shared helpers.
- `test_hmock.py`: unit and integration coverage for configuration defaults, reload boundaries, CORS matching, binary payloads, multipart encoding, and CLI HTTP requests.
- `pyproject.toml`: expose the `omctl` console script.
- Runtime interfaces: two new environment variables and four optional YAML action fields.
- Admin API: no endpoint changes; template and template-set `POST` routes additionally accept `application/yaml` payloads for `omctl`.
