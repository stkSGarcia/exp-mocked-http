## 1. Configuration And Broker Adapters

- [x] 1.1 Extend `Config` and `load_config` for Kafka enablement, shared Kafka defaults, producer/consumer override resolution, side-specific SASL enablement, Kafka TLS flags, AMQP enablement, and AMQP URL.
- [x] 1.2 Add focused helpers for parsing comma-separated Kafka broker lists and side-specific Kafka override fallback rules.
- [x] 1.3 Define injectable Kafka and AMQP adapter interfaces for publish, consume/setup, reconnect/close behavior, with test fakes that do not require real brokers.
- [x] 1.4 Gate production broker client imports and adapter construction behind `HM_KAFKA_ENABLED` and `HM_AMQP_ENABLED`.

## 2. Definition Model And Validation

- [x] 2.1 Extend `Behavior` and related loading code to carry optional HTTP, Kafka, and AMQP expectation data while preserving existing HTTP behavior matching.
- [x] 2.2 Validate `expect.kafka.topic` and reject missing, empty, or non-string Kafka topics.
- [x] 2.3 Validate `expect.amqp.exchange`, `expect.amqp.routing_key`, and optional `expect.amqp.queue`, defaulting an empty or omitted queue to the routing key.
- [x] 2.4 Validate `publish_kafka` action fields, including `topic`, `payload`, and `payload_from_file` requirements.
- [x] 2.5 Validate `publish_amqp` action fields, including `exchange`, `routing_key`, `payload`, and `payload_from_file` requirements.
- [x] 2.6 Load and snapshot broker `payload_from_file` content with the same templates-directory safety checks as other text file-backed fields.
- [x] 2.7 Preserve inheritance, values merging, duplicate-key replacement, and stable action ordering for HTTP, Kafka, and AMQP behaviors.

## 3. Template Contexts And Action Execution

- [x] 3.1 Add Kafka template context construction with `.KafkaTopic`, `.KafkaPayload`, `.Values`, named templates, and existing template functions.
- [x] 3.2 Add AMQP template context construction with `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, `.AMQPPayload`, `.Values`, named templates, and existing template functions.
- [x] 3.3 Refactor ordered action execution so HTTP and broker triggers share `sleep`, `redis`, `send_http`, broker publish, and response-producing `reply_http` behavior.
- [x] 3.4 Implement `publish_kafka` rendering, inline/file payload precedence, publish calls, failure logging, and continue-on-failure behavior.
- [x] 3.5 Implement `publish_amqp` rendering, inline/file payload precedence, publish calls, failure logging, and continue-on-failure behavior.
- [x] 3.6 Ensure HTTP-selected broker publish actions do not replace or suppress the inbound HTTP response.

## 4. Broker Runtime

- [x] 4.1 Add Kafka message matching that consumes topics referenced by active loaded mocks, evaluates conditions, and executes every matching behavior in loaded order.
- [x] 4.2 Refresh Kafka subscriptions when active mock snapshots change and the referenced topic set changes.
- [x] 4.3 Add AMQP startup setup that declares or ensures exchanges, effective queues, and queue bindings for loaded AMQP expectations.
- [x] 4.4 Add AMQP message matching that evaluates exchange, routing key, effective queue, conditions, and loaded-order multi-match execution.
- [x] 4.5 Add AMQP reconnect handling that recreates resources and resumes consumption after transient disconnects.
- [x] 4.6 Integrate broker runtime startup and shutdown with the existing mock server/runtime lifecycle while keeping disabled brokers inert.

## 5. Tests And Verification

- [x] 5.1 Add configuration tests for Kafka defaults, producer/consumer overrides, side-specific SASL enablement, Kafka TLS, AMQP defaults, and AMQP overrides.
- [x] 5.2 Add validation tests for Kafka expectations, AMQP expectations, broker publish actions, and broker `payload_from_file` path safety/snapshot behavior.
- [x] 5.3 Add template rendering tests for Kafka and AMQP contexts, values, named templates, conditions, and publish payload fields.
- [x] 5.4 Add HTTP behavior tests for ordered `publish_kafka` and `publish_amqp` execution, inline/file precedence, publish failure continuation, and response preservation.
- [x] 5.5 Add Kafka runtime tests for topic subscription, topic mismatch, condition pass/fail/error behavior, loaded-order multi-match execution, and disabled Kafka behavior.
- [x] 5.6 Add AMQP runtime tests for queue defaulting, resource setup, match/mismatch behavior, condition pass/fail/error behavior, loaded-order multi-match execution, reconnect recovery, and disabled AMQP behavior.
- [x] 5.7 Run the project test suite with `uv run pytest`.
