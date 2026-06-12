## Context

The server is currently a single Python entry point, `hmock.py`, that loads YAML behaviors, validates them, matches requests, renders templates through the existing compatibility layer, and executes ordered actions such as `sleep` and `reply_http`. Checkpoint 3 extends that same declarative action pipeline with shared state through Redis semantics and outbound HTTP side effects.

The key constraint is that `redisDo` must be available anywhere templates are rendered, including conditions that run before an action list is selected. That makes Redis access part of the template environment rather than only a behavior action concern. The second constraint is that outbound HTTP failures must not alter mock execution or the inbound response, so side effects need to be isolated from response generation.

## Goals / Non-Goals

**Goals:**

- Add Redis backend configuration with `memory` as the default and external Redis selected by `HM_REDIS_TYPE=redis`.
- Provide a Redis-compatible command surface for the checkpoint command set through both `redis` actions and `redisDo`.
- Make `redisDo` available to conditions, response bodies, response headers, and `redis` action item templates.
- Preserve ordered action execution when behaviors mix `redis`, `send_http`, `sleep`, and `reply_http`.
- Add `send_http` side effects with templated URL, headers, inline body, and file-backed body support.
- Ensure outbound HTTP failures are logged and do not fail the inbound mock request.

**Non-Goals:**

- Implementing the entire Redis protocol or every Redis command.
- Persisting the in-memory backend across process restarts.
- Retrying outbound HTTP requests or adding delivery guarantees.
- Blocking startup on the availability of an external Redis server beyond constructing the configured client.

## Decisions

- Introduce a small Redis backend interface with memory and external implementations.

  The memory backend should implement the checkpoint command set directly in Python data structures and return Redis-like values normalized by a shared formatter. The external backend should use a Redis client library for `HM_REDIS_TYPE=redis` and route commands through the same normalization path. This keeps template behavior consistent across backends while avoiding a network dependency for default local use.

- Initialize Redis access before behaviors are matched and expose it through the template environment.

  `redisDo` must work in conditions as well as actions and replies. The cleanest shape is a module-level or server-owned Redis backend initialized from `Config`, with `redisDo` registered as a template function/filter that parses the command string, executes it, and converts the result to the checkpoint string format.

- Parse Redis command strings with shell-like tokenization.

  Commands are rendered as template strings before execution. After rendering, use a tokenizer that supports quoted values so commands like `SET key "hello world"` and `HSET user name "Ada Lovelace"` are practical while keeping the command surface small and explicit.

- Extend `execute_actions` for side effects while keeping `reply_http` as the response boundary.

  `redis` actions execute each rendered command in order and continue. `send_http` actions render request fields, send the outbound request, log failures, and continue. `sleep` keeps its current pause behavior. `reply_http` still returns the inbound response and ends action processing.

- Reuse existing file snapshot semantics for `send_http.body_from_file`.

  The server already resolves `reply_http.body_from_file` relative to `HM_TEMPLATES_DIR` and snapshots file contents at load time. Applying the same preparation path to `send_http.body_from_file` avoids repeated disk reads and keeps file-backed behavior stable for a loaded configuration. If both `body` and `body_from_file` are present, use non-empty inline `body`; otherwise fall back to the file snapshot.

## Risks / Trade-offs

- External Redis behavior may differ subtly from the memory backend for edge cases outside the checkpoint command set. Mitigation: constrain accepted commands and normalize all return values through one formatter.
- Calling `redisDo` from conditions can mutate state before a behavior is selected. Mitigation: document and test that `redisDo` is a stateful template function available in conditions, matching checkpoint behavior.
- Synchronous outbound HTTP side effects can add latency before a response is generated. Mitigation: keep the implementation simple for checkpoint scope, add timeouts, and log failures without raising into the inbound response path.
- Redis command strings can be ambiguous without clear tokenization. Mitigation: use shell-like splitting and test quoted arguments for keys and values with spaces.
