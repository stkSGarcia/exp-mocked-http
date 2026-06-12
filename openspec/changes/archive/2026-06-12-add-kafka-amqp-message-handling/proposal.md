## Why

The mock server only reacts to HTTP requests, so it cannot model services that consume and publish broker messages. Kafka and AMQP support is needed to exercise event-driven workflows with the same YAML behaviors, templates, and ordered actions already used for HTTP mocks.

## Related Work

### Related Changes

- `add-stateful-actions-redis-http-side-effects` introduced non-response actions and outbound side effects; this change complements it with Kafka and AMQP publish actions triggered by any supported transport.
- `add-behavior-templates-inheritance-values-ordering` established reusable behaviors, per-behavior values, and deterministic action ordering; broker-triggered behaviors retain those semantics while allowing every match to execute.
- `add-hot-reload-cors-binary-admin-cli` added environment-driven runtime features and runtime reload behavior; broker workers follow the same configuration and lifecycle conventions.

### Related Specs

- `cors-response-policy/add-hot-reload-cors-binary-admin-cli` defines boolean environment configuration conventions that Kafka and AMQP enablement and TLS settings reuse.
- `http-yaml-mock-server/add-template-helpers-file-backed-bodies` defines template rendering and safe file-backed body loading; broker publish payloads adapt the same rendering, precedence, snapshot, and path-safety behavior.
- `http-yaml-mock-server/add-admin-api-template-persistence` defines startup and runtime behavior compilation; broker topic subscriptions and AMQP topology are derived from the resulting loaded behavior set.

## What Changes

- Add Kafka configuration with shared defaults, producer/consumer overrides, role-specific SASL resolution, TLS settings, and client identification.
- Add `expect.kafka` matching by topic and condition, with Kafka template context and execution of every match in loaded order.
- Subscribe Kafka consumption only to topics referenced by loaded mocks.
- Add a `publish_kafka` action with inline or file-backed templated payloads.
- Add AMQP configuration, automatic exchange/queue/binding setup, and consumer recovery after transient disconnects.
- Add `expect.amqp` matching with queue defaulting, AMQP template context, and execution of every match in loaded order.
- Add a `publish_amqp` action with inline or file-backed templated payloads.
- Add broker client dependencies and deterministic tests using mocked Kafka and AMQP clients.

## Capabilities

### New Capabilities

- `kafka-message-handling`: Kafka configuration, topic consumption, message matching, template context, ordered multi-match execution, and publishing.
- `amqp-message-handling`: AMQP configuration, topology setup, resilient consumption, message matching, template context, ordered multi-match execution, and publishing.

### Modified Capabilities

None.

## Impact

- `hmock.py`: configuration, behavior/action validation, payload loading, broker matching, client adapters, worker lifecycle, and shutdown.
- `test_hmock.py`: configuration precedence, validation, matching/order, publishing, topology, and reconnect tests with mocked clients.
- `pyproject.toml` and `uv.lock`: Kafka and AMQP client libraries.
- Runtime deployments may optionally connect to Kafka and RabbitMQ-compatible AMQP brokers when their respective enable flags are set.
