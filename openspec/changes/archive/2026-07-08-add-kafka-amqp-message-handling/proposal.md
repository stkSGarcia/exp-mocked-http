## Why

Mocks currently focus on HTTP request/response workflows, but modern services also coordinate work through brokers. Adding Kafka and AMQP handling lets the mock server participate in event-driven integration tests by consuming broker messages, matching them against loaded mock definitions, and publishing templated follow-up messages.

## What Changes

- Add Kafka runtime configuration with shared defaults plus producer- and consumer-specific broker, SASL, and TLS overrides.
- Add `expect.kafka` support that consumes topics referenced by loaded mocks, exposes Kafka template context values, evaluates conditions, and executes every matching behavior in loaded order.
- Add `publish_kafka` actions with inline or file-backed template-rendered payloads.
- Add AMQP runtime configuration, automatic exchange/queue/binding setup for loaded AMQP mocks, and transient disconnect recovery.
- Add `expect.amqp` support with exchange, routing key, queue defaulting, AMQP template context values, condition evaluation, and loaded-order execution for every matching behavior.
- Add `publish_amqp` actions with inline or file-backed template-rendered payloads.

## Related Work

### Related Changes

- None found by the shallow KG search.

### Related Specs

- `mock-definition-loading/add-http-yaml-mock-server`: Establishes environment-based runtime configuration defaults and YAML-driven mock loading. This change extends that configuration style to broker enablement, connection defaults, and loaded mock discovery for Kafka topics and AMQP resources.
- `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`: Defines stable action ordering and behavior evaluation semantics for HTTP mocks. This change adapts the action execution model for broker messages while intentionally allowing every matching Kafka or AMQP behavior to run.
- `api-template-persistence/add-admin-api-template-storage`: Covers persisted reusable templates and admin-managed mock definition data. This change complements that work by ensuring broker publish payloads use the same template/file-backed rendering expectations as existing action payloads.

## Capabilities

### New Capabilities

- `kafka-message-mocking`: Kafka configuration, consumption, matching, template context, and publish actions.
- `amqp-message-mocking`: AMQP configuration, resource setup, consumption, matching, template context, reconnect recovery, and publish actions.

### Modified Capabilities

- None.

## Impact

- Adds optional Kafka and AMQP broker dependencies when enabled by environment variables.
- Extends mock definition parsing with `expect.kafka`, `expect.amqp`, `publish_kafka`, and `publish_amqp`.
- Extends runtime action execution and template rendering to asynchronous broker messages.
- Adds background consumers and publisher clients that must start, stop, and recover cleanly with the server lifecycle.
