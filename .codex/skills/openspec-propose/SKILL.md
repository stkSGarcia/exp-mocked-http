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

2. **Shallow KG search — find related intents and specs**

   a. **Generate hypothetical intent tags** (internal reasoning — do NOT include in any artifact):

      ```json
      {
        "intent": {
          "label": "<3–6 word kebab-case name, e.g. `add-user-notifications`>",
          "tags": ["<tag1: 2–4 words>", "<tag2: 2–4 words>", "<tag3: 2–4 words>", "<tag4: 2–4 words>"]
        }
      }
      ```
      Tags must cover distinct aspects (e.g. `CLI command interface`, `notification delivery`, `event trigger model`).

   b. **Run shallow KG search — intent + spec matches only (no requirement depth yet):**

      **IMPORTANT: NEVER read, list, or glob files under `openspec/changes/archive/` during this search or any step — archived changes are strictly off-limits.**

      ```bash
      openspec kg context \
        --text "<tag1>|<tag2>|<tag3>|<tag4>" \
        --k-deep 0         --k-top 6         --json
      ```
      - `--k-deep 0` skips requirement and scenario phases — returns only intent and spec matches.
      - Read `graphText` from the result to identify Related Changes (intents) and Related Specs (specs).

3. **Create change + write proposal.md**

   a. `openspec new change "<name>"`

   b. If step 2 found matches, write their `id` fields as a JSON array to `openspec/changes/<name>/related-specs.json`:
      ```json
      ["spec:user-notifications", "spec:auth"]
      ```

   c. `openspec instructions proposal --change "<name>" --json`
      Write **proposal.md** using `template` as structure. `context` and `rules` are your constraints only — do NOT copy them into the file.

      From the shallow `graphText` (step 2):
      - `## Related Work > ### Related Changes`: per intent node — what motivated that prior change and how this one extends, replaces, or complements it.
      - `## Related Work > ### Related Specs`: per spec node — what it implements and how this change reuses, adapts, or builds on it.

4. **Deep KG search + write delta spec files**

   a. **R-
      ```json
      {
        "requirements": [
          {
            "title": "<short noun phrase naming the capability>",
            "text": "The <component> SHALL <behavior>.",
            "scenarios": [
              { "title": "<short phrase for one concrete case>", "text": "WHEN <trigger> THEN <outcome>" }
            ]
          }
        ]
      }
      ```
      Use the specific capabilities and behaviors stated in the proposal — not generic placeholders.

   b. **Run deep KG search — requirements and scenarios scoped to the matched specs:**

      **IMPORTANT: NEVER read, list, or glob files under `openspec/changes/archive/`.**

      ```bash
      openspec kg context \
        --text "<same tags from step 2>" \
        --req-text "<req1.title>: <req1.text>|<req2.title>: <req2.text>|..." \
        --scen-text "<scen1.title>: <scen1.text>|<scen2.title>: <scen2.text>|..." \
        --k-top 6 \
        --json
      ```
      - `--req-text` drives requirement search scoped to the specs found in step 2.
      - `--scen-text` drives scenario search scoped to requirements found above.
      - Read `graphText` — it now contains matched requirements and scenarios.

   c. `openspec instructions specs --change "<name>" --json --omit-context`
      Read `proposal.md` then write **specs/\*\*/\*.md** using the deep `graphText`:
      - Where a new requirement reuses or adapts a matched requirement, append: `(adapts <requirement-id>)`
      - Where requirements build on an existing spec's behavior, open that group with: `> Extends: <spec-id>`
      - Draw on matched requirement `text` for consistent language and acceptance criteria style.
      - Never duplicate a requirement already covered by a related spec — reference it instead.

5. **Write design.md and tasks.md**

   Use `TodoWrite` to track. Process in dependency order — read existing artifacts before writing each.

   - **design.md**: `openspec instructions design --change "<name>" --json --omit-context`
     Read `proposal.md` + `specs/**/*.md` first.
     Add `## Related Work` near the top. For each related spec from step 2:
     > **`<id>`**: <text> — informs [specific design decision] because <intent.text>.
     When a design decision was shaped by a related spec, add: _(see `<spec-id>`)_

   - **tasks.md**: `openspec instructions tasks --change "<name>" --json --omit-context`
     Read `design.md` + `specs/**/*.md` first.
     For tasks touching existing code, name the specific files from related changes as starting points.
     Mark pure extensions with `[extends <spec-id>]`.

   After each write: `openspec status --change "<name>" --json` — stop when all `applyRequires` are `"done"`.

6. `openspec status --change "<name>"` — show final status and prompt to run `/opsx:apply`.

**Guardrails**
- Read dependency artifacts before creating each new one
- If change name already exists, ask to continue or rename
- Prefer reasonable decisions over asking; only ask when critically unclear
- Verify artifact file exists after writing before proceeding
- **IMPORTANT: NEVER read, list, or reference any files under `openspec/changes/archive/` — archived changes are off-limits during proposal**
