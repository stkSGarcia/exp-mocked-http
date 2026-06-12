## Context

The repository currently contains the OpenSpec planning scaffold and checkpoint requirements, but no runnable mock server implementation. The first implementation target is a single Python entry point, `hmock.py`, that serves HTTP mocks from YAML behavior files. The server must be simple to run in the `/app` project context, environment-configurable, and deterministic in how it loads, validates, matches, renders, executes, and logs mock behavior.

## Goals / Non-Goals

**Goals:**

- Provide a self-contained HTTP mock server that loads behavior definitions from YAML files.
- Preserve behavior load order for matching while allowing duplicate keys to override earlier definitions.
- Implement path matching with `:param` captures, request-context template rendering, ordered actions, sleeps, and structured logs.
- Return precise HTTP defaults, especially unmatched `404 Not Found` responses and default `Content-Type` / `Content-Length` handling.
- Make failure modes predictable: invalid mocks fail validation, condition render errors skip that behavior, and unknown template variables are render errors.

**Non-Goals:**

- Implement non-HTTP protocols in this revision.
- Add a management API, live reload, persistence, or UI.
- Provide full Go `text/template` compatibility beyond the syntax and functions required by the checkpoint.
- Support multiple `reply_http` actions in a behavior.

## Decisions

- Implement the server as one `hmock.py` module with clear internal sections for configuration, loading, validation, template rendering, matching, action execution, and logging.
  - Rationale: the deliverable is a single entry point, and the initial scope is compact enough that a single file keeps deployment and review straightforward.
  - Alternative considered: a package layout with multiple modules. That can come later if the protocol surface grows.

- Use Python's standard HTTP server stack for the listener and request handling, with small adapters for request context and response emission.
  - Rationale: the required HTTP behavior is request/response oriented and does not require an async framework.
  - Alternative considered: FastAPI or Flask. Those add dependencies and routing behavior that the mock matcher must control itself.

- Parse YAML files into a list of behavior records, then resolve duplicate keys by removing the earlier active record and appending the last loaded definition at its load position.
  - Rationale: "last loaded mock wins" must coexist with ordered first-match evaluation. Keeping the final definition at its own load position makes active order match the surviving behavior definitions.
  - Alternative considered: append duplicates and skip older entries at match time. That is more error-prone and complicates reasoning about load order.

- Normalize HTTP methods to uppercase for matching while preserving request path and query string separately in the template context.
  - Rationale: HTTP method matching should be case-insensitive in practice, while templates need exact URL path and raw query data.
  - Alternative considered: exact method case matching. That would surprise users and does not add useful expressiveness.

- Convert `:param` path patterns to anchored regular expressions and expose captured values through URL/path context in addition to the required request URL fields.
  - Rationale: named captures are easiest to test and reuse during template rendering when they are stored in the request context.
  - Alternative considered: split-and-compare matching only. Regex compilation gives simpler support for exact segment capture and anchoring.

- Build a constrained template evaluator that supports the required delimiters, control structures, variables, pipelines, and function set, and treats undefined variables as render errors.
  - Rationale: conditions and responses depend on Go-template-like expressions. A constrained evaluator can target the required behavior without importing an unrelated templating language with incompatible semantics.
  - Alternative considered: Jinja2. Its syntax and undefined-variable behavior differ enough that compatibility shims would dominate the implementation.

- Execute actions sequentially, collecting the first `reply_http` response and applying `sleep` delays before later actions.
  - Rationale: ordered action execution is explicit in the checkpoint and validation guarantees no behavior has more than one HTTP reply.
  - Alternative considered: require `reply_http` to be the final action. The checkpoint does not impose that constraint.

## Risks / Trade-offs

- Template compatibility gaps -> Mitigate by covering every listed syntax form and function with focused tests and treating unsupported or malformed expressions as render errors.
- YAML file load order can vary across filesystems -> Mitigate by sorting discovered file paths before loading and preserving object order inside each YAML file.
- Duplicate-key ordering semantics can be misread -> Mitigate with tests that demonstrate the active behavior is the last loaded definition and warnings are emitted.
- Long `sleep` actions can block the simple HTTP worker -> Mitigate by using a threaded HTTP server so one delayed request does not block all other requests.
- Header casing and repeated request headers can be subtle -> Mitigate by wrapping request headers in a case-insensitive map that provides `.Get "Header-Name"` for templates.
