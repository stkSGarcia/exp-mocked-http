## ADDED Requirements

> Extends: mock-definition-loading/add-http-yaml-mock-server
> Extends: template-hot-reload/add-hot-reload-cors-binary-cli
> Extends: kafka-message-handling/add-kafka-amqp-message-handling

### Requirement: gRPC Runtime Configuration
The system SHALL run an optional HTTP/2 cleartext gRPC server without TLS when `HM_GRPC_ENABLED` is `true`, reading `HM_GRPC_HOST`, `HM_GRPC_PORT`, and `HM_GRPC_DESCRIPTOR_SET_PATHS` from runtime configuration using documented defaults when variables are absent. (adapts mock-definition-loading/add-http-yaml-mock-server/server-configuration)

#### Scenario: gRPC server disabled by default
- **GIVEN** `HM_GRPC_ENABLED` is absent
- **WHEN** the mock server starts
- **THEN** it does not start a gRPC listener

#### Scenario: gRPC server uses configured address
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **AND** `HM_GRPC_HOST` and `HM_GRPC_PORT` are set
- **WHEN** the mock server starts
- **THEN** it listens for HTTP/2 cleartext gRPC requests on the configured host and port without TLS

### Requirement: Descriptor Set Loading
The system SHALL load comma-separated protobuf descriptor-set files from `HM_GRPC_DESCRIPTOR_SET_PATHS`, resolving relative paths from `HM_TEMPLATES_DIR`, when any loaded behavior uses `expect.grpc` or `reply_grpc`.

#### Scenario: Descriptor config required when gRPC behavior needs protobufs
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **AND** a loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` is missing, unreadable, or invalid
- **THEN** startup fails before serving requests

#### Scenario: Descriptor config optional when gRPC is unused
- **GIVEN** `HM_GRPC_ENABLED` is `true`
- **AND** no loaded behavior uses `expect.grpc` or `reply_grpc`
- **WHEN** `HM_GRPC_DESCRIPTOR_SET_PATHS` is empty
- **THEN** startup succeeds

### Requirement: gRPC Behavior Matching
The system SHALL match gRPC behaviors by the `(service, method)` pair from `expect.grpc.service` and `expect.grpc.method`, using first-match wins.

#### Scenario: First matching gRPC behavior selected
- **GIVEN** two loaded behaviors declare the same `expect.grpc.service` and `expect.grpc.method`
- **WHEN** a gRPC request arrives for that service and method
- **THEN** the first matching behavior is selected

#### Scenario: Nonmatching gRPC method rejected
- **GIVEN** a loaded behavior declares `expect.grpc.service` and `expect.grpc.method`
- **WHEN** a gRPC request arrives for a different method on the same service
- **THEN** that behavior is not selected

### Requirement: gRPC Template Context
The system SHALL render gRPC conditions and replies with `.GRPCService`, `.GRPCMethod`, `.GRPCPayload`, and `.GRPCHeader` values derived from the matched gRPC request.

#### Scenario: gRPC request context is available to templates
- **GIVEN** a gRPC request matches a behavior
- **WHEN** the behavior condition or reply templates render
- **THEN** `.GRPCService` contains the matched service name
- **AND** `.GRPCMethod` contains the matched method name
- **AND** `.GRPCPayload` contains the request body converted from protobuf to JSON
- **AND** `.GRPCHeader.Get "key"` reads HTTP/2 headers and gRPC metadata

### Requirement: Protobuf Request and Response Handling
The system SHALL decode inbound gRPC requests using standard length-prefixed framing, convert request protobuf messages to JSON, render `reply_grpc.payload` or `reply_grpc.payload_from_file` as JSON, and encode the rendered JSON as the configured protobuf response message.

#### Scenario: gRPC payload decoded to JSON
- **GIVEN** a descriptor set contains the request message for a configured gRPC service method
- **WHEN** a framed protobuf request arrives for that method
- **THEN** the request payload is decoded and exposed to templates as a JSON string

#### Scenario: gRPC response encoded from rendered JSON
- **GIVEN** a selected behavior includes `reply_grpc.payload`
- **WHEN** the reply payload renders to valid JSON for the configured response message
- **THEN** the system returns a standard length-prefixed protobuf response frame

### Requirement: gRPC Reply Action
The system SHALL support `reply_grpc` actions with a required rendered `payload` unless `payload_from_file` is set, optional rendered metadata `headers`, and standard successful gRPC response headers. (adapts http-behavior-mocking/add-template-helpers-file-backed-bodies/file-backed-http-response-body)

#### Scenario: gRPC reply includes standard success headers
- **GIVEN** a selected behavior includes `reply_grpc`
- **WHEN** the response is sent
- **THEN** the response includes `grpc-status: 0`
- **AND** the response includes `grpc-message: OK`
- **AND** the response includes `Content-Type: application/grpc`

#### Scenario: gRPC reply includes custom metadata
- **GIVEN** a selected `reply_grpc` action includes rendered `headers`
- **WHEN** the response is sent
- **THEN** the response includes the custom metadata headers in addition to the standard success headers

#### Scenario: File-backed gRPC payload renders
- **GIVEN** a selected `reply_grpc` action sets `payload_from_file`
- **WHEN** the response is rendered
- **THEN** the file content is loaded relative to the template directory when needed and rendered as the response JSON payload
