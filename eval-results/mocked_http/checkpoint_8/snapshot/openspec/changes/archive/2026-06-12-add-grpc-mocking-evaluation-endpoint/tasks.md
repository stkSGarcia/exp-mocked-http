## 1. Dependencies and Configuration

- [x] 1.1 Add `grpcio` and `protobuf` to `pyproject.toml` and refresh `uv.lock`.
- [x] 1.2 Extend `Config`, constants, and `load_config` in `hmock.py` with the four `HM_GRPC_*` settings and defaults; add default/override coverage in `test_hmock.py`. [extends http-yaml-mock-server/add-http-yaml-mock-server]

## 2. Descriptor and Schema Support

- [x] 2.1 Implement descriptor-set path resolution, dependency-aware pool loading, and `(service, method)` lookup in `hmock.py`.
- [x] 2.2 Extend `_validate_behavior` and `_prepare_actions` in `hmock.py` for required `expect.grpc` fields and inline/file-backed `reply_grpc` payloads, reusing existing file restrictions. [extends http-yaml-mock-server/add-template-helpers-file-backed-bodies]
- [x] 2.3 Validate assembled runtime gRPC methods against the descriptor registry before installation and preserve the previous runtime on hot-reload/admin validation failure.
- [x] 2.4 Add `test_hmock.py` coverage for relative paths, multi-file descriptors, missing/unreadable/invalid sets, unresolved methods, and descriptor-free startup when gRPC behaviors are absent.

## 3. gRPC Runtime

- [x] 3.1 Add gRPC context construction, service/method structural matching, first-match behavior selection, and raw condition-result helpers in `hmock.py`. [extends http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering]
- [x] 3.2 Implement the dynamic unary gRPC handler in `hmock.py` to decode request messages to JSON, expose metadata through `HeaderMap`, render ordered actions, encode `reply_grpc`, and return required status and custom metadata.
- [x] 3.3 Add optional insecure gRPC server creation, startup, logging, shutdown, and failure cleanup to `main` in `hmock.py`. [extends http-yaml-mock-server/add-http-yaml-mock-server]
- [x] 3.4 Add descriptor-backed real-client tests in `test_hmock.py` for first-match behavior, gRPC template fields, framed protobuf round trips, file payloads, custom metadata, and default disabled behavior.

## 4. Dry-Run Evaluation

- [x] 4.1 Add evaluation-request parsing and validation in `hmock.py` for a single concrete mock, supported matcher requirements, object-valued context, matcher-specific contexts, and AMQP queue normalization.
- [x] 4.2 Build and merge simulated HTTP, Kafka, AMQP, and gRPC template contexts in `hmock.py`, then evaluate structural matching before rendering the condition. [extends http-yaml-mock-server/add-http-yaml-mock-server]
- [x] 4.3 Implement a dedicated allowlisted dry-run action renderer in `hmock.py` that returns ordered `reply_http_action_performed` and `publish_kafka_action_performed` data without calling runtime side-effect functions. [extends http-yaml-mock-server/add-template-helpers-file-backed-bodies]
- [x] 4.4 Route `POST /api/v1/evaluate` from `AdminRequestHandler` in `hmock.py`, returning `400` for validation failures and the specified match, condition, and action result JSON for valid requests.
- [x] 4.5 Add `test_hmock.py` endpoint coverage for every channel matcher, merged contexts, failed matching, empty/passing/failing conditions, action ordering, HTTP generated headers, Kafka rendering, and malformed requests.
- [x] 4.6 Add tests that patch every Redis, HTTP, Kafka, AMQP, sleep, and other side-effect path and assert evaluation never invokes them or mutates runtime state.

## 5. Verification

- [x] 5.1 Run the full pytest suite and fix regressions in existing HTTP, admin, template, Kafka, AMQP, Redis, and hot-reload behavior.
- [x] 5.2 Run focused gRPC and evaluation tests repeatedly to verify listener cleanup, deterministic action order, and no leaked worker/server threads.
