## 1. Dependencies

- [x] 1.1 Add `lxml` and `jsonpath-ng` to `pyproject.toml` dependencies
- [x] 1.2 Run `uv sync` (or equivalent) to install new packages and update `uv.lock`

## 2. Stdlib helper imports

- [x] 2.1 Add `import hashlib, hmac, html` to the import block in `hmock.py`

## 3. Implement gJsonPath helper function

- [x] 3.1 Implement `_gjson_path(expr, data)` in `hmock.py`: split expr on `.`, traverse parsed JSON, handle numeric indexes, `#` count, and `#.field` wildcard; return `""` on no match; raise on invalid JSON

## 4. Register template helpers in _make_jinja_env

- [x] 4.1 Register `jsonPath` using `jsonpath-ng`: parse expr, match against `json.loads(data)`, return inner text of first result; return `""` on empty data or no match
- [x] 4.2 Register `gJsonPath` delegating to `_gjson_path`
- [x] 4.3 Register `xmlPath` using `lxml.etree`: parse XML, run `xpath(expr)`, return text of first node; return `""` on empty data or no match
- [x] 4.4 Register `uuidv5` using `uuid.uuid5(uuid.NAMESPACE_OID, data)`
- [x] 4.5 Register `regexFindAllSubmatch`: `re.search` → `[m.group(0)] + list(m.groups(""))` or `[]` on no match
- [x] 4.6 Register `regexFindFirstSubmatch`: `re.search` → first capture group or `""` on no match / no groups
- [x] 4.7 Register `hmacSHA256`: `hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()`
- [x] 4.8 Register `isLastIndex`: `int(index) == len(array) - 1`
- [x] 4.9 Register `htmlEscapeString`: `html.escape(str, quote=True)`

## 5. Implement body_from_file loading

- [x] 5.1 In `_validate_behavior()`, detect `body_from_file` on any `reply_http` action: resolve path with `os.path.realpath` relative to `TEMPLATES_DIR`; raise `ValueError` if resolved path does not start with `os.path.realpath(TEMPLATES_DIR)`
- [x] 5.2 Read the resolved file and store its contents as `_body_snapshot` on the `reply_http` action dict

## 6. Use body_from_file at request time

- [x] 6.1 In `execute_reply_http()`, determine the effective body template: use `_body_snapshot` when present and `body` is empty; otherwise fall back to `body`

## 7. Sync specs

- [x] 7.1 Run `openspec sync-specs --change template-helpers-file-backed-bodies` to merge the delta spec into `openspec/specs/http-mock-server/spec.md`
