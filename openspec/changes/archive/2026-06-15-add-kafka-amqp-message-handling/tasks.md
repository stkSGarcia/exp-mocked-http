## 1. Configuration And Test Fixtures

- [x] 1.1 Add Kafka and AMQP configuration fields, defaults, boolean parsing, and resolved Kafka producer/consumer override helpers to `hmock.py`.
- [x] 1.2 Add tests for Kafka disabled defaults, enabled defaults, shared overrides, producer overrides, consumer overrides, and per-endpoint SASL enablement.
- [x] 1.3 Add tests for AMQP disabled defaults, enabled default URL, and `HM_AMQP_URL` override.
- [x] 1.4 Add fake broker producer/consumer adapters for unit tests without requiring live Kafka or RabbitMQ.

## 2. Behavior Model And Validation

- [x] 2.1 Refactor loaded behavior modeling so HTTP, Kafka, and AMQP triggers can share actions, conditions, values, and templates.
- [x] 2.2 Validate `expect.kafka.topic` and allow Kafka-only behaviors without requiring `expect.http`.
- [x] 2.3 Validate `expect.amqp.exchange`, `expect.amqp.routing_key`, and default missing or empty `expect.amqp.queue` to the routing key.
- [x] 2.4 Validate `publish_kafka` and `publish_amqp` action payloads, required destination fields, and required inline or file-backed payload source.
- [x] 2.5 Load `publish_kafka.payload_from_file` and `publish_amqp.payload_from_file` relative to `HM_TEMPLATES_DIR`, snapshot contents, and reject missing or escaping paths.
- [x] 2.6 Add validation tests for accepted and rejected Kafka/AMQP expectations and broker publish actions.

## 3. Template Context And Shared Actions

- [x] 3.1 Add broker template context builders exposing `.KafkaTopic`, `.KafkaPayload`, `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, `.AMQPPayload`, `.Values`, named templates, and template functions.
- [x] 3.2 Refactor action execution so `sleep`, `redis`, `send_http`, `publish_kafka`, and `publish_amqp` run from a supplied render context and dependency bundle.
- [x] 3.3 Implement `publish_kafka` rendering and producer dispatch with inline payload precedence over `payload_from_file`.
- [x] 3.4 Implement `publish_amqp` rendering and producer dispatch with inline payload precedence over `payload_from_file`.
- [x] 3.5 Preserve HTTP `reply_http` response behavior while allowing HTTP-triggered behaviors to execute broker publish actions in normal action order.
- [x] 3.6 Add tests for broker template variables, values inheritance in broker contexts, file-backed publish rendering, and HTTP-triggered broker publish ordering.

## 4. Kafka Runtime

- [x] 4.1 Implement Kafka adapter interfaces for subscribing to referenced topics and publishing rendered payloads.
- [x] 4.2 Start Kafka consumers only when `HM_KAFKA_ENABLED` is true and loaded mocks reference Kafka topics.
- [x] 4.3 Match consumed Kafka messages by topic, evaluate conditions with the Kafka context, and execute every matching behavior in loaded order.
- [x] 4.4 Reconcile Kafka topic subscriptions from the current mock state so hot reload and API-updated mocks affect future consumed messages.
- [x] 4.5 Add tests for referenced topic discovery, topic matching, condition pass/fail behavior, and all-matches execution order using fake adapters.

## 5. AMQP Runtime

- [x] 5.1 Implement AMQP adapter interfaces for declaring exchanges, queues, bindings, consuming queues, publishing messages, and reconnecting after transient disconnects.
- [x] 5.2 Start AMQP consumers only when `HM_AMQP_ENABLED` is true and loaded mocks reference AMQP expectations.
- [x] 5.3 Ensure AMQP exchanges, queues, and bindings exist before consuming messages.
- [x] 5.4 Match consumed AMQP messages by exchange, routing key, and resolved queue, evaluate conditions with the AMQP context, and execute every matching behavior in loaded order.
- [x] 5.5 Add tests for AMQP setup, queue defaulting, message matching, condition pass/fail behavior, all-matches execution order, and reconnect recovery using fake adapters.

## 6. Lifecycle And Verification

- [x] 6.1 Wire broker worker startup and shutdown into the existing server lifecycle without changing HTTP-only startup behavior.
- [x] 6.2 Ensure missing optional broker client dependencies produce clear startup errors only when the corresponding broker feature is enabled.
- [x] 6.3 Run the existing test suite and add regression coverage for HTTP-only behavior with broker features disabled.
- [x] 6.4 Run `openspec status --change "add-kafka-amqp-message-handling"` and confirm the change is ready for implementation review.
