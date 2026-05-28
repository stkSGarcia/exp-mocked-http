## 1. Dependencies and Configuration

- [x] 1.1 Add `aiokafka` and `aio-pika` to `pyproject.toml` dependencies
- [x] 1.2 Add Kafka shared env vars to hmock.py config block: `HM_KAFKA_ENABLED`, `HM_KAFKA_CLIENT_ID`, `HM_KAFKA_SEED_BROKERS`, `HM_KAFKA_SASL_USERNAME`, `HM_KAFKA_SASL_PASSWORD`, `HM_KAFKA_TLS_ENABLED`
- [x] 1.3 Add Kafka per-role override env vars: `HM_KAFKA_PRODUCER_SEED_BROKERS`, `HM_KAFKA_CONSUMER_SEED_BROKERS`, `HM_KAFKA_SASL_PRODUCER_USERNAME`, `HM_KAFKA_SASL_PRODUCER_PASSWORD`, `HM_KAFKA_SASL_CONSUMER_USERNAME`, `HM_KAFKA_SASL_CONSUMER_PASSWORD`, `HM_KAFKA_TLS_PRODUCER_ENABLED`, `HM_KAFKA_TLS_CONSUMER_ENABLED`
- [x] 1.4 Add AMQP env vars: `HM_AMQP_ENABLED`, `HM_AMQP_URL`
- [x] 1.5 Implement `_resolve_kafka_role_config(role)` helper that applies override/fallback logic and returns resolved brokers, SASL credentials, and TLS flag; evaluates SASL enablement after resolving credentials

## 2. Mock Validation Extensions

- [x] 2.1 Extend `_validate_behavior` to accept `publish_kafka` and `publish_amqp` as valid action types
- [x] 2.2 Add `publish_kafka` validation: require `topic`; require `payload` or `payload_from_file`; snapshot `payload_from_file` contents using same path-escape rules as `body_from_file`
- [x] 2.3 Add `publish_amqp` validation: require `exchange` and `routing_key`; require `payload` or `payload_from_file`; snapshot `payload_from_file` contents
- [x] 2.4 In `_assemble_behaviors`, default `expect.amqp.queue` to `expect.amqp.routing_key` when queue is omitted or empty

## 3. Kafka Action Executor

- [x] 3.1 Implement `execute_publish_kafka(cfg, context)` that renders the payload template (or uses snapshot) and publishes to the configured topic via the shared Kafka producer
- [x] 3.2 Wire `publish_kafka` into `execute_actions` dispatch

## 4. Kafka Consumer and Dispatcher

- [x] 4.1 Implement `find_all_behaviors_for_kafka(behaviors, topic, context)` that returns all behaviors whose `expect.kafka.topic` matches and whose `expect.condition` passes (execute-all semantics)
- [x] 4.2 Implement async Kafka consumer coroutine: on each message build KafkaTopic/KafkaPayload context, call `find_all_behaviors_for_kafka`, execute actions for each match in order
- [x] 4.3 Implement `_collect_kafka_topics(behaviors)` that returns the set of topics referenced by `expect.kafka.topic` in loaded behaviors
- [x] 4.4 Implement subscription management: compare active subscriptions to required topics after each reload, start consumers for new topics, stop consumers for removed topics
- [x] 4.5 Start background asyncio event loop in daemon thread and launch Kafka consumer tasks when `HM_KAFKA_ENABLED=true`

## 5. AMQP Action Executor

- [x] 5.1 Implement `execute_publish_amqp(cfg, context)` that renders the payload and publishes to the configured exchange and routing key via the shared AMQP channel
- [x] 5.2 Wire `publish_amqp` into `execute_actions` dispatch

## 6. AMQP Consumer and Auto-Setup

- [x] 6.1 Implement `find_all_behaviors_for_amqp(behaviors, exchange, routing_key, queue, context)` that returns all matching behaviors (execute-all semantics)
- [x] 6.2 Implement async AMQP startup routine: for each `expect.amqp` definition, declare exchange (topic type), declare queue, bind queue to exchange with routing key
- [x] 6.3 Implement async AMQP consumer coroutine per queue: on each message build AMQP context vars, call `find_all_behaviors_for_amqp`, execute actions for each match
- [x] 6.4 Use `aio_pika.connect_robust` for automatic reconnection on transient disconnects
- [x] 6.5 Start AMQP setup and consumers in the shared background asyncio event loop when `HM_AMQP_ENABLED=true`

## 7. Reload Integration

- [x] 7.1 After each `_reload_loop` update to `_BEHAVIORS`, notify the messaging layer to reconcile Kafka topic subscriptions and AMQP queue consumers

## 8. Tests

- [x] 8.1 Add unit tests for `_resolve_kafka_role_config`: override wins, fallback to shared, SASL disabled when password empty
- [x] 8.2 Add unit tests for `_validate_behavior` with `publish_kafka` and `publish_amqp` actions (valid and invalid cases)
- [x] 8.3 Add unit tests for `find_all_behaviors_for_kafka`: topic match, condition filter, execute-all ordering
- [x] 8.4 Add unit tests for `find_all_behaviors_for_amqp`: queue/exchange/routing_key match, condition filter, execute-all ordering
- [x] 8.5 Add unit tests for AMQP queue defaulting to routing_key in `_assemble_behaviors`
