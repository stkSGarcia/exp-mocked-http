## Context

The server is currently a single Python entry point, `hmock.py`, that loads YAML behaviors from `HM_TEMPLATES_DIR`, validates them, matches HTTP requests, and renders conditions, response headers, and response bodies through a Jinja-backed compatibility layer for the checkpoint template syntax. Checkpoint 2 extends that same surface with additional helper functions, file-backed response bodies, and a reaffirmed requirement that headers are templates.

The important constraint is that file-backed bodies are resolved relative to `HM_TEMPLATES_DIR` and use a stable snapshot for the loaded configuration. That points to loading file contents during configuration load/behavior assembly, then rendering the captured text at request time.

## Goals / Non-Goals

**Goals:**

- Add the requested helper functions to every template context used by conditions, response bodies, file-backed response bodies, and response headers.
- Preserve existing template syntax and helper behavior.
- Load `reply_http.body_from_file` content relative to `HM_TEMPLATES_DIR` and keep the loaded content stable until the configuration is reloaded.
- Keep response body precedence explicit: non-empty inline `body` wins over `body_from_file`; `body_from_file` is used only when inline `body` is empty or missing.
- Ensure invalid JSON for `gJsonPath` is surfaced as a render error while empty data and missing matches return `""` where required.

**Non-Goals:**

- Hot reloading template files after startup.
- Supporting every possible XPath or JSONPath dialect feature beyond the checkpoint examples and required behavior.
- Adding support for file-backed headers or non-HTTP protocols.

## Decisions

- Extend the current Jinja environment with helper functions instead of replacing the renderer.

  The existing code already rewrites the checkpoint template syntax into Jinja syntax and registers functions as both globals and filters. Adding the new helpers there keeps conditions, headers, inline bodies, and file-backed bodies consistent. Replacing the renderer would add risk without changing the user-facing language.

- Implement `body_from_file` snapshotting during behavior loading.

  `load_behaviors(templates_dir)` has the templates root available and is already the boundary between files on disk and active behavior configuration. During validation or assembly, `reply_http.body_from_file` can be resolved against the root, read as UTF-8 text, and stored in a private field such as `_body_from_file_content`. `build_http_response` then renders that stored text at request time.

- Keep path resolution confined to `HM_TEMPLATES_DIR`.

  Resolve `body_from_file` by joining it to the templates root and normalizing the result. Reject paths that resolve outside the templates root. This preserves the "relative to `HM_TEMPLATES_DIR`" contract and avoids accidental reads of arbitrary files.

- Implement helper functions with standard-library tools first.

  `uuidv5`, HMAC-SHA256, HTML escaping, regex helpers, and XML XPath can be covered by `uuid`, `hmac`/`hashlib`, `html`, `re`, and `xml.etree.ElementTree`. `gJsonPath` can be implemented as a small dot-notation walker for fields, indexes, wildcards, and counts. `jsonPath` can parse JSON and use a small XPath-style selector for direct fields and recursive `//name` searches. If later checkpoints require broader dialect support, that can become a dependency decision.

- Treat helper failures consistently with template render failures.

  Helpers that are specified to return `""` for empty input or missing matches should do so. Helpers that encounter invalid structured data where the checkpoint says to error, such as `gJsonPath` on invalid JSON, should raise an exception that `render()` wraps in `TemplateRenderError`.

## Risks / Trade-offs

- Limited selector dialect support could miss unlisted JSONPath/XPath variants. Mitigation: cover every syntax explicitly listed in checkpoint 2 with focused tests and keep helper internals small enough to extend.
- Snapshotting file contents at load time means file edits are not visible until restart or reload. Mitigation: this is required behavior; tests should assert that the response uses the loaded snapshot.
- Path normalization can be platform-sensitive. Mitigation: use `Path.resolve()` for both root and candidate path and assert the candidate is within the root before reading.
- Helper return types vary between strings, lists, and booleans. Mitigation: rely on the existing template finalizer and stringification path, and add tests for list helpers used through `index`, loops, or direct output.
