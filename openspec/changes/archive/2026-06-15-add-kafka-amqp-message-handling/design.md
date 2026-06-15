## Context

`hmock.py` is currently an HTTP-oriented mock server that loads YAML definitions, validates `Behavior` objects, renders templates from a request context, and executes ordered actions such as `redis`, `send_http`, `sleep`, and `reply_http`. The existing contracts already separate definition loading, template rendering, and HTTP action execution, but the runtime data model assumes each concrete behavior has `expect.http.method` and `expect.http.path`.

Kafka and AMQP support introduces long-running consumers, outbound broker producers, broker-specific template contexts, and optional external client dependencies. The implementation needs to preserve the simple default startup path: when broker support is disabled, the server should behave as it does today and should not require a broker or broker client import.

## Goals / Non-Goals

**Goals:**
- Support opt-in Kafka and AMQP consume/publish behavior from the same YAML behavior model.
- Keep broker configuration deterministic and testable, including producer/consumer overrides and Kafka SASL/TLS resolution.
- Reuse the existing action ordering, template rendering, file-backed payload loading, values inheritance, and named template support.
- Make broker matching execute every matching behavior in loaded order for each consumed message.
- Isolate real broker clients behind adapters so unit tests can use fakes without requiring Kafka or RabbitMQ.

**Non-Goals:**
- Provide an embedded Kafka or AMQP broker.
- Add exactly-once delivery, transactions, consumer group management controls, or retry policy configuration beyond AMQP reconnect recovery.
- Add admin API or CLI surfaces for broker status in this change.
- Change HTTP matching semantics beyond allowing HTTP-triggered behaviors to publish broker messages.

## Decisions

### Use Explicit Broker Runtime Config Objects

Extend `Config` with Kafka and AMQP fields, plus helper structures for resolved Kafka producer and consumer settings. Kafka resolution should apply endpoint-specific overrides before evaluating SASL enablement so producer and consumer credentials can differ.

Alternative considered: pass raw environment values directly into consumers/producers. That would spread fallback and SASL rules through startup code and make config tests brittle.

### Split Behavior Triggers From Shared Actions

Introduce a runtime shape that can represent HTTP, Kafka, and AMQP triggers while preserving the existing shared `actions`, `condition`, `values`, and `templates`. HTTP matching can keep its current first-match behavior; broker matching should scan loaded behaviors and execute all matches in order.

Alternative considered: keep the current HTTP-only `Behavior` dataclass and bolt broker fields onto it. That would make message-only behaviors awkward because method/path are required today.

### Reuse One Action Executor With Trigger-Specific Context

Refactor action execution so `sleep`, `redis`, `send_http`, `publish_kafka`, and `publish_amqp` are shared actions executed against a supplied render context and dependency bundle. HTTP execution still interprets `reply_http`; broker-triggered execution should ignore or reject response-only assumptions according to validation.

Alternative considered: create separate action runners for HTTP, Kafka, and AMQP. That would duplicate ordering, Redis, outbound HTTP, and rendering behavior.

### Lazy Broker Client Adapters

Wrap Kafka and AMQP libraries in small adapter classes with methods for consuming referenced topics/queues and publishing rendered payloads. Import real client libraries only when the corresponding feature is enabled; tests can inject fake adapters and exercise matching/action logic in-process.

Alternative considered: call third-party client APIs directly from matching and action functions. That would make behavior tests depend on live brokers and make missing optional dependencies affect HTTP-only usage.

### Background Workers Managed By Server Lifetime

When enabled, start Kafka and AMQP consumer workers after mock definitions load and stop them during server shutdown. Workers should use snapshots from `MockState` so hot reload and API-added mocks can affect future message handling without restarting the process.

Alternative considered: start consumers during definition loading. That would couple validation to network I/O and make failed broker connections harder to recover from.

## Risks / Trade-offs

- Optional dependency drift -> Keep adapter interfaces small, import lazily, and fail fast with a clear error only when a broker feature is enabled.
- Broker workers and hot reload race -> Read behavior snapshots at message handling time and avoid mutating behavior objects during execution.
- Duplicate side effects from broker redelivery -> Preserve at-least-once semantics and document that mocks should be idempotent when brokers redeliver.
- AMQP reconnect loops can hide permanent configuration errors -> Log reconnect failures with exchange/routing/queue context and continue retrying only after initial setup succeeds.
- Kafka topic discovery from loaded mocks may miss topics added by API/hot reload if consumers are static -> Reconcile subscribed topics after mock set changes or have workers refresh subscriptions from the current snapshot.

## Migration Plan

No migration is required for existing HTTP-only users because both `HM_KAFKA_ENABLED` and `HM_AMQP_ENABLED` default to `false`. Rollback is disabling the corresponding feature flag or reverting the change; existing mock definition formats remain valid.
