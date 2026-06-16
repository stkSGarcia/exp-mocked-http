## Context

The runtime currently lives mostly in `hmock.py`: `load_config` builds environment configuration, `_validate_actions` validates action payloads and snapshots file-backed content, `validate_behavior` turns loaded definitions into `Behavior` objects, and `execute_actions` runs stable ordered actions. HTTP request matching is first-match, but Kafka and AMQP require message-triggered dispatch that can execute every matching behavior for one consumed message.

Broker support crosses configuration, schema validation, runtime workers, action execution, and tests. It also introduces external broker client libraries, so broker clients need thin adapters that can be replaced by fakes in `tests/test_hmock.py`.

## Related Work

> **`mock-definition-loading/add-template-helpers-file-backed-bodies`**: File-backed response body loading snapshots content from `HM_TEMPLATES_DIR` during mock definition loading — informs broker `payload_from_file` loading because publish payloads need the same path safety and snapshot semantics.

> **`http-behavior-mocking/add-stateful-actions`**: Action execution runs behavior actions in declared order while preserving failure isolation for side effects — informs broker publish action integration because publish actions should fit existing ordered action execution.

> **`http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`**: Action execution uses stable ascending `order` across inherited and declared actions — informs broker action sorting because new publish actions should not introduce a separate ordering model.

## Goals / Non-Goals

**Goals:**

- Add opt-in Kafka and AMQP configuration with documented defaults and side-specific Kafka overrides.
- Extend loaded behavior validation for `expect.kafka`, `expect.amqp`, `publish_kafka`, and `publish_amqp`.
- Reuse file-backed loading, template rendering, values, named templates, Redis template helper, and action ordering.
- Run Kafka and AMQP consumers in background worker threads that dispatch matching behaviors in loaded order.
- Provide broker client adapter interfaces so unit tests can cover matching, rendering, publish, reconnect, and resource setup without live brokers.

**Non-Goals:**

- Do not replace the HTTP server architecture or introduce an async application framework.
- Do not add binary broker payload handling unless a later spec requires it.
- Do not provide broker admin APIs beyond using already loaded runtime definitions.
- Do not make Kafka or AMQP connections when the corresponding enable flag is false.

## Decisions

### Broker Configuration Model

Extend `Config` with Kafka and AMQP fields and keep parsing inside `load_config`. Add a helper that resolves Kafka producer and consumer endpoints from shared defaults plus side-specific overrides after reading env vars. SASL is enabled per side only after fallback resolution and only when both resolved username and password are non-empty.

Alternative considered: parse broker env vars inside broker adapters. Keeping parsing in `Config` matches the existing Redis and HTTP configuration pattern and makes defaults testable without constructing external clients _(see `mock-definition-loading/add-template-helpers-file-backed-bodies`)_.

### Behavior Shape

Extend `Behavior` to carry optional Kafka and AMQP expectation data in addition to the existing HTTP method/path fields. For HTTP-only behaviors, keep the current method/path requirements. For broker-triggered behaviors, require the relevant broker expectation fields and allow no `expect.http`.

Alternative considered: create separate behavior classes per transport. A single behavior model keeps inheritance, values, templates, loaded order, and action sorting shared across transports.

### Broker Client Adapters

Add small Kafka and AMQP adapter classes around the chosen libraries and define simple internal protocols:

- Kafka producer: `publish(topic, payload)`.
- Kafka consumer worker: subscribe to referenced topics and pass `(topic, payload)` messages to dispatcher callbacks.
- AMQP client: ensure exchange/queue/binding, publish, and consume queue messages with reconnect.

The runtime should accept injected adapters for tests. Production adapter construction happens only when enabled flags are true.

Alternative considered: direct library calls inside matching and action execution. Adapters keep external dependency behavior isolated and make reconnect and publish failure paths testable.

### Dispatch Semantics

Add broker dispatch functions that build transport-specific template contexts, evaluate conditions, and execute every matching behavior in loaded order. Kafka dispatch matches topic. AMQP dispatch matches exchange, routing key, and effective queue. This differs intentionally from HTTP first-match routing because broker specs require all matching behaviors to execute.

Alternative considered: reuse `find_behavior`. That would preserve HTTP first-match behavior but would violate Kafka and AMQP all-match requirements.

### Action Execution

Extend `_validate_actions` and `execute_actions` with `publish_kafka` and `publish_amqp`. Payload rendering uses the same template engine and context as the triggering behavior. `payload_from_file` content is stored during load using the same path safety and snapshot behavior as `reply_http.body_from_file` and `send_http.body_from_file` _(see `mock-definition-loading/add-template-helpers-file-backed-bodies`)_. Broker publish actions participate in the existing stable action sort _(see `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`)_.

Alternative considered: execute publish actions outside `execute_actions`. That would duplicate rendering, error handling, and order semantics.

### Worker Lifecycle

Start broker worker threads from the same startup path that creates `HMockRuntimeState` and `HMockHTTPServer`. Workers read `state.get_behaviors()` before dispatch so hot reload and admin-managed definitions are reflected. AMQP workers should recreate connection resources after transient disconnects before resuming consumption.

Alternative considered: bind worker subscriptions to a static behavior snapshot. That would simplify workers but would ignore hot reload and admin API changes.

## Risks / Trade-offs

- External client dependencies may behave differently across broker versions -> wrap them behind narrow adapters and test runtime logic with fakes.
- Background workers can outlive test or server shutdown -> add explicit stop events and join paths in server shutdown tests.
- Hot reload can change topics or AMQP bindings while workers are active -> periodically refresh subscriptions or restart worker subscriptions when the behavior signature changes.
- Publish failures from broker actions can obscure HTTP replies or other actions -> log failures and continue action execution unless validation fails before runtime, matching existing side-effect action behavior.
- AMQP reconnect loops can spin under persistent failure -> use bounded backoff and log retry attempts.

## Migration Plan

1. Add config fields and validation while defaulting Kafka and AMQP to disabled.
2. Add broker action and expectation parsing with unit tests.
3. Add fake-backed dispatch and publish tests before introducing production adapters.
4. Add production adapters and startup wiring behind enable flags.
5. Roll back by setting `HM_KAFKA_ENABLED=false` and `HM_AMQP_ENABLED=false`; disabled broker paths should create no external connections.

## Open Questions

- Which Kafka Python library should be used in this environment: `kafka-python`, `confluent-kafka`, or another dependency already acceptable for the project?
- Should broker publish failures be strictly logged-and-continued for all trigger types, or should broker-triggered behaviors expose a dead-letter/error callback later?
