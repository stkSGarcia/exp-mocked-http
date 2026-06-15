## Why

Teams that mock HTTP integrations also need to exercise event-driven integrations without standing up bespoke test services for each workflow. Adding Kafka and AMQP support lets the same mock definition model consume messages, evaluate conditions, and publish broker messages alongside existing HTTP and Redis actions.

## What Changes

- Add opt-in Kafka consumption and publishing controlled by `HM_KAFKA_*` environment variables, with shared defaults and producer/consumer-specific overrides.
- Add `expect.kafka` matching for consumed Kafka messages, including topic and payload template context.
- Add `publish_kafka` actions with inline or file-backed, template-rendered payloads.
- Add opt-in AMQP consumption and publishing controlled by `HM_AMQP_*` environment variables.
- Add `expect.amqp` matching with exchange, routing key, queue defaulting, broker resource setup, message template context, and automatic reconnect after transient disconnects.
- Add `publish_amqp` actions with inline or file-backed, template-rendered payloads.
- Execute every matching broker behavior in loaded order for each consumed Kafka or AMQP message.

## Capabilities

### New Capabilities
- `message-broker-mocking`: Kafka and AMQP consumption, matching, template context, and broker publish action execution.

### Modified Capabilities
- `mock-definition-loading`: Runtime configuration, behavior validation, and file-backed payload snapshot validation for Kafka and AMQP expectations and publish actions.

## Impact

- Affects `hmock.py` configuration loading, behavior validation, template file loading, runtime startup/shutdown, and action execution.
- Adds external Kafka and AMQP client dependencies or adapters for consuming and publishing messages.
- Adds tests for Kafka and AMQP environment resolution, schema validation, file-backed payload loading, matching semantics, action execution order, AMQP setup/reconnect behavior, and disabled-by-default behavior.
