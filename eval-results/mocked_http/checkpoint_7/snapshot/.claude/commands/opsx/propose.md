---
name: "OPSX: Propose"
description: Propose a new change - create it and generate all artifacts in one step
category: Workflow
tags: [workflow, artifacts, experimental]
---

Propose a new change - create the change and generate all artifacts in one step.

I'll create a change with artifacts:
- proposal.md (what & why)
- design.md (how)
- tasks.md (implementation steps)

When ready to implement, run /opsx:apply

---

**Input**: The argument after `/opsx:propose` is the change name (kebab-case), OR a description of what the user wants to build OR a path to the file where the change is mentioned.

**Steps**

1. **If no input provided, ask what they want to build**

   Use the **AskUserQuestion tool** (open-ended, no preset options) to ask:
   > "What change do you want to work on? Describe what you want to build or fix."

   From their description, derive a kebab-case name (e.g., "add user authentication" → `add-user-auth`).

   **IMPORTANT**: Do NOT proceed without understanding what the user wants to build.

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

3. **Create the change directory**
   ```bash
   openspec new change "<name>"
   ```
   This creates a scaffolded change at `openspec/changes/<name>/` with `.openspec.yaml`.

   **If related specs were found in step 2**, write their IDs to a file so the archive step can create graph edges:
   - Collect the `id` field from each match (e.g. `"spec:user-notifications"`)
   - Write them as a JSON array to `openspec/changes/<name>/related-specs.json`

   Example:
   ```json
   ["spec:user-notifications", "spec:auth"]
   ```

4. **Get the artifact build order**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to get:
   - `applyRequires`: array of artifact IDs needed before implementation (e.g., `["tasks"]`)
   - `artifacts`: list of all artifacts with their status and dependencies

5. **Create artifacts in sequence until apply-ready**

   Use the **TodoWrite tool** to track progress through the artifacts.

   Loop through artifacts in dependency order (artifacts with no pending dependencies first):

   a. **For each artifact that is `ready` (dependencies satisfied)**:
      - Get instructions — **use `--no-context` on every call except the first**:
        - First artifact: `openspec instructions <artifact-id> --change "<name>" --json`
        - All subsequent artifacts: `openspec instructions <artifact-id> --change "<name>" --json --omit-context`
      - The instructions JSON includes:
        - `context`: Project background — **present only on the first call**; apply it as a session-level constraint for ALL artifacts and do NOT include it in output
        - `rules`: Artifact-specific rules (constraints for you - do NOT include in output)
        - `template`: The structure to use for your output file
        - `instruction`: Schema-specific guidance for this artifact type
        - `outputPath`: Where to write the artifact
        - `dependencies`: Completed artifacts to read for context
      - Read any completed dependency files for context
      - Create the artifact file using `template` as the structure
      - Apply `context` (from first call) and `rules` as constraints - but do NOT copy them into the file
      - If related specs/requirements were found in step 2, apply the structured format from step 2d: "### Related Specs" block in proposal.md Why section, `(adapts <id>)` / `> Extends: <id>` annotations in spec requirements, and "## Related Work" section in design.md
      - Show brief progress: "Created <artifact-id>"

   b. **Continue until all `applyRequires` artifacts are complete**
      - After creating each artifact, re-run `openspec status --change "<name>" --json`
      - Check if every artifact ID in `applyRequires` has `status: "done"` in the artifacts array
      - Stop when all `applyRequires` artifacts are done

   c. **If an artifact requires user input** (unclear context):
      - Use **AskUserQuestion tool** to clarify
      - Then continue with creation

6. **Show final status**
   ```bash
   openspec status --change "<name>"
   ```

**Output**

After completing all artifacts, summarize:
- Change name and location
- List of artifacts created with brief descriptions
- If similar specs were found, list them as "Related specs: [labels]"
- What's ready: "All artifacts created! Ready for implementation."
- Prompt: "Run `/opsx:apply` to start implementing."

**Artifact Creation Guidelines**

- Follow the `instruction` field from `openspec instructions` for each artifact type
- The schema defines what each artifact should contain - follow it
- Read dependency artifacts for context before creating new ones
- Use `template` as the structure for your output file - fill in its sections
- **IMPORTANT**: `context` and `rules` are constraints for YOU, not content for the file
  - Do NOT copy `<context>`, `<rules>`, `<project_context>` blocks into the artifact
  - These guide what you write, but should never appear in the output

**Guardrails**
- Create ALL artifacts needed for implementation (as defined by schema's `apply.requires`)
- Always read dependency artifacts before creating a new one
- If context is critically unclear, ask the user - but prefer making reasonable decisions to keep momentum
- If a change with that name already exists, ask if user wants to continue it or create a new one
- Verify each artifact file exists after writing before proceeding to next
- **IMPORTANT: NEVER read, list, or reference any files under `openspec/changes/archive/` — archived changes are off-limits during proposal**
