## Context

`hmock.py` is a single-process mock server with a shared mock collection, template engine, HTTP admin API, optional Kafka/AMQP workers, and action execution helpers. Behaviors currently resolve to exactly one trigger among HTTP, Kafka, and AMQP, then render conditions and actions with a channel-specific context.

This change adds a fourth trigger, `grpc`, and a dry-run admin endpoint. gRPC differs from existing channels because matching uses protobuf service/method metadata while payload rendering requires descriptor-driven conversion between length-prefixed protobuf messages and JSON. The evaluation endpoint should reuse the same matching, condition, ordering, and rendering behavior as runtime paths while deliberately replacing all side effects with render-only results.

## Goals / Non-Goals

**Goals:**
- Add opt-in cleartext HTTP/2 gRPC serving without changing default HTTP/admin startup behavior.
- Use configured protobuf descriptor sets to decode inbound request messages to JSON and encode rendered JSON replies to response messages.
- Extend behavior validation, matching, action execution, and template context with `expect.grpc` and `reply_grpc`.
- Add `POST /api/v1/evaluate` for a single mock definition plus simulated HTTP, Kafka, AMQP, or gRPC context.
- Share matching and rendering helpers between live runtime paths and dry-run evaluation so behavior remains consistent.

**Non-Goals:**
- TLS, reflection, code generation from `.proto` files, streaming RPCs, and bidirectional streams.
- Executing Redis, outbound HTTP, Kafka, AMQP, sleeps, or gRPC network side effects during evaluation.
- Returning dry-run result types for every existing action; only `reply_http` and `publish_kafka` are included initially.

## Decisions

1. Add gRPC as a first-class behavior trigger.

   `Behavior` should gain `grpc_service` and `grpc_method`, and `_expect_trigger` should include `grpc` in the exactly-one-trigger check. This keeps gRPC matching aligned with the current HTTP/Kafka/AMQP model and avoids a parallel mock schema.

   Alternative considered: treat gRPC as HTTP/2 path matching. That would leak transport details into mock definitions and would not give templates stable protobuf service/method names.

2. Use descriptor sets at startup when gRPC behaviors require them.

   `HM_GRPC_DESCRIPTOR_SET_PATHS` should resolve comma-separated files relative to `HM_TEMPLATES_DIR` when not absolute. Startup should fail when gRPC is enabled, loaded behaviors include `expect.grpc` or `reply_grpc`, and descriptor config is missing, unreadable, invalid, or does not include the configured service/method messages. Startup can succeed without descriptors when gRPC is enabled but no loaded behavior needs protobuf descriptors.

   Alternative considered: load descriptors lazily on the first gRPC request. Startup validation gives faster feedback and matches existing load-time validation for file-backed payloads.

3. Use a small gRPC runtime adapter boundary.

   Keep descriptor loading, length-prefixed frame parsing/writing, protobuf JSON conversion, and HTTP/2 cleartext serving behind helper classes/functions. Core behavior matching and action rendering should remain independent of the transport library so tests can cover matching/rendering without opening sockets.

   Alternative considered: embed all protobuf handling directly in request handlers. That would make evaluation and unit tests harder to keep in sync with runtime behavior.

4. Reuse action rendering through a dry-run evaluator.

   Add evaluator helpers that build the same channel template context as live paths, check channel match before condition rendering, sort actions by existing order rules, and render only allowed dry-run result types. Side-effecting actions should be skipped in evaluation rather than executed against fake adapters.

   Alternative considered: simulate side effects with in-memory adapters. Skipping keeps the endpoint safe and preserves the contract that no side effects occur.

5. Keep evaluation request context as one merged object.

   The admin endpoint should accept `context` as a single object with optional `http_context`, `kafka_context`, `amqp_context`, and `grpc_context` members. The evaluator merges provided channel contexts into the template context for rendering, but requires the matching channel context for the declared trigger.

   Alternative considered: accept an array of contexts. A single object is simpler for clients and matches the checkpoint requirement.

## Risks / Trade-offs

- Descriptor/protobuf dependency behavior can vary across Python packages -> isolate it behind helpers and add tests with a generated descriptor fixture.
- Cleartext HTTP/2 support is not available in the standard `http.server` stack -> select a focused dependency and keep the existing HTTP mock server unchanged.
- Evaluation can drift from live execution if it forks rendering logic -> centralize context builders, matchers, payload-source rendering, and action ordering.
- gRPC payload JSON conversion errors can be hard to diagnose -> surface validation/startup errors with service, method, and descriptor path details.
- Startup should remain lightweight when gRPC is disabled -> gate descriptor parsing and gRPC server construction behind `HM_GRPC_ENABLED`.

## Migration Plan

No migration is required for existing users because gRPC is disabled by default and existing HTTP, Kafka, AMQP, and admin endpoints keep their current schema. Rollback consists of disabling `HM_GRPC_ENABLED` and avoiding `reply_grpc`/`expect.grpc` definitions until the code is reverted.
