## Why

hmock currently handles only HTTP, Redis, and outbound HTTP behaviors. Teams working with event-driven architectures need the ability to consume and react to Kafka and AMQP messages within the same mock server, keeping integration test environments simple and self-contained.

## What Changes

- Add Kafka consumer/producer support with per-producer and per-consumer connection overrides (brokers, SASL, TLS)
- Add `expect.kafka` mock section for matching on topic and condition, executing all matching behaviors in loaded order
- Add `publish_kafka` behavior to publish messages to Kafka topics
- Add AMQP (RabbitMQ) consumer/producer support with auto-setup of exchanges, queues, and bindings
- Add `expect.amqp` mock section for matching on exchange, routing key, and queue, executing all matching behaviors in loaded order
- Add `publish_amqp` behavior to publish messages to AMQP exchanges
- Startup consumes only topics and queues referenced by loaded mocks
- AMQP reconnects automatically after transient disconnects

## Capabilities

### New Capabilities
- `kafka-messaging`: Kafka consumer and producer integration — environment config, `expect.kafka` mock matching, `publish_kafka` behavior, per-producer/consumer connection overrides
- `amqp-messaging`: AMQP (RabbitMQ) consumer and producer integration — environment config, `expect.amqp` mock matching with auto-setup, `publish_amqp` behavior, automatic reconnection

### Modified Capabilities
- `http-mock-server`: Extend the mock file format to support `expect.kafka` and `expect.amqp` sections alongside the existing `expect.http`

## Impact

- New runtime dependencies: Kafka client library (`kafka-python` or `aiokafka`), AMQP client library (`aio-pika`)
- `hmock.py`: new environment variable parsing, new consumer/producer startup logic, extended mock-loading to register Kafka/AMQP handlers
- Mock YAML schema gains `expect.kafka`, `expect.amqp`, `publish_kafka`, `publish_amqp` fields
- `docker-compose` / deployment configs need broker service definitions for integration tests
