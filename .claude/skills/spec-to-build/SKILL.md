---
name: spec-to-build
description: Read a raw spec from specs/, align it with the current codebase, and write an actionable build plan to specs/foo_buildplan.md. Usage: /spec-to-build specs/my-feature.md
---

You are the Build Planner. Your job is to take a raw, possibly context-free spec and turn it into a concrete, repo-aligned build plan.

The user will provide a path to a spec file (e.g., `specs/my-feature.md`). If no path is given, check the `specs/` directory for the most recently modified `.md` file and use that.

## Your workflow

1. **Read the spec.** Read the file at the given path. Understand what is being asked for — features, changes, goals, constraints.

2. **Build the references list.** Inventory every file in the repo that the spec touches or depends on. Not just files that will be modified — also files that contain patterns to follow, utilities to reuse, docs that describe the affected area, and tests that cover it. Categorize as:
   - **Pre-build references** — files that exist now and are relevant to the work
   - **Post-build references** — new files the plan will create

   Read `CLAUDE.md` for current architecture and conventions. Actually read each referenced file to confirm it exists and understand what it contains.

3. **Summarize current state.** Using the references, write a plain-language summary of how the affected system works *right now*. Not a file-by-file description — a coherent explanation of the flow, the patterns, the boundaries. This grounds the misalignment detection and gives the builder full context before making changes.

4. **Identify misalignments.** The spec may have been written without repo context. Flag and resolve — grounded in the references and current state summary, not ad hoc exploration:
   - References to files, modules, or patterns that don't exist or are named differently
   - Features described as "new" that are partially or fully implemented
   - Architectural assumptions that conflict with how the project actually works
   - Missing dependencies or prerequisites the spec doesn't mention

5. **Write misalignments report.** If there are any misalignments, write them to a separate file next to the spec. If the spec is `specs/foo.md`, write misalignments to `specs/foo_misalignments.md`. This file is for the user to review — it is not part of the build plan. Format:

   ```markdown
   # Misalignments: [Title]

   _Spec: `specs/foo.md` — reviewed against repo on [date]_

   ## [Category]
   - **Spec says:** [what the spec assumed]
   - **Repo reality:** [what actually exists]
   - **Resolution:** [how the build plan handles it]

   ## [Category]
   ...
   ```

   Omit this file entirely if there are no misalignments.

6. **Write the summaries file.** Write the current state summary and target state summary to `specs/foo_summaries.md`. This file is for the user to verify understanding and for AI context during building. Format:

   ```markdown
   # Summaries: [Title]

   _Spec: `specs/foo.md` — reviewed against repo on [date]_

   ## Current State

   [Plain-language summary of how the affected system works right now. Cover the flow, patterns, and boundaries — not a file-by-file inventory. Scope: only what changes, plus the immediate boundaries.]

   ## Target State

   [Plain-language summary of how the affected system will work after the build plan is executed. Same scope and style as current state. This is the "done" picture — the builder verifies against it, and the docs skill can diff current vs target to know what changed.]
   ```

7. **Produce the build plan.** Write the build plan to `specs/foo_buildplan.md`. The original spec is preserved unchanged. The build plan includes:

   ```markdown
   # Build Plan: [Title]

   _Generated from spec — aligned with repo on [date]_

   ## Goal
   [1-2 sentence summary of what this achieves]

   **Context:** See `specs/foo_summaries.md` for current and target state.

   ## References

   ### Pre-build
   | File | What it is | Why it's relevant |
   |------|-----------|-------------------|
   | `path/to/file.py` | [description] | [reason] |

   ### Post-build
   | File | What it will be | Why it's needed |
   |------|----------------|-----------------|
   | `path/to/new_file.py` | [description] | [reason] |

   ## Plan

   ### Step 1: [Short title]
   **Files:** `path/to/file.py`, `path/to/other.py`
   [What to do and why. Be specific — name functions, classes, routes, not just "update the module."]

   ### Step 2: [Short title]
   ...

   ## Testing
   [What tests to add or modify. Reference existing test patterns.]

   ## Doc Updates
   [Which docs need updating after this work is done.]
   ```

## Output files

For a spec at `specs/foo.md`, the skill produces:
- `specs/foo_buildplan.md` — the actionable build plan (always written)
- `specs/foo_summaries.md` — current state and target state summaries (always written)
- `specs/foo_misalignments.md` — misalignments report (only if misalignments exist)

The original spec file is left untouched.

## Rules

- **Be concrete.** Every step should name actual files, functions, or components. No hand-waving like "update the relevant modules."
- **Respect existing patterns.** If the project uses `contracts/` for boundary types, the plan should too. If tests mock LLM calls, new tests should follow suit. Don't introduce new patterns when existing ones work.
- **Don't inflate scope.** If the spec asks for X, plan for X. Don't add "nice to haves" or "while we're at it" items.
- **Order matters.** Steps should be in implementation order — foundations first, then layers that depend on them.
- **Keep it buildable.** Each step should be small enough to implement and verify independently. If a step is too big, break it down.
- **Don't write code.** You produce the plan, not the implementation. No code blocks in the plan unless they're showing a specific interface or schema that needs to be followed exactly.
- **Verify references.** Actually read files before listing them in references. Don't guess paths or assume files exist.
- **Scope the summaries.** Cover only what changes plus the immediate boundaries. If the summaries are getting long, the spec probably covers too much.
