## Context

`hmock.py` currently owns configuration loading, mock definition validation, runtime state, template rendering, HTTP request matching, and action execution. Broker support needs to integrate with those same paths so Kafka and AMQP mocks inherit existing behavior for values, named templates, `redisDo`, file-backed payload loading, action ordering, persisted template sets, and hot reload.

## Related Work

**`template-rendering/add-http-yaml-mock-server`**: Conditions and rendered outputs share one request template context — informs broker message context construction because Kafka and AMQP conditions and publish payloads must render through one message-specific context.

**`mock-definition-loading/add-http-yaml-mock-server`**: Runtime configuration is read from environment variables with documented defaults — informs broker configuration parsing because Kafka and AMQP should be disabled unless explicitly enabled and should keep predictable defaults.

**`template-rendering/add-stateful-actions`**: Template helpers are available in every expression context — informs use of `build_template_context` or a compatible context builder because broker conditions and publish actions must keep `redisDo`, named templates, and helper functions available.

**`http-behavior-mocking/add-template-helpers-file-backed-bodies`**: File-backed HTTP response bodies render from loaded file content — informs `publish_kafka.payload_from_file` and `publish_amqp.payload_from_file` because broker payloads should snapshot and render files like existing body fields.

**`http-behavior-mocking/add-stateful-actions`**: A selected behavior executes its actions in declared order — informs broker dispatch because each matching broker behavior should reuse the current action executor ordering while changing only the selection model to allow multiple matches.

**`mock-definition-loading/add-template-helpers-file-backed-bodies`**: File-backed body fields are loaded during mock definition loading — informs validation-time payload file resolution because missing or out-of-root broker payload files should fail before consumption starts.

**`http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`**: Stable `order` sorting determines action execution — informs broker behavior execution because Kafka and AMQP should execute matching behaviors in loaded order, while each behavior's actions keep stable sorted order.

## Goals / Non-Goals

**Goals:**

- Add Kafka and AMQP configuration fields to `Config` and `load_config`.
- Extend validated behavior models so one behavior may target HTTP, Kafka, or AMQP expectations.
- Reuse template rendering, values, named templates, Redis-backed helpers, file path safety checks, and action ordering for broker messages.
- Start and stop broker consumers alongside the HTTP server when the relevant broker feature is enabled.
- Support testable broker adapters so unit tests can verify matching and publish behavior without requiring live Kafka or RabbitMQ for every case.

**Non-Goals:**

- Provide a full broker management UI through the admin HTTP API.
- Implement broker-specific serialization beyond string payloads.
- Add exactly-once delivery guarantees, retry policies for publish actions, or dead-letter handling.
- Change existing HTTP first-match behavior.

## Decisions

### Broker Configuration Is Resolved Into Explicit Client Settings

Add Kafka and AMQP fields to `Config`, including resolved Kafka producer and consumer settings. Kafka override/fallback and SASL enablement should be computed during `load_config` so runtime code receives explicit client settings instead of repeatedly reading environment variables. This follows the current configuration pattern _(see `mock-definition-loading/add-http-yaml-mock-server`)_.

Alternative considered: defer override resolution to each adapter. That would scatter configuration semantics across startup and publish paths, making tests harder to reason about.

### Keep `Behavior` as the Shared Validated Runtime Object

Extend `Behavior` with optional HTTP, Kafka, and AMQP expectation data rather than creating separate behavior classes. `validate_behavior`, `_validate_abstract_definition`, inheritance merging, and `build_behavior_set` already provide ordering, values, templates, duplicate handling, and file snapshotting; broker mocks should pass through that same pipeline _(see `mock-definition-loading/add-http-yaml-mock-server`)_.

Alternative considered: introduce separate KafkaBehavior and AMQPBehavior classes. That would reduce optional fields but duplicate inheritance and validation behavior.

### Reuse Action Execution With Message-Specific Contexts

