## Context

`hmock.py` currently owns configuration loading, mock validation, template rendering, HTTP/admin request handling, broker dispatch, and action execution. The existing tests in `tests/test_hmock.py` exercise HTTP mocks, template helpers, action ordering, Kafka/AMQP dispatch, admin storage, and side-effect actions.

This change adds a second runtime protocol, gRPC over HTTP/2 cleartext, and a new admin-style endpoint that previews matching/rendering without mutating state. The design should reuse the existing behavior model and renderer as much as possible so gRPC and evaluation do not grow into separate mock engines.

## Related Work

**`kafka-message-handling/add-kafka-amqp-message-handling`**: Defines message-channel runtime configuration, matching, context, and broker action behavior — informs the gRPC dispatch shape and first-match behavior because this change adds another non-HTTP channel with request-derived context.

**`template-rendering/add-admin-template-storage`**: Protects template rendering side effects in managed storage contexts — informs the evaluation endpoint's no-side-effects execution mode because evaluation must render selected outputs without mutating Redis, brokers, HTTP targets, or storage.

**`http-behavior-mocking/add-template-helpers-file-backed-bodies`**: Defines file-backed HTTP response bodies and request-derived helpers — informs `reply_grpc.payload_from_file` because gRPC replies need the same file resolution and template rendering conventions.

**`template-rendering/add-reusable-templates-inheritance-values-action-ordering`**: Defines reusable templates, inherited values, and ordered action rendering — informs evaluation action sorting because dry-run output must match runtime action order.

**`template-rendering/add-http-yaml-mock-server`**: Defines shared template context for conditions, response bodies, and headers — informs gRPC and evaluation context construction because both should render through the same template engine.

**`mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`**: Defines reusable template definitions and action ordering in loaded mocks — informs schema validation and action ordering because `expect.grpc`, `reply_grpc`, and evaluation should participate in the same loaded behavior model.

**`template-hot-reload/add-hot-reload-cors-binary-cli`**: Defines environment-driven runtime configuration and startup behavior — informs the gRPC config fields and descriptor validation because gRPC should fail fast only when configured behavior requires descriptors.

**`mock-definition-loading/add-http-yaml-mock-server`**: Defines base config and YAML mock loading — informs new gRPC schema fields because existing mocks must continue loading unchanged.

**`mock-definition-loading/add-stateful-actions`**: Defines stateful action extensions — informs dry-run behavior because evaluation must explicitly omit or simulate side-effecting actions without executing them.

## Goals / Non-Goals

**Goals:**

- Add config, validation, and runtime support for optional cleartext gRPC serving.
- Add descriptor-set loading and protobuf JSON conversion for configured service methods.
- Add `expect.grpc`, gRPC template context values, and `reply_grpc`.
- Add `POST /api/v1/evaluate` for side-effect-free matching, condition rendering, and supported action rendering.
- Reuse existing behavior validation, action ordering, template rendering, and file-backed payload helpers where possible.

**Non-Goals:**

- TLS, mTLS, reflection, or dynamic descriptor discovery.
- Streaming gRPC requests or responses.
- Executing any side effects during evaluation.
- Returning dry-run result payloads for action types other than `reply_http` and `publish_kafka`.
- Splitting `hmock.py` into multiple modules as part of this change.

## Decisions

### Add gRPC config as nested runtime config

Add a `GRPCConfig` dataclass and a `grpc` field on `Config`, mirroring `AMQPConfig`. `load_config()` reads `HM_GRPC_ENABLED`, `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS`, with descriptor paths stored as a tuple of raw configured values. Relative descriptor paths are resolved later against `Config.templates_dir` so validation can report the exact source path. _(see `mock-definition-loading/add-http-yaml-mock-server`, `template-hot-reload/add-hot-reload-cors-binary-cli`)_

Alternative considered: flat fields on `Config`. A nested dataclass keeps the optional listener state grouped and avoids further widening the top-level config shape.

### Extend `Behavior` with gRPC fields

Add `grpc_service`, `grpc_method`, and a way to identify `reply_grpc` actions during validation. `validate_behavior()` should accept `expect.grpc` alongside HTTP, Kafka, and AMQP expectations, requiring both service and method. `_validate_actions()` should validate `reply_grpc.payload`, `payload_from_file`, and `headers`, reusing `_validate_text_payload_source()` and `_validate_headers_mapping()` with gRPC-specific field names. _(see `mock-definition-loading/add-reusable-templates-inheritance-values-action-ordering`)_

