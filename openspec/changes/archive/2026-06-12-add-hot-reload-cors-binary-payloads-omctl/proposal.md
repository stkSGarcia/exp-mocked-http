## Why

The mock server needs to support faster local template iteration, browser-facing mock use cases, binary fixtures, and remote template administration from a developer workstation. These capabilities remove restart loops and manual admin API calls while preserving deterministic loaded mock behavior.

## What Changes

- Add configurable filesystem hot reload for the templates directory, enabled by default.
- Add optional global CORS response handling on the mock HTTP server, including unmatched `OPTIONS` preflight responses.
- Add binary file-backed payload support to `reply_http` and `send_http` actions.
- Add an `omctl` command-line tool for pushing YAML templates to the admin API and deleting named template sets.

## Capabilities

### New Capabilities
- `admin-cli`: Remote admin CLI behavior for uploading local YAML templates and deleting named template sets.

### Modified Capabilities
- `mock-definition-loading`: Runtime configuration, filesystem reload visibility, and binary fixture snapshot validation change.
- `http-behavior-mocking`: Mock response CORS handling, binary `reply_http` payloads, and binary `send_http` behavior change.
- `admin-http-api`: Admin endpoints must accept YAML payloads from the CLI in addition to the existing JSON mock definition payloads.

## Impact

- Affects `hmock.py` configuration, template loading, active mock set refresh behavior, HTTP response middleware, and outbound HTTP action execution.
- Adds a new `omctl` CLI entry point/module.
- Extends tests around filesystem reloads, CORS headers and preflights, binary response/outbound bodies, YAML admin posts, and CLI request construction.