Introduce a shared action runner that accepts a prepared template context and optional response capture. HTTP will keep using it to produce `reply_http`; Kafka and AMQP will use it for `redis`, `sleep`, `send_http`, `publish_kafka`, and `publish_amqp`, ignoring `reply_http` or rejecting it for broker-only behaviors depending on validation strictness. Broker contexts should expose `.KafkaTopic`/`.KafkaPayload` or `.AMQPExchange`/`.AMQPRoutingKey`/`.AMQPQueue`/`.AMQPPayload`, plus `.Values`, named templates, and `redisDo` _(see `template-rendering/add-http-yaml-mock-server` and `template-rendering/add-stateful-actions`)_.

Alternative considered: duplicate execution loops for broker consumers. That would risk diverging action ordering and template rendering behavior.

### Broker Matching Uses Multi-Match Dispatch

HTTP matching remains first-match. Kafka and AMQP dispatchers scan loaded behaviors in order, evaluate broker-specific fields and `condition`, and execute every matching behavior. This implements asynchronous fan-out semantics while preserving the existing per-behavior action order _(see `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`)_.

Alternative considered: use the HTTP first-match model for brokers. That would make it harder to model event fan-out and is explicitly different from the checkpoint requirement.

### File-Backed Publish Payloads Snapshot During Validation

`publish_kafka.payload_from_file` and `publish_amqp.payload_from_file` should use `_resolve_body_file` with field-specific names and store loaded content on the action payload, mirroring `reply_http.body_from_file` and `send_http.body_from_file` _(see `mock-definition-loading/add-template-helpers-file-backed-bodies`)_.

Alternative considered: load broker payload files at publish time. That would make behavior depend on file changes after validation and diverge from existing snapshot semantics.

### Broker Adapters Own External Libraries

Add small Kafka and AMQP adapter layers with common `start()`, `stop()`, and `publish(...)` surfaces. Production adapters can wrap the selected client libraries, while tests can use in-memory fakes. `main()` should start adapters after state initialization and stop them in `finally`; reload paths should refresh subscriptions and AMQP bindings based on the current behavior set.

Alternative considered: call client libraries directly from action and startup code. Adapter boundaries keep optional dependencies and live-broker concerns contained.

## Risks / Trade-offs

- [Optional dependency availability] Broker libraries may not be installed in minimal deployments → keep broker code dormant when disabled and raise a clear startup error only when enabled without the required dependency.
- [Consumer lifecycle complexity] Hot reload can change subscribed topics and AMQP bindings while consumers are running → centralize resubscribe/rebind work in broker managers and call it after `HMockRuntimeState.reload`.
- [Duplicate side effects] Multi-match broker dispatch can intentionally execute several behaviors for one message → log matched behavior keys and preserve loaded order to make side effects inspectable.
- [Reconnect loops] AMQP reconnect can spin during prolonged outages → use bounded sleep/backoff and log reconnect attempts at warning level.
- [Live broker test cost] Integration tests may be slow or unavailable in CI → cover matching, config, validation, and publish rendering with fake adapters, and keep live broker tests opt-in.

## Migration Plan

1. Add config fields with disabled defaults so existing deployments keep current HTTP-only behavior.
2. Extend schema validation and action execution while preserving existing HTTP tests.
3. Add broker managers and start them only when `HM_KAFKA_ENABLED` or `HM_AMQP_ENABLED` is true.
4. Document the new environment variables and mock fields in examples or README material if the project has user-facing docs.

Rollback is disabling `HM_KAFKA_ENABLED` and `HM_AMQP_ENABLED`, or reverting the broker adapter startup path while leaving HTTP behavior intact.

## Open Questions

- Which concrete Python client libraries should be used for Kafka and AMQP in this repository's dependency model?
- Should `reply_http` be rejected in broker-only behaviors, ignored, or allowed as a no-op for inheritance reuse?
- Should Kafka consumer group IDs be configurable separately from `HM_KAFKA_CLIENT_ID`?
