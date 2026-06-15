## Why

Mock scenarios increasingly need to model asynchronous integrations in addition to HTTP request/response flows. Adding Kafka and AMQP support lets the server consume broker messages, match them against loaded behaviors, and publish broker messages from actions using the same template-driven mock definitions.

## What Changes

- Add opt-in Kafka support controlled by `HM_KAFKA_*` environment variables, including shared producer/consumer defaults, producer/consumer overrides, TLS toggles, and SASL enablement only when both resolved username and password are non-empty.
- Add opt-in AMQP support controlled by `HM_AMQP_*` environment variables, including an AMQP connection URL, startup broker resource setup, and automatic consumption recovery after transient disconnects.
- Add `expect.kafka` behavior matching by consumed topic plus `expect.condition`, with Kafka-specific template context values for topic and payload.
- Add `expect.amqp` behavior matching by exchange, routing key, and queue, with omitted or empty queue defaulting to the routing key and AMQP-specific template context values for exchange, routing key, queue, and payload.
- Add `publish_kafka` and `publish_amqp` actions with inline payload templates and file-backed payload templates using existing file loading and rendering rules.
- Preserve loaded behavior order when multiple broker behaviors match a message; Kafka and AMQP message handling execute every matching behavior rather than selecting only the first match.

## Capabilities

### New Capabilities
- `message-broker-mocking`: Defines Kafka and AMQP runtime configuration, broker consumers, message matching, broker-specific template contexts, publish actions, AMQP setup, and reconnect behavior.

### Modified Capabilities
- `mock-definition-loading`: Extends mock validation and file loading rules for broker expectations and `publish_kafka` / `publish_amqp` actions.
- `template-rendering`: Extends template rendering contexts to support Kafka and AMQP message-driven behavior execution.
- `http-behavior-mocking`: Extends HTTP action execution so HTTP-triggered behaviors may use broker publish actions in normal action order.

## Impact

- Affects `hmock.py` configuration, validation, mock collection behavior modeling, action execution, startup orchestration, and shutdown/reconnect handling.
- Adds runtime dependencies for Kafka and AMQP clients, selected to fit the existing Python server and test workflow.
- Adds unit tests for config parsing, validation, file-backed broker payload loading, broker context rendering, and ordered action execution.
- Adds integration-style tests around broker adapters using fakes or lightweight abstractions so core behavior is testable without requiring live Kafka or RabbitMQ for every test run.
