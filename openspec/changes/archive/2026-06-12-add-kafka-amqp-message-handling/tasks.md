## 1. Dependencies and Configuration

- [x] 1.1 Add `kafka-python-ng` and `pika` runtime dependencies to `pyproject.toml` and refresh `uv.lock`.
- [x] 1.2 Extend `Config` and `load_config` in `hmock.py` with all Kafka and AMQP defaults and boolean validation, starting from the existing CORS/environment parsing pattern. [extends cors-response-policy/add-hot-reload-cors-binary-admin-cli]
- [x] 1.3 Add resolved Kafka producer/consumer settings helpers in `hmock.py` for broker-list parsing, role override fallback, independent TLS, and complete-pair SASL enablement.
- [x] 1.4 Extend configuration tests in `test_hmock.py` to cover defaults, every override family, producer/consumer independence, partial SASL credentials, and invalid booleans. [extends cors-response-policy/add-hot-reload-cors-binary-admin-cli]

## 2. Behavior Compilation and Payloads

- [x] 2.1 Extend behavior validation in `hmock.py` for `expect.kafka`, `expect.amqp`, required transport fields, and AMQP queue defaulting.
- [x] 2.2 Extend action preparation in `hmock.py` for `publish_kafka` and `publish_amqp`, including required fields and inline-versus-file payload validation.
- [x] 2.3 Generalize the safe text fixture loader in `hmock.py` so `payload_from_file` uses the existing templates-directory containment, load-time snapshot, rendering, and inline precedence rules. [extends http-yaml-mock-server/add-template-helpers-file-backed-bodies]
- [x] 2.4 Add compilation and fixture tests in `test_hmock.py` for valid definitions, missing fields, queue defaulting, path escape, missing files, snapshots, and inline payload precedence. [extends http-yaml-mock-server/add-template-helpers-file-backed-bodies]

## 3. Matching and Dispatch

- [x] 3.1 Add Kafka and AMQP context builders and list-returning match functions in `hmock.py` that evaluate conditions with behavior values and preserve loaded order.
- [x] 3.2 Add broker message dispatch functions in `hmock.py` that take one `runtime_snapshot()`, execute every match, and preserve the existing first-match HTTP path.
- [x] 3.3 Extend `execute_actions` in `hmock.py` with injectable Kafka and AMQP publishing helpers that render routing fields and selected payloads.
- [x] 3.4 Add `test_hmock.py` unit tests for transport context values, condition filtering, no-match behavior, multiple matches in loaded order, cross-transport actions, and rendered publishes.

## 4. Kafka Runtime

- [x] 4.1 Add Kafka producer and consumer adapters/factories in `hmock.py` using resolved role settings and injectable fake boundaries.
- [x] 4.2 Implement the Kafka worker in `hmock.py` to derive unique topics from current compiled behaviors, reconcile subscriptions after runtime changes, consume messages, and dispatch payloads. [extends http-yaml-mock-server/add-admin-api-template-persistence]
- [x] 4.3 Add Kafka worker lifecycle integration in `main()` so disabled Kafka creates no clients and enabled resources stop and close during shutdown.
- [x] 4.4 Add fake-client tests in `test_hmock.py` for client configuration, referenced-topic subscriptions, duplicate topic removal, runtime subscription changes, message dispatch, and shutdown.

## 5. AMQP Runtime

- [x] 5.1 Add AMQP connection/channel adapters and factories in `hmock.py` with injectable fake boundaries.
- [x] 5.2 Implement AMQP topology derivation and reconciliation in `hmock.py` to declare unique exchanges and queues, bind routing keys, and consume each resolved queue once. [extends http-yaml-mock-server/add-admin-api-template-persistence]
- [x] 5.3 Implement the stop-aware AMQP reconnect loop in `hmock.py` so transient failures close stale resources, reconnect, restore topology, and resume consumption.
- [x] 5.4 Add AMQP worker lifecycle integration in `main()` so disabled AMQP creates no connection and shutdown stops reconnects and closes active resources.
- [x] 5.5 Add fake-client tests in `test_hmock.py` for topology setup, duplicate resource handling, default queues, message metadata dispatch, transient reconnect recovery, and shutdown.

## 6. Verification

- [x] 6.1 Run `uv run pytest` and fix regressions across existing HTTP, admin, hot-reload, Redis, Kafka, and AMQP behavior.
- [x] 6.2 Run focused tests repeatedly to confirm broker tests do not require external services and have no timing-dependent failures.
- [x] 6.3 Review `hmock.py` logging paths to ensure broker connection, publish, consume, reconnect, and shutdown failures include transport and operation context without exposing SASL credentials.
