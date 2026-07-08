---
name: openspec-archive-change
description: Archive a completed change in the experimental workflow. Use when the user wants to finalize and archive a change after implementation is complete.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.3.1"
---

Archive a completed change in the experimental workflow.

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `openspec list --json` to get available changes. Use the **AskUserQuestion tool** to let the user select.

   Show only active changes (not already archived).
   Include the schema used for each change if available.

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Check artifact completion status**

   Run `openspec status --change "<name>" --json` to check artifact completion.

   Parse the JSON to understand:
   - `schemaName`: The workflow being used
   - `artifacts`: List of artifacts with their status (`done` or other)

   **If any artifacts are not `done`:**
   - Display warning listing incomplete artifacts
   - Use **AskUserQuestion tool** to confirm user wants to proceed
   - Proceed if user confirms

3. **Check task completion status**

   Read the tasks file (typically `tasks.md`) to check for incomplete tasks.

   Count tasks marked with `- [ ]` (incomplete) vs `- [x]` (complete).

   **If incomplete tasks found:**
   - Display warning showing count of incomplete tasks
   - Use **AskUserQuestion tool** to confirm user wants to proceed
   - Proceed if user confirms

   **If no tasks file exists:** Proceed without task-related warning.

4. **Extract aspects from each delta spec**

   For each spec under `openspec/changes/<name>/specs/<capability>/spec.md`:

   a. Read the full spec content.
   b. Identify **at most 4 distinct aspects** this spec covers — each aspect should be a different thematic concern (e.g., "API surface changes", "data model updates", "error handling", "performance constraints"). Aspects must be meaningfully different, not variations on the same theme.
   c. For each aspect, derive **exactly 3 lowercase semantic keyword tags** (1–3 words each, no duplicates across all aspects).
   d. Write `openspec/changes/<name>/specs/<capability>/aspects.json` with this exact shape:
      ```json
      [
        { "label": "<Aspect Label>", "tags": ["tag1", "tag2", "tag3"] },
        { "label": "<Aspect Label>", "tags": ["tag4", "tag5", "tag6"] }
      ]
      ```

   Repeat for every capability directory under `specs/`. If a spec has fewer than 4 meaningful dimensions, use fewer aspects — quality over quantity.

5. **Perform the archive**

   Run the archive command, which reads the `aspects.json` files, indexes delta specs into the knowledge graph, and moves the change to the archive directory:

   ```bash
   openspec archive <name> --yes
   ```

   If the command exits with a non-zero code, surface the error to the user and stop.

6. **Display summary**

   Show archive completion summary including:
   - Change name
   - Schema that was used
   - Archive location
   - Capabilities indexed into the KG (aspects extracted per spec)
   - Note about any warnings (incomplete artifacts/tasks)

**Output On Success**

```
## Archive Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Archived to:** openspec/changes/archive/YYYY-MM-DD-<name>/
**KG:** ✓ Delta specs indexed (Capability → DeltaSpec → Requirement → Scenario)
**Aspects:** ✓ Up to 4 aspects extracted per spec with semantic tags and embeddings

All artifacts complete. All tasks complete.
```

**Guardrails**
- Always prompt for change selection if not provided
- Use artifact graph (openspec status --json) for completion checking
- Don't block archive on warnings - just inform and confirm
- Preserve .openspec.yaml when moving to archive (it moves with the directory)
- Show clear summary of what happened
