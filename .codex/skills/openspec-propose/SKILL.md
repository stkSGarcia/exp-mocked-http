---
name: openspec-propose
description: Propose a new change with all artifacts generated in one step. Use when the user wants to quickly describe what they want to build and get a complete proposal with design, specs, and tasks ready for implementation.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.3.1"
---

**Steps**

1. If no description provided, ask with AskUserQuestion: "What do you want to build?"
   Derive a kebab-case name (e.g. `add-user-auth`). Do NOT proceed without a description.

2. **Find similar existing specs and their requirements and scenarios**

   a. **Generate hypothetical spec artifacts** to sharpen KG search (internal reasoning — do NOT include in any artifact):

      Think through the change as a spec author and produce JSON in this shape:
      ```json
      {
        "intent": {
          "label": "<3–6 word kebab-case name, e.g. `add-user-notifications`>",
          "tags": ["<tag1: 2–4 words>", "<tag2: 2–4 words>", "<tag3: 2–4 words>", "<tag4: 2–4 words>"]
        },
        "requirements": [
          {
            "title": "<short noun phrase naming the capability>",
            "text": "The <component> SHALL <behavior>.",
            "scenarios": [
              {
                "title": "<short phrase for one concrete case>",
                "text": "WHEN <trigger> THEN <outcome> AND <optional extra outcome>"
              }
            ]
          }
        ]
      }
      ```
      Tags must cover distinct aspects (e.g. `CLI command interface`, `notification delivery`, `event trigger model`, `user alert display`).

   b. **Run KG search using the hypothetical artifacts (no user permission needed):**

      **IMPORTANT: NEVER read, list, or glob files under `openspec/changes/archive/` during this search or any step — archived changes are strictly off-limits.**

      ```bash
      openspec kg context \
        --text "<tag1>|<tag2>|<tag3>|<tag4>" \
        --req-text "<req1.title>: <req1.text>|<req2.title>: <req2.text>|..." \
        --scen-text "<scen1.title>: <scen1.text>|<scen2.title>: <scen2.text>|..." \
        --json
      ```
      - `--text` drives the intent + spec search (Phase 1).
      - `--req-text` drives the requirement search scoped to specs found in Phase 1.
      - `--scen-text` drives the scenario search scoped to requirements found in Phase 2.
      - All three phases run in one call; the result is a single JSON with `graphText` and `counts`.

      Read `graphText` from the JSON — it contains the merged context view for use in step c.

   c. **Use the graph-text to build on previous work — reference and reuse across all artifacts:**

      - iN **proposal.md**
            `## Why` section:
                1. Open with a 1–2 sentence problem statement explaining why this change is needed.

            `## Related Work` section:
                1. `### Related Changes`: per intent node — what motivated that prior change and how this one extends, replaces, or complements it.
                2. `### Related Specs`: per spec node — what it implements and how this change reuses, adapts, or builds on it. Name the capability specifically, not just the id.
      - In **spec** (requirements):
        - Where a new requirement reuses or adapts a pattern from a related requirement match, append a parenthetical reference: `(adapts <requirement-id>)`
        - Where new requirements build on an existing spec's behavior, open that requirements group with a blockquote: `> Extends: <spec-id>`
        - Draw on the related requirement `text` to stay consistent in language, scope, and acceptance criteria style.
        - Never duplicate a requirement already covered by a related spec — reference it with `(adapts <requirement-id>)` instead of restating it.

      - In **design.md**:
        - Add a "## Related Work" section near the top. For each related spec write:
          > **`<id>`**: <text> — informs [specific design decision] because <intent.text>.
        - When a design decision was directly shaped by a related spec, add an inline citation in that section: _(see `<spec-id>`)_

      - In **tasks.md**: for tasks that touch existing code, name the specific files from related changes as the starting point. Mark pure extensions with `[extends <spec-id>]`.

3. `openspec new change "<name>"`
   If step 2 found matches, write their `id` fields as a JSON array to `openspec/changes/<name>/related-specs.json`.

4. `openspec status --change "<name>" --json` — note `applyRequires` and `artifacts`.

5. **Create artifacts** — use TodoWrite to track. Process in dependency order (status `ready` first):
   - First artifact: `openspec instructions <id> --change "<name>" --json`
   - Subsequent artifacts: add `--omit-context` (context is identical — carry it from first call)
   - Write artifact using `template` as structure. `context` and `rules` are your constraints only — do NOT copy them into the file.
   - Read `dependencies` files before writing each artifact.
   - After each write: `openspec status --change "<name>" --json` — stop when all `applyRequires` are `"done"`.
   - If context is unclear: AskUserQuestion, then continue.

6. `openspec status --change "<name>"` — show final status and prompt to run `/opsx:apply`.

**Guardrails**
- Read dependency artifacts before creating each new one
- If change name already exists, ask to continue or rename
- Prefer reasonable decisions over asking; only ask when critically unclear
- Verify artifact file exists after writing before proceeding
- **IMPORTANT: NEVER read, list, or reference any files under `openspec/changes/archive/` — archived changes are off-limits during proposal**