Alternative considered: keep raw gRPC expectation only in `Behavior.expect`. Explicit fields match the existing Kafka/AMQP shape and make dispatch/evaluation simpler.

### Use a small protobuf descriptor adapter

Introduce a descriptor registry helper that loads configured descriptor-set files, resolves `(service, method)` to request/response message descriptors, and exposes `decode_request()` and `encode_response()` helpers. Keep gRPC frame parsing and serialization close to this adapter so the listener code deals in JSON strings and response bytes. _(see `kafka-message-handling/add-kafka-amqp-message-handling`)_

Alternative considered: shell out to `protoc` or require generated Python modules. Descriptor-set loading is more portable for local mocks and matches the checkpoint's configuration model.

### Add gRPC as an optional side listener

Keep `HMockHTTPServer` and `HMockAdminHTTPServer` unchanged for HTTP/admin traffic, and add a `HMockGRPCServer` or equivalent thread-managed component started only when `config.grpc.enabled` is true. The listener receives the shared `HMockRuntimeState`, evaluates loaded behaviors in order, builds gRPC template context, runs conditions, and returns `reply_grpc` output. _(see `mock-definition-loading/add-http-yaml-mock-server`)_

Alternative considered: route gRPC through the existing `BaseHTTPRequestHandler`. Python's standard HTTP server does not provide HTTP/2 handling, so gRPC needs a protocol-specific server path.

### Centralize dry-run evaluation

Add pure helper functions for `evaluate_behavior(mock, context, state)` and channel-specific match checks. The admin handler's `POST /api/v1/evaluate` endpoint should validate the request, turn the single mock into a validated `Behavior`, merge simulated channel contexts into the template context, check matching before rendering conditions, and render only `reply_http` and `publish_kafka` dry-run results. Unsupported actions are skipped and side-effecting helpers are not called. _(see `template-rendering/add-admin-template-storage`, `mock-definition-loading/add-stateful-actions`)_

Alternative considered: invoke `_run_behavior_actions()` with fake publishers. A dedicated dry-run path is clearer and avoids accidental Redis, HTTP, broker, sleep, or storage side effects.

### Reuse action ordering and render helpers

Evaluation and gRPC dispatch should use `_sort_actions()`, `_render_text_payload()`, `render_template()`, and existing file-backed payload snapshot fields where applicable. HTTP dry-run results should use the same body/header/content-length rules as runtime HTTP replies. _(see `template-rendering/add-reusable-templates-inheritance-values-action-ordering`, `http-behavior-mocking/add-template-helpers-file-backed-bodies`)_

Alternative considered: duplicate rendering in the endpoint. Reusing helpers reduces drift between previewed and runtime behavior.

## Risks / Trade-offs

- [Risk] Python gRPC/HTTP2 support may require an additional dependency not currently present in the repo -> Mitigation: isolate dependency use behind a small server/descriptor adapter and keep unit tests focused on pure helpers where possible.
- [Risk] Descriptor-set parsing errors can be hard to understand -> Mitigation: validate descriptors at startup when gRPC behaviors require them and include the configured path and service/method in errors.
- [Risk] Evaluation could accidentally execute side-effect actions if it reuses runtime action execution too directly -> Mitigation: implement a dedicated dry-run renderer that whitelists `reply_http` and `publish_kafka`.
- [Risk] Merged channel contexts may create ambiguous template values -> Mitigation: preserve existing channel-specific names (`HTTPBody`, `KafkaPayload`, `AMQPPayload`, `GRPCPayload`) and only merge documented sub-objects.
- [Risk] gRPC support may be mistaken for production-grade service emulation -> Mitigation: explicitly document unary, cleartext, descriptor-set-backed behavior only.

## Migration Plan

1. Ship gRPC disabled by default.
2. Add validation for new schema fields while preserving existing HTTP, Kafka, and AMQP definitions.
3. Deploy `/api/v1/evaluate` without changing existing admin endpoints.
4. Roll back by disabling `HM_GRPC_ENABLED`; existing mocks and admin APIs remain compatible unless they depend on newly added fields.

## Open Questions

- Which gRPC/protobuf Python package should be used in implementation, and is adding that dependency acceptable for the target runtime?
- Should evaluation return structured validation details beyond `400 Bad Request` text in a later change?
