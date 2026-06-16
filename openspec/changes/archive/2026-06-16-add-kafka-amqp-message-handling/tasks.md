## 1. Configuration And Model

- [x] 1.1 Extend `hmock.py` `Config` and `load_config` with Kafka and AMQP environment variables and unit tests in `tests/test_hmock.py`. [extends mock-definition-loading]
- [x] 1.2 Add Kafka producer/consumer override resolution helpers in `hmock.py`, including per-side SASL and TLS fallback tests. [extends kafka-message-handling]
- [x] 1.3 Extend `Behavior` in `hmock.py` to carry optional Kafka and AMQP expectation data while preserving existing HTTP behavior tests. [extends mock-definition-loading]

## 2. Definition Validation And File Loading

- [x] 2.1 Extend `hmock.py` expectation validation for `expect.kafka.topic` and `expect.amqp.exchange`, `routing_key`, and optional `queue`. [extends mock-definition-loading]
- [x] 2.2 Extend `hmock.py` action validation for `publish_kafka` and `publish_amqp` required fields and payload-source rules. [extends mock-definition-loading]
- [x] 2.3 Reuse `_resolve_body_file` in `hmock.py` to snapshot broker `payload_from_file` content and add path safety tests in `tests/test_hmock.py`. [extends mock-definition-loading]

## 3. Broker Dispatch

- [x] 3.1 Add Kafka message context construction and matching dispatch in `hmock.py`, executing every matching behavior in loaded order. [extends kafka-message-handling]
- [x] 3.2 Add AMQP message context construction and matching dispatch in `hmock.py`, including queue defaulting to routing key. [extends amqp-message-handling]
- [x] 3.3 Add condition render failure tests for broker dispatch so later matching behaviors still run. [extends kafka-message-handling]
- [x] 3.4 Add tests proving Kafka and AMQP template contexts expose `.KafkaTopic`, `.KafkaPayload`, `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, and `.AMQPPayload`. [extends template-rendering]

## 4. Publish Actions

- [x] 4.1 Extend `execute_actions` in `hmock.py` to execute `publish_kafka` with rendered inline and file-backed payloads through an injectable producer adapter. [extends kafka-message-handling]
- [x] 4.2 Extend `execute_actions` in `hmock.py` to execute `publish_amqp` with rendered inline and file-backed payloads through an injectable AMQP adapter. [extends amqp-message-handling]
- [x] 4.3 Add action ordering tests in `tests/test_hmock.py` showing broker publish actions sort with `redis`, `send_http`, `sleep`, and `reply_http`. [extends http-behavior-mocking]
- [x] 4.4 Add tests for inline payload precedence over `payload_from_file` for both broker publish actions. [extends mock-definition-loading]

## 5. Runtime Workers And Adapters

- [x] 5.1 Add Kafka adapter and worker startup in `hmock.py` behind `HM_KAFKA_ENABLED`, with fake-adapter tests proving no connection is created when disabled. [extends kafka-message-handling]
- [x] 5.2 Add AMQP adapter resource setup and worker startup in `hmock.py` behind `HM_AMQP_ENABLED`, with fake-adapter tests for exchange, queue, and binding setup. [extends amqp-message-handling]
- [x] 5.3 Add AMQP reconnect loop behavior in `hmock.py` with bounded backoff and fake-adapter tests for consumption recovery. [extends amqp-message-handling]
- [x] 5.4 Ensure broker workers read `HMockRuntimeState.get_behaviors()` during dispatch so hot reload and admin-managed mocks are reflected. [extends mock-definition-loading]

## 6. Verification

- [x] 6.1 Run `uv run pytest tests/test_hmock.py` and fix any regressions.
- [x] 6.2 Run `openspec status --change "add-kafka-amqp-message-handling"` and confirm all proposal artifacts remain complete.
