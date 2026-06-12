## 1. Configuration And Runtime Reload

- [x] 1.1 Add `templates_dir_hot_reload` and `cors_enabled` defaults, `Config` fields, and environment parsing in `hmock.py`; extend configuration tests in `test_hmock.py`.
- [x] 1.2 Implement templates-tree fingerprinting and an atomic polling reload worker in `hmock.py`, coordinated with `_MUTATION_LOCK` and preserving the last valid `RuntimeState`. [extends `http-yaml-mock-server/add-behavior-templates-inheritance-values-ordering`]
- [x] 1.3 Wire reload worker startup, shutdown, and disabled-mode boundaries into `hmock.py`; add `test_hmock.py` coverage for create, edit, delete, invalid edit, fixture edit, and disabled hot reload.

## 2. CORS Response Policy

- [x] 2.1 Attach `Config` to the mock server and add case-insensitive CORS default merging in `hmock.py`.
- [x] 2.2 Update `MockRequestHandler` in `hmock.py` so explicit `OPTIONS` mocks match normally and unmatched requests become empty `200` preflights only when CORS is enabled.
- [x] 2.3 Add `test_hmock.py` integration coverage for matched responses, `404` responses, explicit and unmatched `OPTIONS`, disabled CORS, and mock-defined header precedence.

## 3. Binary HTTP Payloads

- [x] 3.1 Extend action preparation in `hmock.py` to validate confined `body_from_binary_file` paths and capture stable byte snapshots plus source filenames. [extends `http-yaml-mock-server/add-template-helpers-file-backed-bodies`]
- [x] 3.2 Update `build_http_response()` in `hmock.py` for inline-body precedence, unrendered binary bytes, byte-accurate `Content-Length`, and optional inline `Content-Disposition`. [extends `http-yaml-mock-server/add-template-helpers-file-backed-bodies`]
- [x] 3.3 Add a one-file multipart encoder and update `send_http_request()` in `hmock.py` for binary `POST` uploads, filename selection, file-part content type overrides, and raw non-`POST` bytes.
- [x] 3.4 Add `test_hmock.py` coverage for binary path validation, snapshot stability, reply precedence and headers, multipart field metadata and bytes, raw outbound methods, and inline outbound precedence.

## 4. Admin YAML And omctl

- [x] 4.1 Extend `AdminRequestHandler` in `hmock.py` to parse `application/yaml` and `application/x-yaml` definitions while retaining JSON behavior and atomic validation. [extends `admin-template-management/add-admin-api-template-persistence`]
- [x] 4.2 Create `omctl.py` with `argparse` help, recursive and prevalidated `push`, URL-encoded named-set routing, required-key `delete`, expected-status checks, and non-zero error exits. [extends `admin-template-management/add-admin-api-template-persistence`]
- [x] 4.3 Add the `omctl` console script to `pyproject.toml`.
- [x] 4.4 Extend `test_hmock.py` and add focused CLI tests if needed for YAML admin requests, push defaults and overrides, recursive aggregation, invalid local YAML without network activity, delete requests, and transport/status failures.

## 5. Verification

- [x] 5.1 Run the complete `pytest` suite and resolve regressions across existing text bodies, admin persistence, action ordering, and request handling.
- [x] 5.2 Exercise the installed `omctl --help`, `omctl push`, and `omctl delete` entry points against a local admin server fixture.
- [x] 5.3 Run OpenSpec validation for `add-hot-reload-cors-binary-admin-cli` and confirm every checkpoint requirement is represented by passing tests.
