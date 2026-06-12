## Context

The server currently compiles filesystem, persisted base, and named-set definitions into a `RuntimeState`, then atomically exposes that state through `install_runtime()` and `runtime_snapshot()`. Admin mutations already rebuild under `_MUTATION_LOCK`; text file-backed bodies are resolved and captured while actions are prepared. Mock and admin HTTP handling, outbound HTTP actions, and packaging all use the Python standard library plus PyYAML and Jinja.

This change crosses configuration, runtime lifecycle, response handling, action compilation, outbound encoding, admin payload parsing, and command packaging. It must preserve request-level runtime consistency and existing JSON/admin behavior.

## Related Work

> **`admin-template-management/add-admin-api-template-persistence`**: Defines independent admin endpoints, persisted collections, atomic mutation, and named-set deletion — informs reuse of the existing routes and mutation lock because the CLI is a client of that contract rather than a second management path.

> **`http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`**: Defines compiled behaviors, action execution, and ordered runtime assembly — informs atomic hot-reload installation because each request must observe one complete compiled runtime.

> **`http-yaml-mock-server/add-template-helpers-file-backed-bodies`**: Defines templates-directory path confinement, load-time validation, body precedence, and stable text snapshots — informs binary snapshot preparation because binary fixtures require the same lifecycle without decoding or rendering.

## Goals / Non-Goals

**Goals:**

- Make filesystem changes visible automatically when enabled while retaining the last valid runtime during failed reloads.
- Apply CORS consistently to all mock-server responses without overriding mock-defined values.
- Support byte-preserving reply and outbound payloads with deterministic multipart encoding.
- Provide a testable `omctl` client over the existing admin endpoints.
- Keep implementation compatible with Python 3.11 and the existing dependency set.

**Non-Goals:**

- Add filesystem hot reload to persisted Redis data independently of admin mutations.
- Add configurable CORS origins, methods, headers, or credential values.
- Stream large binary files; snapshots remain in memory with the compiled runtime.
- Add authentication, retries, synchronization, or template diffing to `omctl`.
- Change admin endpoint paths or persisted Redis formats.

## Decisions

### Poll the templates tree and atomically swap runtimes

Add `templates_dir_hot_reload` and `cors_enabled` to `Config`. When hot reload is enabled, `main()` starts a daemon reloader with a stop event. The reloader periodically fingerprints regular files under the templates directory using relative path, modification time, size, and a content digest. A changed fingerprint triggers `build_runtime()` under `_MUTATION_LOCK`; only a successful build is passed to `install_runtime()`. The reloader records failed fingerprints so an unchanged invalid tree does not cause repeated rebuilds and logs, while the last valid runtime remains installed. _(see `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`)_

The fingerprint covers the whole templates tree, not only YAML files, so edits to referenced binary or text fixtures also rebuild their snapshots. Admin mutations continue to call the existing synchronous rebuild path regardless of the hot-reload setting. When hot reload is disabled, startup and successful admin mutations are the reload boundaries.

Alternative considered: check for changes at the start of every request. That avoids a thread but couples reload latency and filesystem traversal cost to request traffic, and filesystem changes would not be reflected until a mock request arrived.

### Merge CORS defaults into the completed response

Keep normal matching and action execution unchanged. After a response is selected, apply CORS defaults only when `config.cors_enabled` is true. Header existence is tested case-insensitively so any value produced by `reply_http` wins. If an `OPTIONS` request has no match, select an empty `200` response instead of the normal `404`, then apply the same defaults.

Attach `Config` to the mock `ThreadingHTTPServer` so each handler can use immutable server configuration without new process-wide flags. Applying CORS to the final `Response` naturally covers matched responses, misses, and empty preflights.

Alternative considered: emit CORS headers directly in `send_response()`. That function is shared with the admin server, where global mock CORS must not apply, and it has less context for unmatched `OPTIONS` behavior.

### Prepare binary snapshots alongside text file bodies

Extend `_prepare_actions()` with a binary preparation helper that uses the existing templates-directory confinement rule and stores private byte and source-name fields in compiled action dictionaries. Inline non-empty `body` remains the first choice. Otherwise, response and outbound builders select the binary snapshot before the existing text-file snapshot. _(see `http-yaml-mock-server/add-template-helpers-file-backed-bodies`)_

`build_http_response()` bypasses Jinja for selected binary bytes, computes byte length directly, and adds the optional inline filename header. Internal snapshot fields remain absent from `RuntimeState.definitions`, so admin listing and persisted definitions retain their public YAML shape.

Alternative considered: read binary files during each request. That would violate stable loaded-configuration semantics, expose partial writes, and make disabled hot reload ineffective for binary fixtures.

### Encode POST binary actions as one-part multipart requests

Add a focused multipart encoder that generates a boundary and one `file` part. `binary_file_name` supplies the filename; otherwise the basename of `body_from_binary_file` is used. A configured `Content-Type` action header becomes the file-part media type and is removed from the user header map before the generated `multipart/form-data; boundary=...` envelope header is installed. For non-`POST` methods, the bytes are passed directly to `urllib.request.Request`.

Alternative considered: add a multipart dependency. A one-part encoder is small, deterministic, and avoids expanding the project dependency surface.

### Add a separate omctl module and YAML-aware admin parsing

Create `omctl.py` with `argparse` subcommands and expose it through `[project.scripts]`. `push` reuses recursive YAML discovery semantics, parses every file before network activity, combines object/list documents, serializes one YAML array, URL-encodes optional set keys, and expects the existing successful `200` response. `delete` requires a set key and expects `204`. Unexpected statuses and transport or parse failures produce a concise stderr error and non-zero exit code. _(see `admin-template-management/add-admin-api-template-persistence`)_

Rename the admin body reader around definitions rather than JSON and select `yaml.safe_load()` for `application/yaml`/`application/x-yaml`, while retaining JSON parsing for existing clients. Both formats pass through `normalize_definition_payload()` and the existing build-before-persist mutation flow.

Alternative considered: emit JSON while labeling it `application/yaml`, because JSON is YAML-compatible. Parsing and emitting actual YAML better matches the CLI contract and makes the admin media-type behavior explicit.

## Risks / Trade-offs

- [Large template trees make polling expensive] -> Use a modest interval and only trigger YAML parsing and runtime compilation when the content fingerprint changes.
- [Some filesystems preserve timestamps for rapid same-size edits] -> Include a content digest so creations, edits, deletions, and fixture rewrites are detected consistently.
- [Reload races with admin mutations] -> Serialize both rebuild paths with `_MUTATION_LOCK` and install only complete `RuntimeState` objects.
- [Binary snapshots increase memory use] -> Preserve the checkpoint's stable-snapshot requirement and document that files are loaded once per runtime.
- [Multipart header interpretation differs from raw requests] -> Treat configured `Content-Type` as the file-part type only for binary `POST`; always generate a valid multipart envelope header.
- [YAML accepts more scalar forms than JSON] -> Continue enforcing object/list shape and existing definition validation before persistence.

## Migration Plan

1. Add configuration fields with backward-compatible defaults: hot reload enabled and CORS disabled.
2. Add reloader and CORS behavior without changing existing persisted data.
3. Add binary fields as optional action properties; existing text and inline bodies retain precedence and behavior.
4. Add YAML admin parsing while preserving JSON clients.
5. Publish the `omctl` console script with the project package.

Rollback removes the reloader, new optional fields, YAML media handling, and script entry point; no data migration is required because persisted definitions remain compatible dictionaries.

## Open Questions

None.
