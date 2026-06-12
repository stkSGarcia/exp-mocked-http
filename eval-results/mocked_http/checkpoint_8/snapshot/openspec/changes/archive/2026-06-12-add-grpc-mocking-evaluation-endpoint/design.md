## Context

`hmock.py` currently owns environment configuration, behavior validation and assembly, immutable runtime snapshots, HTTP/admin servers, Kafka and AMQP workers, template context construction, channel matchers, and ordered action execution. Runtime actions mix pure rendering with side-effecting operations, so evaluation cannot safely reuse `execute_actions` directly. gRPC also requires HTTP/2 transport plus dynamic protobuf request and response types that are not present in the current dependency set.

The new endpoint belongs on the existing admin HTTP listener because the other `/api/v1/*` management APIs are routed by `AdminRequestHandler`. The gRPC listener is separately enabled and must share the same runtime snapshots and template engine as the existing transports.

## Related Work

> **`http-yaml-mock-server/add-http-yaml-mock-server`**: Defines environment-driven server startup and active-load-order HTTP matching — informs the optional gRPC listener and first-match selection because the original change established one declarative runtime shared by request transports.

> **`http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`**: Defines concrete behavior assembly, inherited values, and ordering — informs gRPC behavior selection and evaluation-time preparation because only assembled concrete behaviors should be executable.

> **`http-yaml-mock-server/add-template-helpers-file-backed-bodies`**: Defines template rendering and file-backed response content — informs `reply_grpc` preparation and dry-run rendering because new outputs must behave consistently with existing templated actions.

## Goals / Non-Goals

**Goals:**

- Serve unary gRPC mocks over insecure HTTP/2 using descriptor-set-defined input and output message types.
- Keep gRPC matching, context construction, condition rendering, and action ordering consistent with existing channels.
- Validate and evaluate one supplied mock against one merged simulated context without installing it into runtime state.
- Make it structurally impossible for evaluation to invoke side-effecting action implementations.
- Preserve default startup behavior when gRPC is disabled or unused.

**Non-Goals:**

- TLS, reflection, generated protobuf modules, streaming RPCs, compression, or gRPC-Web.
- Persisting evaluation requests or changing active runtime definitions.
- Returning dry-run results for action types other than `reply_http` and `publish_kafka`.
- Refactoring the single-module application into a package as part of this change.

## Decisions

### Use grpcio with dynamic protobuf messages

Add explicit `grpcio` and `protobuf` dependencies. Start a `grpc.Server` with `add_insecure_port`, which supplies HTTP/2 cleartext transport and standard gRPC message framing without custom socket or HTTP/2 parsing. Register a generic RPC handler whose identity serializers expose request and response protobuf bytes; the handler resolves `/fully.qualified.Service/Method` through a descriptor registry and uses `google.protobuf.json_format` plus dynamic message classes for JSON conversion.

This avoids generated source files and directly supports descriptor sets. Implementing HTTP/2 and gRPC framing with a lower-level library would add protocol state, flow control, trailers, and interoperability risk without adding required behavior. _(see `http-yaml-mock-server/add-http-yaml-mock-server`)_

### Build one immutable descriptor registry

Parse all configured `FileDescriptorSet` files into a `DescriptorPool`, account for inter-file dependencies, and index methods by `(service full name, method name)`. Resolve relative paths against `HM_TEMPLATES_DIR`. Build the registry before listeners or workers start, and fail startup when active gRPC behavior requires a registry that cannot be built.

When descriptors are configured but no gRPC behavior is active, invalid configuration may still be reported because the operator explicitly requested descriptor loading. When no descriptors are configured and no active behavior needs them, retain an empty registry and allow startup. Runtime/admin updates that introduce gRPC behavior must validate against the existing registry and reject unresolved methods rather than partially installing a runtime.

### Extend existing behavior preparation

Validate `expect.grpc.service` and `expect.grpc.method` in `_validate_behavior`, prepare `reply_grpc.payload_from_file` with the existing text-file path restrictions, and require exactly one payload source. Keep sorted actions and inherited values unchanged. Add a gRPC matcher that scans assembled concrete behaviors in active load order and returns the first structural service/method match whose condition passes. _(see `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`)_

