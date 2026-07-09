## 1. Configuration And Model

- [x] 1.1 Extend `hmock.py` `Config` and `load_config` with Kafka enabled/client/broker/SASL/TLS fields and producer/consumer override resolution. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 1.2 Extend `hmock.py` `Config` and `load_config` with AMQP enabled and URL fields using the documented defaults. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 1.3 Extend `hmock.py` behavior data structures so validated behaviors can carry optional HTTP, Kafka, and AMQP expectation data without changing HTTP first-match behavior.
- [x] 1.4 Add focused configuration tests in `tests/test_hmock.py` for Kafka defaults, producer/consumer overrides, SASL enablement, AMQP defaults, and disabled-by-default behavior.

## 2. Schema Validation And File Loading

- [x] 2.1 Update `hmock.py` definition validation to accept `expect.kafka.topic` and validate it as a non-empty string. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 2.2 Update `hmock.py` definition validation to accept `expect.amqp.exchange`, `expect.amqp.routing_key`, and optional `expect.amqp.queue`, defaulting empty queue values to the routing key. [extends mock-definition-loading/add-http-yaml-mock-server]
- [x] 2.3 Update `hmock.py` action validation to accept `publish_kafka.topic` plus `payload` or `payload_from_file`, resolving file-backed payloads with the existing safe file resolver. [extends mock-definition-loading/add-template-helpers-file-backed-bodies]
- [x] 2.4 Update `hmock.py` action validation to accept `publish_amqp.exchange`, `routing_key`, plus `payload` or `payload_from_file`, resolving file-backed payloads with the existing safe file resolver. [extends mock-definition-loading/add-template-helpers-file-backed-bodies]
- [x] 2.5 Add validation and file snapshot tests in `tests/test_hmock.py` for missing broker fields, queue defaulting, missing payload sources, missing payload files, and out-of-root payload paths.

## 3. Broker Matching And Action Execution

- [x] 3.1 Refactor `hmock.py` action execution so HTTP, Kafka, and AMQP can execute ordered actions with a prepared template context while preserving existing HTTP responses. [extends http-behavior-mocking/add-reusable-templates-inheritance-values-action-ordering]
- [x] 3.2 Add Kafka message context construction in `hmock.py` exposing `.KafkaTopic`, `.KafkaPayload`, `.Values`, named templates, and `redisDo`. [extends template-rendering/add-http-yaml-mock-server]
- [x] 3.3 Add AMQP message context construction in `hmock.py` exposing `.AMQPExchange`, `.AMQPRoutingKey`, `.AMQPQueue`, `.AMQPPayload`, `.Values`, named templates, and `redisDo`. [extends template-rendering/add-http-yaml-mock-server]
- [x] 3.4 Implement Kafka multi-match dispatch in `hmock.py` that matches by topic, evaluates `condition`, and executes every matching behavior in loaded order.
- [x] 3.5 Implement AMQP multi-match dispatch in `hmock.py` that matches by exchange/routing key/queue, evaluates `condition`, and executes every matching behavior in loaded order.
- [x] 3.6 Add tests in `tests/test_hmock.py` for broker condition rendering, loaded-order multi-match behavior execution, and preservation of per-behavior action ordering.

## 4. Broker Adapters And Runtime Lifecycle

- [x] 4.1 Add Kafka producer/consumer adapter boundaries in `hmock.py` or a new broker module, with fakeable `start`, `stop`, `subscribe`, and `publish` operations.
- [x] 4.2 Add AMQP adapter boundaries in `hmock.py` or a new broker module, with fakeable resource declaration, binding, consuming, reconnect, `stop`, and `publish` operations.
- [x] 4.3 Wire broker managers into `HMockRuntimeState.reload` or the server startup path so Kafka subscriptions and AMQP declarations are refreshed from current loaded behaviors.
- [x] 4.4 Update `hmock.py` `main()` lifecycle to start enabled broker managers after state initialization and stop them during shutdown.
- [x] 4.5 Add adapter-level tests in `tests/test_hmock.py` using fake Kafka and AMQP clients to verify topic subscription, AMQP setup, publish calls, and AMQP reconnect recovery.

## 5. Publish Actions And Verification

- [x] 5.1 Implement `publish_kafka` execution in `hmock.py`, rendering inline and file-backed payloads with the active message context before publishing.
- [x] 5.2 Implement `publish_amqp` execution in `hmock.py`, rendering inline and file-backed payloads with the active message context before publishing.
- [x] 5.3 Add tests in `tests/test_hmock.py` for inline and file-backed `publish_kafka` rendering, including access to Kafka context variables.
- [x] 5.4 Add tests in `tests/test_hmock.py` for inline and file-backed `publish_amqp` rendering, including access to AMQP context variables.
- [x] 5.5 Run `uv run pytest` and confirm existing HTTP, admin, template, Redis, and new broker tests pass.
