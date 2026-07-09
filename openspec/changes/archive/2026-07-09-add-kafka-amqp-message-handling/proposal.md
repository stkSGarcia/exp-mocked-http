## Why

HTTP mocks already cover request/response behavior, templating, file-backed payloads, and ordered actions, but services that communicate through brokers need the same mock-driven workflow for asynchronous messages. Adding Kafka and AMQP support lets test environments consume broker messages, match them with mock definitions, and publish templated responses or side effects without a separate harness.

## What Changes

- Add Kafka runtime configuration, including shared defaults plus producer- and consumer-specific broker, SASL, and TLS overrides.
- Add `expect.kafka` matching that consumes topics referenced by loaded mocks, exposes a Kafka template context, evaluates conditions, and executes every matching behavior in loaded order.
- Add `publish_kafka` actions with inline or file-backed template-rendered payloads.
- Add AMQP runtime configuration from environment variables.
- Add `expect.amqp` matching with exchange, routing key, queue defaulting, automatic broker resource setup, AMQP template context, loaded-order multi-match execution, and transient reconnect recovery.
- Add `publish_amqp` actions with inline or file-backed template-rendered payloads.

## Related Work

### Related Changes

- No related change intents were returned by the shallow KG search.

### Related Specs

- `template-rendering/add-http-yaml-mock-server`: Established that conditions and rendered output share one request-oriented template context; this change extends that pattern with Kafka and AMQP message contexts.
- `mock-definition-loading/add-http-yaml-mock-server`: Established environment-driven runtime configuration with documented defaults; this change applies the same configuration style to broker clients.
- `template-rendering/add-stateful-actions`: Made template helpers available across expression contexts; broker conditions and publish payloads should reuse the same rendering pipeline.
- `http-behavior-mocking/add-template-helpers-file-backed-bodies`: Added file-backed HTTP response bodies; this change adapts that behavior for broker publish payloads.
- `http-behavior-mocking/add-stateful-actions`: Defined action execution order for selected behaviors; broker matching needs its own multi-match semantics while preserving per-behavior action order.
- `mock-definition-loading/add-template-helpers-file-backed-bodies`: Defined load-time resolution of file-backed body fields; broker payload files should follow the same path and error handling rules.
- `http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering`: Refined stable action ordering; this change depends on that ordering inside each matching Kafka or AMQP behavior.

## Capabilities

### New Capabilities

- `kafka-message-handling`: Kafka environment configuration, topic consumption, Kafka expectation matching, template context, and Kafka publish actions.
- `amqp-message-handling`: AMQP environment configuration, broker resource setup, queue consumption, AMQP expectation matching, reconnect recovery, template context, and AMQP publish actions.

### Modified Capabilities

- None.

## Impact

- Mock definition schema grows with `expect.kafka`, `expect.amqp`, `publish_kafka`, and `publish_amqp`.
- Runtime configuration gains Kafka and AMQP environment variables.
- Broker client dependencies may be added for Kafka and AMQP connections.
- Message consumption introduces asynchronous startup, broker setup, reconnect, and test coverage concerns.
- Template rendering and file-backed payload loading are reused for broker publish payloads.
