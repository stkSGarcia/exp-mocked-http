## Context

The server is a single-file Python application ([hmock.py](../../../hmock.py)) using Jinja2 with `StrictUndefined`. Template functions are registered once in `_make_jinja_env()` via `env.globals` and `env.filters`. The existing set covers string manipulation, encoding, math, and basic UUID generation. The `execute_reply_http` function already renders header values through `render()`.

The checkpoint adds nine new template helpers plus a `body_from_file` field on `reply_http`. All helpers map directly to Python standard-library or lightweight third-party functions.

## Goals / Non-Goals

**Goals:**
- Register all nine new template helpers in `_make_jinja_env()`
- Add `body_from_file` field: snapshot file contents at load time, render at request time
- Specify header rendering behavior in the spec (it is already implemented)

**Non-Goals:**
- Changing the template delimiter syntax or preprocessing pipeline
- Full JSONPath spec compliance beyond what the checkpoint describes
- Caching or hot-reloading of `body_from_file` contents after startup

## Decisions

### Template helpers: use standard library + minimal deps

| Helper | Implementation |
|---|---|
| `uuidv5(data)` | `uuid.uuid5(uuid.NAMESPACE_OID, data)` — stdlib, no new dep |
| `hmacSHA256(secret, data)` | `hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()` — stdlib |
| `htmlEscapeString(str)` | `html.escape(str, quote=True)` — stdlib |
| `isLastIndex(index, array)` | `int(index) == len(array) - 1` — no dep |
| `regexFindAllSubmatch(pattern, str)` | `re.search(pattern, str)` → `[m.group(0)] + list(m.groups(""))` or `[]` — stdlib |
| `regexFindFirstSubmatch(pattern, str)` | first capture group from `re.search`, `""` if no match/no group — stdlib |
| `jsonPath(expr, data)` | `jsonpath-ng`: parse expr, find in `json.loads(data)`, return inner text of first match |
| `gJsonPath(expr, data)` | Custom dot-path walker: split on `.`, handle `#` count, `#` wildcard, numeric indexes |
| `xmlPath(expr, data)` | `lxml.etree` with `xpath()`: return inner text of first node, `""` on no match |

**jsonPath vs gJsonPath:** Two distinct helpers because they serve different syntaxes used in real Go templates (`jsonpath-ng` covers the XPath-style `//foo` queries; the custom `gJsonPath` covers `gjson`-style dot notation which is more common in practice and handles the array wildcard `items.#.id` and count `items.#`).

**jsonpath-ng for jsonPath:** The `jsonpath-ng` library parses standard JSONPath expressions and is the most faithful mapping of the XPath-style syntax described in the checkpoint. Alternatives like `jmespath` use a different query language.

**lxml for xmlPath:** `lxml` ships prebuilt wheels, supports full XPath 1.0, and is already commonly present in Python environments. Alternative `xml.etree.ElementTree` only supports a limited XPath subset and cannot handle `//` or predicates reliably.

**gJsonPath implemented in-house:** The `gjson` dot-notation rules (array index, `#` count, `#.field` wildcard) are simple enough to implement in ~30 lines without adding another dependency.

### body_from_file: snapshot at load time

During `load_behaviors()`, after validating each behavior, check whether any `reply_http` action contains `body_from_file`. If so:
1. Resolve the path relative to `TEMPLATES_DIR`.
2. Read the file and store its content as a string in a synthetic `_body_snapshot` key on the action dict.

At request time in `execute_reply_http()`:
- If `_body_snapshot` is present, use it as the template string.
- Otherwise fall back to `body`.
- If both `body` and `body_from_file` are set, use `body_from_file` only when `body` is empty (per spec).

Snapshotting at load time means file reads happen once, keeping request-path latency predictable and making the server's behavior stable regardless of file changes after startup.

### Header rendering: already implemented, no code change needed

`execute_reply_http` already iterates over headers and calls `render(str(v), context)` for each value. The only action required is updating the spec to make this an explicit requirement.

## Risks / Trade-offs

- **lxml binary dependency** → Mitigation: lxml provides pre-built wheels for all major platforms; add it to `pyproject.toml` alongside `jsonpath-ng`.
- **gJsonPath wildcard returns joined string** → When `items.#.id` matches multiple values, the helper must decide on a representation. Decision: join with `\n` and return as a single string, consistent with how `gjson` serializes array results.
- **body_from_file path traversal** → Paths are resolved with `os.path.realpath` and compared against `TEMPLATES_DIR` to ensure the resolved path stays within the templates directory. Raise `ValueError` at load time if the path escapes.
- **jsonPath empty data returns ""** → Per spec. If `data` is not valid JSON, return a render error (let the exception propagate to `render()`).

## Migration Plan

1. Add `lxml` and `jsonpath-ng` to `pyproject.toml` dependencies.
2. Add `import hashlib, hmac, html` to `hmock.py` imports.
3. Implement `_gjson_path()` helper function.
4. Register all nine new globals/filters in `_make_jinja_env()`.
5. Add `body_from_file` resolution to `_validate_behavior()` / `load_behaviors()`.
6. Update `execute_reply_http()` to check `_body_snapshot`.
7. Update `openspec/specs/http-mock-server/spec.md` via delta spec.

No migration concerns — changes are purely additive. Rollback: revert `hmock.py` and the spec delta.
