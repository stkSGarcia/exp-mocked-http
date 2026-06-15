## Context

`hmock.py` currently loads YAML behavior definitions, matches HTTP requests, renders templates with request context, and executes ordered actions such as Redis commands, outbound HTTP calls, sleeps, and HTTP replies. Kafka and AMQP support adds long-running background consumers, producer clients, and broker-specific template contexts while preserving the current behavior/action model and loaded-order semantics.

This change is opt-in: broker clients start only when their enabled flags are true. Existing HTTP behavior remains the default runtime surface, and existing mock definitions continue to load unchanged.

## Goals / Non-Goals

**Goals:**
- Add Kafka and AMQP runtime configuration with safe disabled-by-default behavior.
- Consume Kafka topics and AMQP queues declared by loaded mock definitions.
- Match broker messages against `expect.kafka` and `expect.amqp`, evaluate conditions with broker-specific template context, and execute every matching behavior in loaded order.
- Publish Kafka and AMQP messages from ordered actions with inline or file-backed payload templates.
- Keep broker action execution compatible with existing ordered actions, values, reusable templates, and Redis template functions.

**Non-Goals:**
- Implement broker admin APIs, topic creation for Kafka, dead-letter handling, delivery guarantees beyond client-library defaults, or exactly-once semantics.
- Add binary broker payload support; Kafka and AMQP payloads are modeled as strings for this change.
- Change HTTP matching semantics, where the first matching behavior still handles an HTTP request.

## Decisions

1. Represent broker expectations on the existing `Behavior` model instead of adding separate definition kinds.

   Rationale: broker mocks need inheritance, values, reusable templates, ordered actions, and duplicate-key handling just like HTTP mocks. Extending the effective behavior shape with optional HTTP, Kafka, and AMQP expectation metadata keeps loading and admin persistence consistent.

   Alternative considered: introduce `KafkaBehavior` and `AMQPBehavior` kinds. That would duplicate inheritance and action validation logic and complicate mixed actions.

2. Start broker workers from the runtime, not from request handlers.

   Rationale: Kafka and AMQP are background input streams. `HMockRuntime` already owns loaded mocks, reload state, Redis storage, and lifecycle concerns, so it is the right boundary for starting, stopping, and refreshing consumers.

   Alternative considered: build standalone broker loops outside the runtime. That would make hot reload and admin mutations harder to coordinate with the active behavior set.

3. Use client adapters around external Kafka and AMQP libraries.

   Rationale: the project can unit-test matching, payload rendering, action dispatch, reconnect, and configuration resolution without real brokers by injecting fake adapters. The adapters isolate dependency-specific APIs and keep the core runtime deterministic.

   Alternative considered: call client libraries directly from matching/action code. That would make tests depend on broker availability or broad mocking of third-party internals.

4. Resolve Kafka producer and consumer settings independently after shared defaults.

   Rationale: tests commonly use different credentials, brokers, or TLS modes for publish and consume paths. Applying override/fallback before deciding SASL enablement keeps partial credentials from enabling SASL accidentally.

   Alternative considered: one Kafka client configuration for both directions. That is simpler but does not satisfy the producer/consumer override contract.

5. Treat broker publish payloads like existing file-backed HTTP bodies.

   Rationale: `payload_from_file` should use the same templates-directory path safety, load-time snapshotting, and render-at-execution behavior as other `*_from_file` fields. Inline non-empty payloads take precedence over file-backed payloads to match the existing HTTP action pattern.

   Alternative considered: read payload files at publish time. That would make behavior execution depend on mutable files and differ from current snapshot semantics.

6. Execute every matching broker behavior in loaded order.

   Rationale: a single event can trigger multiple side effects, unlike HTTP where one selected behavior owns the response. Matching all broker behaviors enables fan-out test flows while keeping ordering deterministic.

   Alternative considered: stop at the first broker match. That would mirror HTTP but would not satisfy the event fan-out behavior requested for Kafka and AMQP.

## Risks / Trade-offs

- Broker client dependencies increase installation size and runtime startup paths. -> Keep broker features disabled by default and import/connect lazily only when enabled.
- Background consumers can race with reloads. -> Snapshot the active behavior list for each consumed message and use runtime locks only to retrieve that snapshot.
- Broker publish failures could interrupt unrelated actions. -> Log publish failures and continue action execution, matching outbound HTTP failure behavior unless a later requirement asks for hard failures.
- AMQP reconnect behavior can be flaky in tests if tied to wall-clock timing. -> Put reconnect loops behind adapter hooks and test retry decisions with fake adapters.
- Kafka topic discovery from loaded mocks can miss topics added by later admin mutations until consumers refresh. -> Refresh broker subscriptions after runtime reloads and admin mutations.

## Migration Plan

No migration is required for existing mock definitions because Kafka and AMQP are disabled by default and new fields are additive. Rollback consists of disabling `HM_KAFKA_ENABLED` and `HM_AMQP_ENABLED` or reverting the change; existing HTTP mocks remain valid.

## Open Questions

- Which Kafka and AMQP Python client libraries should be preferred for the final implementation environment?
- Should broker publish failures remain log-and-continue permanently, or should a future change add configurable failure policy?
