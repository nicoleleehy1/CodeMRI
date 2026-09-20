# Create mode: first release scope

Create turns an architecture drawing into a reviewable coding proposal. The source-backed architecture remains the baseline; a saved draft records the desired change. The first release works at the architecture/component layer in an analyzed repository.

## Delivered workflow

1. Analyze a repository and open **Create**. Start from its architecture or choose a blank, additive draft.
2. Add components, edit names/types/responsibilities, draw typed connections by selecting source and target, edit their behavior, remove nodes/connections, and arrange the canvas. Mouse dragging, arrow-key movement, panning, zoom, fit, undo, and redo are supported.
3. Describe overall intent and acceptance criteria. Explain migration/replacement behavior for removed existing components and independently removed connections.
4. **Check locally** validates structure without an AI call. It checks intent, responsibilities, duplicate names, missing endpoints, connection descriptions, removal notes, and source/architecture identity. It lists source paths for affected components and their immediate neighbors. These checks do not prove feasibility.
5. **Assess & plan with Codex** checks source freshness, then runs the installed Codex CLI in a temporary repository copy with a read-only sandbox. The focused prompt contains the semantic graph diff, relevant component/file mappings, intent, and acceptance criteria. Codex is asked for feasibility, evidence, missing requirements, implementation steps, and verification. This step consumes tokens.
6. Review the assessment. **Implement reviewed plan** requires an assessment of this exact semantic draft and an unchanged indexed source revision. It uses the existing isolated coding-proposal workflow. Changes to responsibilities, connections, removal notes, intent, or acceptance invalidate the previous assessment; moving nodes does not.
7. Review proposed file diffs in **Explore codebase** and approve selected files. Create also shows tentative structural matches between the proposed graph and the extracted architecture of the proposed code. The agent is asked to report acceptance criteria as met, unmet, or unverified. Structural matching is not behavioral verification.

## Semantics and persistence

- Layout coordinates are presentation only and are excluded from agent prompts and plan identity.
- Removing a component requests removal of its responsibility, not wholesale deletion of every file associated with it. Shared implementation must be preserved.
- Blank drafts add to the repository; omitted existing components are not deletion requests. A repository must still be analyzed first.
- One draft and assessment are saved per repository root in VS Code workspace state. Drafts survive panel reopening and extension reloads; analyze the repository to restore its graph. Undo/redo history is session-local.
- A code proposal retains the originating architecture draft so restored file reviews can show structural comparison.
- Source changes block assessment/implementation until reanalysis. The old draft remains visible; reconciliation is manual in this release. Replacing a draft clears its edits and assessment.
- `GET /graphs/{repo_id}/freshness` recomputes the indexed source revision without replacing the saved architecture or the review baseline. It makes no model call. Its coverage is the analyzer's existing coverage.
- Assessment copies are deleted after success, failure, or cancellation. Implementation proposals continue using the existing pending-file storage and approval behavior.
- Draft input is versioned and validated at the extension boundary. The current limits are 500 nodes, 2,000 edges, and 500,000 serialized characters. Agent prompts above 30,000 characters are rejected before invocation; split larger proposals into focused changes.

## Explicit boundaries

This is a component-level editor, not a function-signature editor or an automatic refactoring engine. It does not prove runtime feasibility, automatically resolve stale-draft conflicts, enforce organization-specific architecture rules, or infer all dynamic dependencies. Cycles and disconnected components may be intentional; the agent assessment must evaluate their meaning. The assessment is readable text, and the user must resolve its questions before choosing implementation. The implementation prompt instructs the agent to stop on unresolved material conflicts.

Initial layout is a simple editable grid. Collaboration, multiple named drafts, import/export, rich ports, automatic graph rebasing, project bootstrapping outside an analyzed repository, and measured token-savings benchmarks are follow-up work.

## Verification

`npm run check` checks TypeScript. `npm test` builds the extension and runs JavaScript plus Python tests. Create tests cover source isolation, layout/intent separation, graph diff semantics, stale revisions, malformed drafts, removal requirements, focused context, tentative comparison, read-only assessment, failed assessments, plan invalidation, temporary-copy cleanup, proposal approval, and freshness preservation of saved architecture. The webview is also exercised in a browser with a mocked VS Code bridge, without paid Codex calls.
