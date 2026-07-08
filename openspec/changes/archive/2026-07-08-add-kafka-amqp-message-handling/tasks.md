## 1. Configuration and Dependency Boundaries

- [x] 1.1 Extend `Config` and `load_config` in `hmock.py` with Kafka shared defaults, producer/consumer override resolution, side-specific SASL enablement, side-specific TLS enablement, and AMQP URL/enablement fields. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 1.2 Add tests in `tests/test_hmock.py` for Kafka defaults, producer/consumer fallback behavior, independent SASL enablement, TLS overrides, AMQP defaults, and disabled-by-default broker features. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 1.3 Add lazy import/client factory boundaries in `hmock.py` so Kafka and AMQP libraries are required only when the corresponding feature is enabled.

## 2. Mock Definition Schema and Loading

- [x] 2.1 Refactor the `Behavior` model and `validate_behavior` in `hmock.py` so concrete behaviors can declare exactly one supported expectation type: `expect.http`, `expect.kafka`, or `expect.amqp`. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 2.2 Validate `expect.kafka.topic`, `expect.amqp.exchange`, `expect.amqp.routing_key`, AMQP queue defaulting, and invalid/missing broker expectation fields in `hmock.py`. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 2.3 Extend `_validate_actions` in `hmock.py` for `publish_kafka` and `publish_amqp`, including required target fields, mutually sufficient `payload`/`payload_from_file`, and file snapshot resolution with existing path-safety helpers. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 2.4 Add validation and YAML-loading tests in `tests/test_hmock.py` for Kafka/AMQP expectations, queue defaulting, publish action validation, and file-backed publish payload snapshots.

## 3. Shared Matching and Action Execution

- [x] 3.1 Preserve existing HTTP matching in `find_behavior` and add broker-specific matching helpers in `hmock.py` that return every Kafka or AMQP behavior matching a consumed message in loaded order. [extends http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering]
- [x] 3.2 Extend template context construction in `hmock.py` for Kafka values (`.KafkaTopic`, `.KafkaPayload`) and AMQP values (`.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, `.AMQPPayload`).
- [x] 3.3 Split `execute_behavior` in `hmock.py` into reusable action execution logic plus HTTP response assembly so broker-triggered behaviors can run `sleep`, `redis`, `send_http`, `publish_kafka`, and `publish_amqp` without requiring `reply_http`. [extends http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering]
- [x] 3.4 Add tests in `tests/test_hmock.py` proving multiple Kafka matches and multiple AMQP matches execute in loaded order while HTTP still selects one response behavior.

## 4. Kafka Runtime

- [x] 4.1 Implement a Kafka producer/consumer adapter in `hmock.py` using resolved config, lazy dependencies, producer settings for publish, and consumer settings for topic consumption.
- [x] 4.2 Implement `KafkaBrokerService` in `hmock.py` to discover topics from `ActiveMockRegistry.behaviors()`, consume referenced topics, evaluate Kafka conditions, and execute all matching behaviors.
- [x] 4.3 Implement `publish_kafka` action execution in `hmock.py` for inline and file-backed template-rendered payloads.
- [x] 4.4 Add fake-adapter tests in `tests/test_hmock.py` for topic discovery, condition context, all-match execution order, and rendered Kafka publish payloads.

## 5. AMQP Runtime

- [x] 5.1 Implement an AMQP adapter in `hmock.py` using resolved URL config, lazy dependencies, exchange/queue/binding setup, publishing, consuming, and reconnect hooks.
- [x] 5.2 Implement `AMQPBrokerService` in `hmock.py` to ensure resources for loaded mocks, consume queues, apply queue defaulting, evaluate AMQP conditions, execute all matching behaviors, and restore resources after transient disconnects.
- [x] 5.3 Implement `publish_amqp` action execution in `hmock.py` for inline and file-backed template-rendered payloads.
- [x] 5.4 Add fake-adapter tests in `tests/test_hmock.py` for resource setup, queue defaulting, AMQP context, all-match execution order, rendered publish payloads, and reconnect recovery.

## 6. Server Lifecycle and Verification

- [x] 6.1 Wire optional broker services into `build_server`/`main` in `hmock.py` so enabled services start with the process and stop cleanly with HTTP/admin shutdown.
- [x] 6.2 Add lifecycle tests in `tests/test_hmock.py` for disabled broker services, enabled fake broker startup, shutdown, and worker thread joining.
- [ ] 6.3 Run `uv run pytest` and fix any regressions across existing HTTP, Redis, template, admin, Kafka, and AMQP behavior.
