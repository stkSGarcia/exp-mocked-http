## Why

Mock users need to exercise message-driven integrations without standing up bespoke test harnesses around Kafka or RabbitMQ. This change adds broker-backed consume and publish behavior so loaded mocks can react to asynchronous messages and emit broker messages using the same template-driven model as existing HTTP mocks.

## Related Work

### Related Changes

- `add-template-helpers-file-backed-bodies`: introduced file-backed response content and richer template support; this change extends that pattern to broker publish payloads.
- `add-admin-api-template-storage`: introduced runtime mock management concerns; this change complements it by making message broker mocks part of the same loaded mock model.
- `add-hot-reload-cors-binary-admin-cli`: expanded mock runtime coverage for richer workflows; this change adds asynchronous broker workflows to that broader mock surface.

### Related Specs

- `mock-definition-loading`: defines runtime configuration, behavior validation, ordered loading, and file-backed body loading. This change reuses those patterns for broker environment variables and `payload_from_file` loading.
- `http-behavior-mocking`: defines condition routing and ordered action execution. This change adapts action ordering for broker publish actions while defining separate all-match semantics for consumed broker messages.
- `template-rendering`: defines shared template syntax, functions, and values. This change reuses that rendering model with Kafka and AMQP-specific message context variables.

## What Changes

- Add opt-in Kafka support controlled by environment variables, including shared defaults and producer/consumer-specific broker, SASL, and TLS overrides.
- Add `expect.kafka` matching by topic and condition using Kafka template context, with every matching behavior executed in loaded order for each consumed message.
- Add `publish_kafka` actions that publish rendered inline or file-backed payloads to Kafka topics.
- Add opt-in AMQP support controlled by `HM_AMQP_ENABLED` and `HM_AMQP_URL`.
- Add `expect.amqp` matching by exchange, routing key, and queue, including queue defaulting and startup resource/binding setup.
- Add `publish_amqp` actions that publish rendered inline or file-backed payloads to AMQP exchanges and routing keys.
- Add automatic AMQP consumption recovery after transient disconnects.

## Capabilities

### New Capabilities

- `kafka-message-handling`: Kafka configuration, consuming, matching, template context, and publish actions.
- `amqp-message-handling`: AMQP configuration, resource setup, consuming, matching, template context, reconnect behavior, and publish actions.

### Modified Capabilities

- `mock-definition-loading`: validate broker expectation and publish action shapes and load broker `payload_from_file` content using existing file-backed payload rules.
- `http-behavior-mocking`: allow broker publish actions to participate in existing stable action ordering.

## Impact

- Mock YAML schema accepts `expect.kafka`, `expect.amqp`, `publish_kafka`, and `publish_amqp`.
- Runtime configuration gains Kafka and AMQP environment variables.
- The server process may create Kafka and AMQP client connections when enabled.
- Additional dependencies may be required for Kafka and AMQP clients.
- Tests need broker-client fakes or integration seams for consume, publish, reconnect, resource setup, and payload rendering behavior.
