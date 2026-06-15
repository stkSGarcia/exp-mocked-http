## Why

The mock server currently models HTTP-driven behavior, but many integration flows depend on Kafka topics and AMQP queues. Adding broker-backed expectations and publish actions lets teams test asynchronous message workflows with the same YAML mock definitions, templating, ordering, and fixture-loading model they already use for HTTP mocks.

## What Changes

- Add opt-in Kafka support for consuming configured topics from loaded mocks and publishing rendered messages.
- Add opt-in AMQP support for declaring/binding broker resources, consuming configured queues, recovering after transient disconnects, and publishing rendered messages.
- Add `expect.kafka` and `expect.amqp` behavior triggers with broker-specific template contexts and condition rendering.
- Add `publish_kafka` and `publish_amqp` actions with inline and file-backed payload support.
- Extend runtime configuration with Kafka and AMQP environment variables, including producer/consumer Kafka override handling.

## Capabilities

### New Capabilities
- `message-broker-mocking`: Kafka and AMQP consumption, matching, broker-specific template contexts, publish actions, resource setup, and reconnect behavior.

### Modified Capabilities
- `mock-definition-loading`: Runtime configuration and behavior/action schema validation must accept the new broker settings, expectations, publish actions, and file-backed publish payloads.
- `template-rendering`: Broker-triggered conditions and publish payloads require Kafka and AMQP template contexts while preserving the existing template syntax and functions.
- `http-behavior-mocking`: HTTP-selected behaviors can execute `publish_kafka` and `publish_amqp` actions through the existing ordered action execution model.

## Impact

- Affects `hmock.py` configuration, behavior validation, template rendering context construction, action execution, and server lifecycle management.
- Adds optional Kafka and AMQP client dependencies or adapters, gated by `HM_KAFKA_ENABLED` and `HM_AMQP_ENABLED`.
- Extends tests for environment parsing, schema validation, file-backed payload loading, broker matching, ordered multi-match behavior, publish actions, AMQP setup/reconnect, and disabled broker behavior.
