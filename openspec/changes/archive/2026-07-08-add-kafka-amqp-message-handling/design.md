## Context

`hmock.py` currently loads YAML mock definitions, validates HTTP expectations and actions, serves HTTP requests through `HMockHTTPServer`, and executes actions synchronously in `execute_behavior`. Configuration is centralized in `Config` and `load_config`, file-backed payloads are resolved during validation, and tests in `tests/test_hmock.py` cover configuration defaults, schema validation, template context, action ordering, and server lifecycle.

This change adds broker-driven workflows without making Kafka or AMQP mandatory. Kafka and AMQP clients should be constructed only when their feature flag is enabled, and broker consumers should participate in the same registry, template rendering, Redis store, logging, and shutdown lifecycle as HTTP mocks.

## Related Work

**`mock-definition-loading/add-http-yaml-mock-server`**: Environment defaults and YAML loading shape this design's `Config` extension, broker feature flags, and validation-time discovery because broker mocks are loaded from the same definitions as HTTP mocks. _(see `mock-definition-loading/add-http-yaml-mock-server`)_

**`http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`**: Stable action ordering informs reusing sorted behavior actions for broker-triggered execution because Kafka and AMQP messages should preserve loaded-order behavior evaluation while executing all matches. _(see `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`)_

**`api-template-persistence/add-admin-api-template-storage`**: Persisted/admin-managed definitions inform using the existing `ActiveMockRegistry` as the source of truth because broker consumers must react to the same active definitions used by HTTP routes. _(see `api-template-persistence/add-admin-api-template-storage`)_

## Goals / Non-Goals

**Goals:**

- Add Kafka and AMQP configuration defaults and overrides to `Config` and `load_config`.
- Extend behavior parsing and validation to support `expect.kafka`, `expect.amqp`, `publish_kafka`, and `publish_amqp`.
- Execute broker-triggered actions with the same Redis store, template engine, values, reusable templates, and loaded action ordering used by HTTP behavior execution.
- Run optional broker consumers in background threads that start and stop with the main process.
- Keep unit tests deterministic by isolating broker adapters behind small interfaces that can be faked without external broker processes.

**Non-Goals:**

- Do not implement a full admin API redesign for broker state.
- Do not make Kafka or AMQP dependencies required when the corresponding feature is disabled.
- Do not add durable delivery guarantees beyond what the configured broker/client provides.
- Do not change HTTP behavior matching or the single selected HTTP response behavior.

## Decisions

### Configuration Model

Extend `Config` with broker-specific fields rather than passing raw environment dictionaries deeper into the runtime. Kafka should include shared defaults (`HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, shared SASL credentials, shared TLS) plus resolved producer and consumer settings. SASL enablement is computed per side after applying side-specific overrides and shared fallback values. AMQP should include `HM_AMQP_ENABLED` and `HM_AMQP_URL`.

Alternative considered: resolve all broker options at client construction time. Keeping resolution in config is easier to test and follows the existing `load_config` pattern. _(see `mock-definition-loading/add-http-yaml-mock-server`)_

### Behavior Shape

Refactor `Behavior` so the expectation can represent HTTP, Kafka, or AMQP without forcing broker definitions to provide HTTP method/path fields. A conservative approach is to add optional `http`, `kafka`, and `amqp` expectation dataclasses or dictionaries while preserving existing HTTP properties for compatibility inside `find_behavior`.

Validation should require exactly one supported expectation type on concrete broker behaviors, validate broker-specific fields, snapshot `payload_from_file` contents using the same path safety rules as `body_from_file`, and continue to sort actions by `order`.

Alternative considered: create separate `KafkaBehavior` and `AMQPBehavior` types. A single behavior model keeps inheritance, values, templates, actions, admin persistence, and loaded-order evaluation consistent.

### Broker Runtime

Introduce small broker service classes in `hmock.py` or narrowly scoped helper classes:

- `KafkaBrokerService`: watches active behaviors, subscribes to topics referenced by `expect.kafka`, consumes messages, builds Kafka context, finds all matching Kafka behaviors, and executes their actions.
- `AMQPBrokerService`: ensures exchange/queue/binding resources for `expect.amqp`, consumes messages, restores resources after reconnect, builds AMQP context, finds all matching AMQP behaviors, and executes their actions.

Each service should expose `start()` and `stop()` so `main()` can manage lifecycle alongside the HTTP and admin servers. The initial implementation can poll the existing `ActiveMockRegistry.behaviors()` before processing messages, matching the current hot-reload model without adding a registry callback system.

Alternative considered: embed broker loops inside `HMockHTTPServer`. Separate services make it possible to run broker handling without coupling it to request-handler internals.

### Broker Action Execution

Split action execution into a shared executor that accepts a prebuilt template context and supports action names common to HTTP and broker flows. HTTP execution can continue returning `ResponseInfo`, while broker execution should ignore `reply_http` and execute side-effect actions such as `sleep`, `redis`, `send_http`, `publish_kafka`, and `publish_amqp`.

Kafka contexts add `.KafkaTopic` and `.KafkaPayload`. AMQP contexts add `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, and `.AMQPPayload`. Condition evaluation should use the same template truthiness rules used by HTTP matching.

Alternative considered: duplicate action loops for each transport. A shared executor reduces drift for template rendering, Redis behavior, file-backed payloads, and action ordering. _(see `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`)_

### Optional Dependencies and Test Fakes

Delay importing Kafka and AMQP client libraries until the matching feature is enabled, and wrap them behind minimal producer/consumer interfaces. Tests should cover config, validation, matching, ordering, payload rendering, and reconnect/resource setup with fake broker clients. Integration tests against real brokers can be added later if dependencies and infrastructure are available.

Alternative considered: require real Kafka/RabbitMQ in the default test suite. That would make the core suite slower and less portable for this small repository.

## Risks / Trade-offs

- Broker libraries may not be installed in all environments -> Import them lazily only when enabled and raise clear validation/runtime errors when enabled but unavailable.
- Background consumers may outlive the HTTP server -> Give each service explicit `start()`/`stop()` and join worker threads during `main()` shutdown.
- Hot-reloaded mock definitions may change subscriptions or bindings -> Recompute topics/resources from the active registry in the broker services and avoid retaining stale behavior snapshots longer than a message-processing cycle.
- Broker messages can match many behaviors and run many side effects -> Preserve loaded-order execution and log matched behavior keys for observability.
- Reconnect loops can spin during broker outages -> Add bounded sleep/backoff between AMQP reconnect attempts and log warning entries.

## Migration Plan

Add the behavior schema and config fields first while keeping both broker feature flags disabled by default. Then add fake-client-backed unit tests, broker services, publish actions, and lifecycle wiring. Rollback is straightforward because the new runtime is inert unless `HM_KAFKA_ENABLED` or `HM_AMQP_ENABLED` is true.

## Open Questions

- Which concrete Python Kafka and AMQP client libraries should be used for implementation?
- Should broker consumers have explicit group/consumer-tag configuration beyond the checkpoint's listed environment variables?