### Keep gRPC transport adaptation separate from action rendering

Create a gRPC request context from service, method, decoded JSON, and invocation metadata. A transport handler obtains a runtime snapshot, selects the behavior, and runs a gRPC-aware ordered action loop. Existing side-effect actions retain their runtime behavior; `reply_grpc` renders JSON, parses it into the dynamic output message, serializes it, and returns custom initial metadata with an OK status and message. `grpcio` supplies the `application/grpc` content type and wire-level framing/trailers.

File-backed payload selection and header rendering reuse the existing template and prepared-file helpers. _(see `http-yaml-mock-server/add-template-helpers-file-backed-bodies`)_

### Introduce pure structural matching and condition evaluation helpers

Separate channel-specific structural matching from condition rendering so both runtime dispatch and `/api/v1/evaluate` follow the required order. Preserve current public runtime behavior by having existing find functions compose those helpers. Add a condition evaluator that returns both the raw rendered string and pass/fail status; `condition_passes` remains a compatibility wrapper.

This small extraction prevents evaluation from approximating runtime semantics while avoiding a broad matcher rewrite.

### Parse evaluation requests on the admin API

Route `POST /api/v1/evaluate` in `AdminRequestHandler`. Parse JSON only, require top-level `mock` and object-valued `context`, validate a deep copy of the mock through normal concrete-behavior preparation, then perform evaluation without adding it to `RuntimeState`.

Build each supplied channel context with the existing context constructors plus a new gRPC constructor, merge their template variables, and add the mock's `Values`. Matcher-specific validation requires the corresponding context object. AMQP normalization continues to default an omitted queue to `routing_key`.

### Use a dedicated dry-run action renderer

Add `evaluate_actions`, which iterates `_sort_actions` but only recognizes `reply_http` and `publish_kafka`. For HTTP it calls the pure `build_http_response` and serializes status as a string, body as UTF-8 text, content type, and generated headers. For Kafka it renders topic and payload using the same payload-selection helper but never accesses a producer.

All other action types are skipped without dispatch. The function must not call `execute_actions`, `publish_kafka_message`, `publish_amqp_message`, `send_http_request`, Redis helpers, sleep, or any worker API. This explicit allowlist is the primary side-effect boundary.

## Risks / Trade-offs

- [Dynamic descriptor dependency ordering can reject valid multi-file sets if loaded naively] -> Add files to the pool in dependency-resolved passes and fail with the unresolved file names.
- [The runtime can hot-reload a gRPC method absent from the startup registry] -> Validate every assembled runtime against the immutable registry before installation and retain the previous snapshot on reload failure.
- [grpcio controls some protocol headers and trailers] -> Set OK code/details and custom metadata through its APIs, then verify wire behavior with a real gRPC client.
- [Merged channel contexts can contain fields from unrelated channels] -> Match only declared matchers while deliberately exposing every provided context to templates, as required.
- [A future action could accidentally become side-effecting during evaluation] -> Keep evaluation on an allowlist and test that side-effect functions are not called for every currently supported action type.
- [Adding grpcio increases binary dependency size] -> Keep it optional at runtime through `HM_GRPC_ENABLED`, while accepting the install-time dependency for reliable protocol support.

## Migration Plan

1. Add and lock `grpcio` and `protobuf`.
2. Extend configuration and behavior validation without changing existing defaults.
3. Add descriptor loading and the optional gRPC server lifecycle.
4. Add shared matcher/condition helpers and the evaluation route.
5. Run the existing suite plus descriptor-backed gRPC integration and no-side-effect evaluation tests.

Rollback consists of disabling `HM_GRPC_ENABLED` and reverting the new endpoint/dependencies; existing mock definitions and default HTTP, Kafka, and AMQP startup behavior remain compatible.

## Open Questions

None. The checkpoint fixes the transport security mode, supported RPC shape, descriptor source, endpoint shape, and dry-run action allowlist.
