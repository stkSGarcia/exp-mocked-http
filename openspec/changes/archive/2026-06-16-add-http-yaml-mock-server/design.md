## Context

This repository is starting from an OpenSpec planning structure with no existing implementation files. The requested deliverable is a single HTTP-only server entry point, `hmock.py`, run with `uv run --project /app hmock.py`.

The server must discover YAML mock definitions from the filesystem, validate and order behavior records, match incoming HTTP requests, render template expressions, execute actions, and emit JSON logs. Although the product direction is multi-protocol, this change is intentionally scoped to HTTP behavior mocking.

## Goals / Non-Goals

**Goals:**
- Provide a self-contained Python HTTP mock server that runs from `hmock.py`.
- Keep behavior definitions declarative and loadable from recursive YAML template directories.
- Implement deterministic request matching, condition evaluation, action execution, response rendering, and structured logs.
- Make the design testable through unit-level parser/renderer/matcher tests and end-to-end HTTP tests.

**Non-Goals:**
- Add non-HTTP protocols in this revision.
- Provide a management API, hot reload, UI, persistence, or distributed coordination.
- Implement every edge case of Go `text/template`; only the requested syntax and functions are in scope.

## Decisions

1. **Use Python standard HTTP primitives with small internal components.**

   Implement `hmock.py` with a standard-library HTTP server handler and split logic into internal classes/functions in the same file for this revision: configuration, mock loading, template rendering, request matching, action execution, and logging.

   Alternative considered: introduce a web framework. A framework would add routing and middleware conveniences, but the required matching semantics are custom and the deliverable is a single script.

2. **Normalize loaded YAML into behavior records before serving.**

   The loader will recursively scan `HM_TEMPLATES_DIR`, parse `.yaml` and `.yml` files, flatten their top-level lists into a single ordered stream, validate each behavior, default `kind` to `Behavior`, and collapse duplicate keys so the last loaded definition wins while preserving final evaluation order.

   Alternative considered: validate lazily during request handling. Eager validation gives earlier failures and keeps request-time code smaller.

3. **Compile path patterns into matchers.**

   HTTP paths from behavior definitions will be compiled into segment-based regular expressions where `:name` captures one path segment. Matching ignores the query string for route comparison while the full path and raw query remain available in template context.

   Alternative considered: use a router library. A local compiler makes named parameter behavior explicit and avoids changing the requested path semantics.

4. **Evaluate templates through a constrained Go-template-like interpreter.**

   The renderer will support the requested delimiters, variable access, pipelines, conditionals, ranges, assignments, raw strings, whitespace trimming, undefined-variable errors, and the specified functions. It will translate request state into a strict context with header accessors and path parameter accessors.

   Alternative considered: reuse Jinja. Jinja syntax differs from the requested templates, especially pipelines and dotted variables, so a compatibility layer would be more confusing than a constrained interpreter.

5. **Treat action execution as a single-response pipeline.**

   Actions run in order. `sleep` pauses execution and `reply_http` commits the HTTP response. Validation rejects more than one `reply_http` action so request handling never has to resolve competing responses.

   Alternative considered: allow multiple replies and use the first. Rejecting invalid mocks is clearer and matches the schema rule.

## Risks / Trade-offs

- Template compatibility gaps -> Add focused tests for every supported syntax form and function from the checkpoint.
- Recursive file ordering can vary by filesystem -> Sort discovered file paths before loading so evaluation order is deterministic.
- Duplicate key handling can make earlier definitions disappear -> Log a warning with both the duplicate key and replacement behavior.
- Long sleeps can block a worker -> Use a threaded HTTP server so one delayed mock does not stall unrelated requests.
- Render failures could leak internals -> Treat condition render failures as non-matches and response render failures as server errors with structured logs.

## Migration Plan

This is a new capability with no existing runtime migration. Implementation can land as `hmock.py` plus tests, and rollback is removing that file and related tests.

## Open Questions

None for this proposal.
