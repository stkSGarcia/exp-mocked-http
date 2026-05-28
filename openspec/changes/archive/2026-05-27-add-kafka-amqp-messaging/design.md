## Context

hmock is a single-file Python mock server (`hmock.py`). It currently handles HTTP mocks and a Redis state backend. Behaviors are loaded from YAML files and stored in a shared `_BEHAVIORS` list protected by a lock. Each behavior has an `expect` block (matching rules) and an `actions` list (side-effects like `reply_http`, `send_http`, `redis`).

Adding Kafka and AMQP requires two new integration layers: (1) background consumers that receive messages and dispatch them against loaded behaviors, and (2) new action executors (`publish_kafka`, `publish_amqp`) that send outbound messages during behavior execution.

## Goals / Non-Goals

**Goals:**
- Kafka and AMQP consumers start on demand based on topics/queues referenced in loaded mocks
- `expect.kafka` and `expect.amqp` match messages against behaviors, executing all matches in loaded order
- `publish_kafka` and `publish_amqp` actions send messages as part of behavior execution
- Per-producer and per-consumer Kafka connection overrides (brokers, SASL, TLS)
- AMQP auto-setup (declare exchanges, queues, bindings on startup)
- AMQP auto-reconnect after transient disconnects
- Hot reload updates active subscriptions when mocks change

**Non-Goals:**
- Kafka consumer group coordination beyond single-instance use
- AMQP consumer acks/nacks or dead-letter handling
- Admin API endpoints for messaging state
- Message schema validation

## Decisions

### Kafka client: `aiokafka` over `kafka-python`
`aiokafka` is async-native and integrates naturally with an asyncio event loop running in a background thread. `kafka-python` is synchronous and would require thread-per-consumer management. Since AMQP (`aio-pika`) is also async, a shared asyncio loop keeps both integrations on the same concurrency model.

**Alternative considered**: `kafka-python` in threads — rejected because it complicates synchronization and doesn't compose with the async AMQP client.

### Single background asyncio event loop
Both Kafka and AMQP consumers run as coroutines in one background asyncio event loop (`asyncio.new_event_loop()`) started in a daemon thread at startup. This avoids two separate threading models and lets both integrations share connection lifecycle management.

**Alternative considered**: separate threads per broker — simpler but harder to coordinate restarts and subscription updates.

### Subscription update via `_trigger_reload`
The existing reload mechanism (`_trigger_reload` / `_reload_loop`) fires when mocks change. Kafka/AMQP consumers hook into this: after `_BEHAVIORS` updates, the integration layers compare the new set of required topics/queues against currently active subscriptions and start or stop consumers accordingly. No new notification mechanism is needed.

### Behavior execution model: "execute all matches"
Kafka and AMQP differ from HTTP (first match wins). The checkpoint spec mandates executing every matching behavior in loaded order. A dedicated `find_all_behaviors_for_kafka` / `find_all_behaviors_for_amqp` function iterates the full list, evaluating conditions, and returns all matches.

### AMQP queue defaulting
When `expect.amqp.queue` is omitted or empty, it defaults to the value of `routing_key`. This is resolved at mock-load time during `_assemble_behaviors`, so the consumer always has a concrete queue name.

### `payload_from_file` resolution
Both `publish_kafka.payload_from_file` and `publish_amqp.payload_from_file` follow the same load-and-snapshot pattern as `reply_http.body_from_file`: the file is read and stored in `_payload_snapshot` during `_validate_behavior`, using the same `templates_dir` root and path-escape check.

## Risks / Trade-offs

- [asyncio in a non-async codebase] Starting a background event loop in a daemon thread is unconventional. → Isolate it in a `_start_messaging_loop()` helper; never share the loop with the main thread.
- [aiokafka / aio-pika not in pyproject.toml] Must add dependencies; optional import at runtime to avoid breaking deployments that don't need messaging. → Guard with `if KAFKA_ENABLED` / `if AMQP_ENABLED` before importing.
- [subscription drift on reload] If reload fires while a consumer is mid-message, the consumer list may temporarily be stale. → Consumer threads hold a reference to the behavior list snapshot at dispatch time (same pattern as HTTP handler).
- [AMQP reconnect loop] `aio-pika` robust connections handle reconnect internally; manual retry loop only needed if the library's built-in reconnect is insufficient. → Use `aio_pika.connect_robust` and let the library handle it.
