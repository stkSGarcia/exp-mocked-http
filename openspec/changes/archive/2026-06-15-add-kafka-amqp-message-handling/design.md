## Context

The current project is a compact Python mock server centered in `hmock.py`. It loads YAML mock definitions into `Behavior` objects, validates actions in one place, renders templates with a shared context/function engine, serves HTTP requests through `ThreadingHTTPServer`, and keeps active mock snapshots in `HMockRuntimeState`.

This change adds asynchronous broker triggers beside the existing HTTP trigger. Kafka and AMQP support must be optional, must preserve current startup behavior when disabled, and must reuse existing behavior ordering, inheritance, values, template functions, file-backed text fixture rules, and action order sorting wherever possible.

## Goals / Non-Goals

**Goals:**
- Add Kafka and AMQP runtime configuration with the exact environment variables and defaults from the checkpoint.
- Allow loaded behaviors to match Kafka messages by topic and optional condition, then execute every matching behavior in loaded order.
- Allow loaded behaviors to match AMQP messages by exchange, routing key, queue, and optional condition, then execute every matching behavior in loaded order.
- Add `publish_kafka` and `publish_amqp` actions that render inline or file-backed payloads with the active trigger context.
- Keep broker dependencies inactive unless their corresponding enable flag is true.
- Recover AMQP consumption after transient disconnects.

**Non-Goals:**
- Add a general streaming abstraction beyond Kafka and AMQP.
- Add broker administration APIs to `omctl` or the admin HTTP API.
- Add binary broker payload fields; this change covers string payloads and text `payload_from_file`.
- Guarantee exactly-once broker processing; the mock server will provide best-effort test-fixture behavior.

## Decisions

### Keep broker support optional and adapter-based

Introduce small Kafka and AMQP adapter interfaces around connect, consume, publish, setup, and close operations. Production adapters can wrap client libraries, while tests can inject in-memory adapters without requiring real brokers. `HM_KAFKA_ENABLED=false` and `HM_AMQP_ENABLED=false` leave adapters unconstructed and preserve current HTTP-only behavior.

Alternative considered: directly import client libraries in the main request/action path. That would make disabled broker support harder to test and could fail startup in environments that only need HTTP mocks.

### Extend `Config` with resolved producer and consumer settings

Add Kafka shared defaults, producer overrides, consumer overrides, and AMQP URL to `Config`. Resolve producer and consumer broker lists, TLS flags, and SASL credentials during configuration loading so downstream code receives explicit effective settings. Evaluate SASL enablement separately for producer and consumer after fallback resolution.

Alternative considered: resolve fallbacks inside each adapter call. Central resolution keeps environment parsing testable and avoids mismatched producer/consumer behavior.

### Generalize behavior triggers without replacing HTTP matching

Keep the existing HTTP matching path intact, but extend `Behavior` to carry optional `kafka` and `amqp` expectation data in addition to HTTP method/path data. HTTP behaviors continue to require `expect.http`; Kafka and AMQP behaviors require their respective expectation blocks. Broker consumer loops filter only behaviors that declare the matching broker expectation.

Alternative considered: split `Behavior` into separate HTTP/Kafka/AMQP classes. A single behavior model better preserves inheritance, values, templates, duplicate-key replacement, and ordered action execution.

### Reuse ordered action execution with trigger-specific contexts

Move the reusable action loop behind a helper that accepts a template context and an optional HTTP response accumulator. HTTP requests still return `reply_http` responses; broker-triggered executions ignore `reply_http` response output if present but continue to execute publish, Redis, outbound HTTP, and sleep actions in order. `publish_kafka` and `publish_amqp` actions use the same render-and-continue failure posture as `send_http`: publish failures are logged and do not stop later actions.

Alternative considered: implement separate broker-only action executors. That risks diverging ordering, templating, and error behavior from HTTP-selected behaviors.

### Start broker consumers from runtime state lifecycle

Attach a lightweight `BrokerRuntime` to `HMockRuntimeState` or the server startup path. On startup, it snapshots active behaviors, derives Kafka topics and AMQP bindings, starts background consumer threads when enabled, and uses runtime-state snapshots before each message match so hot reload and admin mutations become visible to broker processing. Shutdown closes adapters and stops loops.

Alternative considered: start consumers directly in `load_active_snapshot`. Loading should stay pure validation/snapshot work; long-running network loops belong to runtime lifecycle.

### AMQP setup is declarative and idempotent

On startup, gather all loaded AMQP expectations, default empty or missing `queue` to `routing_key`, declare exchanges/queues as needed, and bind each queue to its exchange/routing key before consuming. Repeat setup after reconnect.

Alternative considered: require users to pre-create AMQP resources. The checkpoint asks for auto-setup, and declarative setup makes local test environments less brittle.

## Risks / Trade-offs

- Broker client libraries may not be available in minimal environments -> gate imports behind enable flags and keep adapter tests independent from external services.
- Background consumer loops can race with hot reload or admin mutations -> fetch runtime snapshots per message and hold runtime locks only while copying active data.
- Kafka topic discovery from loaded mocks can change after reload -> rebuild subscribed topics when the active snapshot signature changes or restart the Kafka consumer on topic-set changes.
- AMQP reconnect can duplicate bindings or consumers -> make setup idempotent and ensure reconnect closes stale channel resources before resubscribing.
- Broker-triggered behaviors executing `reply_http` have no response channel -> allow validation for inherited/shared actions but ignore the response output during broker execution.

## Migration Plan

No breaking migration is required. Existing users keep HTTP-only behavior because Kafka and AMQP are disabled by default. Enabling either broker requires setting the corresponding enable flag and providing broker-specific connection settings only when defaults are not suitable.
