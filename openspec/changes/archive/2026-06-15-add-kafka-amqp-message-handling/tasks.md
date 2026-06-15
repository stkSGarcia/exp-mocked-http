## 1. Configuration And Model

- [x] 1.1 Add Kafka and AMQP configuration fields to `Config`, including enabled flags, defaults, Kafka shared settings, Kafka producer/consumer overrides, and AMQP URL.
- [x] 1.2 Implement Kafka producer and consumer resolved-config helpers that apply override/fallback rules and enable SASL only when resolved username and password are both non-empty.
- [x] 1.3 Extend the loaded `Behavior` model to retain optional HTTP, Kafka, and AMQP expectations while preserving existing HTTP matching behavior.
- [x] 1.4 Add broker message context construction for Kafka (`.KafkaTopic`, `.KafkaPayload`) and AMQP (`.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, `.AMQPPayload`) with existing values, templates, and Redis functions.

## 2. Mock Definition Loading

- [x] 2.1 Validate `expect.kafka.topic` as a required non-empty string when `expect.kafka` is present.
- [x] 2.2 Validate `expect.amqp.exchange`, `expect.amqp.routing_key`, and optional string `expect.amqp.queue`, defaulting an omitted or empty queue to the routing key.
- [x] 2.3 Allow broker-only behaviors that omit `expect.http` while preserving validation for existing HTTP behaviors.
- [x] 2.4 Validate `publish_kafka` actions, including required `topic` and exactly one usable payload source from `payload` or `payload_from_file`.
- [x] 2.5 Validate `publish_amqp` actions, including required `exchange`, `routing_key`, and exactly one usable payload source from `payload` or `payload_from_file`.
- [x] 2.6 Load and snapshot broker `payload_from_file` values with the same templates-directory containment and missing-file checks used by existing file-backed actions.

## 3. Broker Runtime

- [x] 3.1 Add Kafka and AMQP client adapter interfaces with fake-adapter-friendly methods for subscribe, consume loop callbacks, publish, declare/bind, reconnect, and close.
- [x] 3.2 Start Kafka consumers only when `HM_KAFKA_ENABLED=true`, subscribing to all topics referenced by loaded `expect.kafka` behaviors.
- [x] 3.3 Start AMQP consumers only when `HM_AMQP_ENABLED=true`, declaring exchanges, effective queues, and bindings for loaded `expect.amqp` behaviors before consuming.
- [x] 3.4 Refresh broker subscriptions and AMQP declarations after runtime reloads and admin mutations.
- [x] 3.5 Stop broker consumers and close producer/publisher resources during runtime or server shutdown.
- [x] 3.6 Implement AMQP reconnect handling that resumes consumption for the active loaded bindings after transient disconnects.

## 4. Matching And Actions

- [x] 4.1 Implement Kafka message matching by topic and condition, skipping condition render failures and evaluating every matching behavior in loaded order.
- [x] 4.2 Implement AMQP message matching by exchange, routing key, effective queue, and condition, evaluating every matching behavior in loaded order.
- [x] 4.3 Execute broker-triggered behavior actions with the existing stable order semantics for `sleep`, `redis`, `send_http`, `publish_kafka`, and `publish_amqp`.
- [x] 4.4 Implement `publish_kafka` rendering and publishing for rendered topic plus inline or file-backed payload.
- [x] 4.5 Implement `publish_amqp` rendering and publishing for rendered exchange, routing key, and inline or file-backed payload.
- [x] 4.6 Log Kafka and AMQP publish failures and continue executing later actions.

## 5. Tests And Verification

- [x] 5.1 Add configuration tests for default-disabled Kafka/AMQP behavior, Kafka shared defaults, producer/consumer overrides, SASL enablement, TLS toggles, and AMQP URL resolution.
- [x] 5.2 Add validation tests for Kafka and AMQP expectations, broker-only behaviors, publish action required fields, and broker `payload_from_file` safety checks.
- [x] 5.3 Add unit tests with fake broker adapters for Kafka topic subscription, condition context, all-matching behavior execution, loaded-order execution, and publish action rendering.
- [x] 5.4 Add unit tests with fake broker adapters for AMQP queue defaulting, resource declaration, condition context, all-matching behavior execution, publish action rendering, and reconnect recovery.
- [x] 5.5 Add regression tests proving existing HTTP matching still selects only the first matching HTTP behavior and existing HTTP mocks load unchanged.
- [x] 5.6 Run the project test suite and OpenSpec validation/status checks for `add-kafka-amqp-message-handling`.
