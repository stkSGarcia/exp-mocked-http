## Context

`hmock.py` currently owns configuration, YAML compilation, template rendering, action execution, runtime reload, HTTP serving, and process lifecycle. Behaviors are stored in loaded order and HTTP matching selects the first match, while the new broker transports must execute all matching behaviors. The change also introduces long-lived external clients, dynamic subscriptions derived from runtime definitions, reconnect behavior, and two new dependencies.

## Related Work

> **`cors-response-policy/add-hot-reload-cors-binary-admin-cli`**: Defines environment boolean configuration and runtime feature enablement — informs reuse of `_parse_bool`, disabled-by-default broker startup, and managed shutdown because the prior change established optional runtime services controlled by environment settings.

> **`http-yaml-mock-server/add-template-helpers-file-backed-bodies`**: Defines template rendering and safe, snapshotted file-backed bodies — informs the shared payload loader and inline-payload precedence because publish payloads must behave like existing `*_from_file` action fields.

> **`http-yaml-mock-server/add-admin-api-template-persistence`**: Defines compilation and installation of persisted runtime definitions — informs deriving subscriptions and AMQP topology from `runtime_snapshot()` because admin and reload operations can replace the active behavior set.

## Goals / Non-Goals

**Goals:**

- Add optional Kafka and AMQP consume/publish support without changing existing HTTP behavior.
- Preserve existing behavior values, conditions, templates, action ordering, and file security rules.
- Execute all matching broker behaviors deterministically in loaded order.
- Reconcile broker consumption with the currently installed runtime.
- Make broker code unit-testable without running Kafka or RabbitMQ.

**Non-Goals:**

- Broker administration beyond resources directly required by loaded mocks.
- Kafka key, headers, partitions, consumer groups, or delivery-semantics configuration beyond the checkpoint.
- AMQP exchange type, durability, acknowledgement, prefetch, or message-property customization.
- Cross-process coordination of subscriptions or AMQP topology.

## Decisions

### Use dedicated client adapters

Define narrow Kafka producer/consumer and AMQP connection/channel adapter boundaries in `hmock.py`. Production factories wrap `kafka-python-ng` and `pika`; tests inject fakes that record configuration, subscriptions, topology calls, publishes, disconnects, and closes.

This keeps optional transport details out of matching and action execution and permits deterministic tests without broker containers. Directly calling third-party clients throughout the module was rejected because it would couple validation, lifecycle, and tests to library-specific objects.

### Represent resolved Kafka roles explicitly

Extend `Config` with raw shared and role-specific Kafka values, then resolve immutable producer and consumer settings through one helper. Empty role-specific strings mean fallback to shared values. Broker lists are split on commas and trimmed. SASL is enabled only after resolution and only when both credentials are non-empty; TLS is resolved independently per role.

This mirrors established environment parsing conventions _(see `cors-response-policy/add-hot-reload-cors-binary-admin-cli`)_ and prevents a partial producer override from accidentally changing consumer authentication.

### Compile transport-specific behavior metadata

During `_validate_behavior`, validate `expect.kafka` and `expect.amqp`, normalize AMQP's empty queue to its routing key, and prepare publish actions. File-backed payload preparation reuses the existing templates-directory containment and snapshot rules with field-specific error messages _(see `http-yaml-mock-server/add-template-helpers-file-backed-bodies`)_.

The compiled behavior remains the single source for HTTP, Kafka, and AMQP matching. Separate `find_kafka_behaviors` and `find_amqp_behaviors` functions return lists rather than changing `find_behavior`, preserving HTTP first-match semantics.

### Dispatch broker messages through the existing executor

Build transport contexts containing only the specified Kafka or AMQP fields, then add each matched behavior's `Values` before evaluating its condition and executing its actions. For each message, iterate a stable `runtime_snapshot()` so a concurrent reload cannot reorder or replace behaviors midway through dispatch.

The existing `execute_actions` function gains `publish_kafka` and `publish_amqp` branches. Publisher handles are installed in a process-level runtime service registry and are accessed through small publishing helpers; disabled or unavailable clients produce a logged warning rather than crashing an HTTP or broker worker.

### Reconcile consumers with runtime snapshots

Kafka and AMQP workers run in daemon threads managed by `main()`. Each worker tracks a signature of the transport expectations in `runtime_snapshot()` and reconciles when that signature changes:

- Kafka updates the consumer's unique topic subscription.
- AMQP ensures unique exchanges, queues, and bindings, then consumes each resolved queue once.

Using runtime snapshots extends the existing reload and admin mutation model _(see `http-yaml-mock-server/add-admin-api-template-persistence`)_ without adding callbacks to every runtime installation path. A short worker polling interval is acceptable for this single-process mock server.

### Reconnect AMQP in the worker loop

The AMQP worker owns connection creation in a retry loop. A transient connection or consumption exception closes the stale connection, waits with a stop-aware bounded delay, reconnects, re-declares topology, and restores consumers. Shutdown sets a stop event before closing the connection so no new reconnect starts.

Embedding reconnect in callbacks was rejected because callback ownership varies by AMQP client state and is harder to stop and test reliably.

### Keep processing synchronous and ordered

Each consumer worker dispatches one message at a time and runs all matched behaviors serially. This guarantees loaded-order execution and avoids requiring thread-safety guarantees from action implementations. The trade-off is lower throughput, which is acceptable for a mock server focused on deterministic tests.

## Risks / Trade-offs

- [A slow action blocks further messages on that transport] -> Keep dispatch synchronous for deterministic ordering and document the behavior; users can run separate mock instances for parallelism.
- [Runtime changes may take one reconciliation interval to affect subscriptions] -> Use a short stop-aware interval and reconcile immediately after connection.
- [Kafka and AMQP libraries expose different failure modes] -> Translate them at adapter boundaries, log transport and operation context, and keep worker retry loops broad enough to survive transient client exceptions.
- [Publishing from a behavior triggered by the same topic or queue can create loops] -> Do not add implicit loop prevention; mock authors control routing and conditions.
- [AMQP redeclaration can conflict with incompatible pre-existing resources] -> Surface the broker error and retry rather than attempting destructive reconciliation.
- [New dependencies increase install size and maintenance] -> Use maintained pure-Python clients and pin only compatible lower bounds in project metadata.

## Migration Plan

1. Add dependencies and configuration fields while both transports remain disabled by default.
2. Add validation, matching, adapters, publishing helpers, and mocked-client tests.
3. Start and stop workers from `main()` only when enabled.
4. Deploy with existing configuration unchanged; no broker connections occur.
5. Enable one transport at a time and provide reachable broker settings.

Rollback consists of disabling `HM_KAFKA_ENABLED` and `HM_AMQP_ENABLED` or reverting the change. Existing HTTP-only definitions remain valid throughout.

## Open Questions

None. Delivery acknowledgements, Kafka consumer-group policy, and advanced broker properties remain intentionally outside this checkpoint.
