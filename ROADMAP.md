# CodeMRI Roadmap

Living plan for building CodeMRI. [README.md](README.md) is the product spec and the source of truth for what ships; this file is the build order. **Update this file in the same change as the work it describes** (see [How to maintain](#how-to-maintain-this-file)).

- **Last updated:** 2026-09-20 (source audit; no fresh test/F5 run)
- **Current phase:** Reconcile the delivered Codex/Create/review features with remaining Track A and agent-loop work
- **Next task:** Ensure the remote checkout includes this local baseline, run existing checks, then P0.4 → A1b → A3/P1.3. Continue the remaining tasks below in dependency order; external validation does not block independent local work.

## Implementation handoff (read first)

This plan was reconciled against the local working tree on 2026-09-20. It contains substantial modified and untracked implementation files. **Before giving a remote agent this plan, commit and push the intended implementation and documentation, or supply a complete source snapshot.** README/ROADMAP alone do not transfer local changes. Record the starting commit in the implementation report. Do not commit `.env`, caches, credentials, or `sources/` changes.

- Treat `[~]` as partially delivered: implement only the stated remainder. `[x]` historical verification is not a fresh verification of today's checkout.
- Preserve the existing SQLite store, Codex temporary-copy approval flow, Create editor, hierarchy/cards/call navigation, and baseline diff. Extend these modules rather than replacing them.
- Start with `npm run check` and `npm test`; record baseline failures separately. For each change run relevant checks, update this file, and report completed task IDs with evidence. Manual F5, paid-provider runs, sponsor requirements, and benchmark results must be labeled pending until actually exercised.
- Suggested unattended sequence after the small fixes above: P0.5 → P3.3 → P3.1/P3.2 → P3.4 → remaining P3.5/P3.6 → P4.1/P4.2/P4.3 → P4.4. **Status 2026-09-20: this sequence is implemented and tested locally (see the log); what remains in it is the recorded real run / F5 evidence, which needs a live agent and VS Code.** Existing baseline diff is sufficient to start the loop; historical snapshot retention is not a prerequisite. Schema/identity changes need migration tests and should stay separate from loop integration.
- Track A's remaining selection/UX/exploration tasks can follow local fixes. A4a live measurement and A8 comparisons require actual provider runs. Do not claim them from mocks. Phase 5 remains gated on confirmed requirements; Phase 7 is optional backlog, not an overnight completion requirement.
- If one task requires unavailable credentials, tools, or owner input, record the blocker and continue independent work. Do not mark blocked work complete or substitute a fake integration.

### Delivered baseline — do not rebuild

| Capability | Source and existing test evidence | Remaining scope |
|---|---|---|
| SQLite current graph + reviewed baseline, legacy JSON loading | `store.py`, `tests/test_changes.py` | Historical retention and arbitrary-pair comparison |
| Offset-tolerant symbol/edge diff and graph review | `changes.py`, `change-review.js`, `tests/test_changes.py` | Stable IDs, rename/move, architecture-layer diff, cycles, PR mode |
| Codex chat, isolated proposals, file approval/discard/restoration | `agent.ts`, `proposals.ts`, `tests/extension.test.cjs`, `tests/test_proposals.py` | Delivered 2026-09-20 (P3.4/P3.5); a recorded real run is still pending |
| Create drafts, local checks, read-only assessment, implementation | `create-model.ts`, `create-mode.js`, `tests/create.test.cjs` | Follow-ups in `docs/create-mode.md`; no rewrite required |
| Freshness endpoint, stale warnings, explicit scans | `services/api/main.py`, `extension.ts`, `tests/test_api.py` | Incremental indexing (P6); structured test results now shown |
| Budget slider, copy context, selected-symbol highlighting | `extension.ts`, `graph.js` | Delivered 2026-09-20 (P4.3); recorded F5 check pending |
| Hierarchy, symbol cards, pinned panels, call occurrences, keyboard navigation | `hierarchy.py`, webview modules, hierarchy/call-site/renderer tests | Scale and deeper resolution |

Paths above are relative to their engine, extension, or test directories. Evidence lists identify code/tests, not a new test run.

## Decisions

Confirmed with the project owner on 2026-09-19.

| Question | Decision |
|---|---|
| Deadline | None fixed. HackMIT 2026 is a milestone, not a cliff. Prefer correct foundations over demo shortcuts. |
| Headline feature | **Agent loop + architecture diff**: `task → impact → context → agent patch → tests → reanalyze → graph diff`. |
| Sponsor tracks | OpenAI, Token Company, Cognition (Devin), Warp. All four are candidates; each is gated on verifying its real requirements (Phase 5). |
| Working mode | Owner-directed implementation; remote-agent handoff follows the current dependency order above. Historical Claude decisions are preserved below as context. |
| Priority (2026-09-19) | **AI-generated architecture graph (Track A) comes first.** The local map (`system_map.py`) only looks good on MemMunkDB: it uses LSM vocabulary and fixed group names, and other repos degrade to directory names. It stays as a labelled offline fallback and is no longer tuned. |
| AI approach | Single-pass GitDiagram-style pipeline first, then a tool-using exploration loop. GitDiagram is MIT (rev `1b97a5e`); its ideas are ported to Python, not its TypeScript. |
| Provider and model | OpenAI Responses API; use the configured `CODEMRI_ARCHITECTURE_MODEL`. The historical run used `gpt-5.6-luna`; no current availability or price claim is made here. |
| Key handling | Historical owner-run paid-provider workflow remains the default unless the owner authorizes a change. Do not read or copy real `.env` credentials into reports. Tests use a mocked provider. |
| Order vs Phase 0 | The original Track A sequencing is superseded by the 2026-09-20 handoff above. Independent local fixes need not wait for live measurements. |

## Principles

Carried over from the README; they decide close calls.

1. **Never overclaim.** Static edges are "possible behavior", AI edges are "inferred", and observed runtime evidence is a separate class. No agent-savings claim without a benchmark run behind it.
2. **Local-first.** Analysis, graph, impact, and context need no key or hosted service. AI is optional and is an explicit user action.
3. **Preserve the working demo.** Every phase ends with `npm run check`, `npm test`, and the F5 MemMunkDB flow green. Changes are additive or migrated, not rewrites.
4. **One engine, two consumers.** API and MCP read the same snapshots through the same engine code. A feature is not done until both consumers can use it.
5. **Reading is separate from acting.** MCP code-reading tools never execute repository code or apply patches. Test execution and patch application are explicit, isolated workflow steps.
6. **Untrusted input.** Repository text (comments, docs, commit messages) is data, never instructions, and keeps its provenance in context packs.

## Historical baseline (2026-09-19, before later implementation)

The following records the original verification, not the current file count, test count, Git state, or implementation status. See the delivered baseline above for today’s source audit:

- `npm run check` (`tsc --noEmit`) is clean. `npm test` runs the Node tests and `pytest`: 17 Python tests pass, no Node failures.
- Toolchain: Node 20.20, Python 3.12.5, Java 23, Maven 3.9.14.
- Engine is small and dense: about 1,400 lines across `packages/engine/codemri/`, `services/`, and `apps/extension/src/`.
- `examples/MemMunkDB` is cloned locally, has Maven and 21 JUnit tests (`LSMStoreTest`), and is a real git repo.
- `examples/shop` and `examples/system-design` have **no tests and no `package.json`**, so they cannot host a patch → test loop as-is.
- The repository has **no commits** yet, and `.venv-old/`, `.DS_Store`, `.vscode/`, and `.github/modernize/` are untracked and not all ignored.
- Not yet re-verified: the manual F5 acceptance flow (it needs VS Code).

## Gaps found in the current code

These are why the phases are ordered the way they are. Each has an owning task.

| Gap | Where | Impact | Task |
|---|---|---|---|
| Symbol IDs embed byte offsets (`path::name@byte`) | `analyzer.py` | IDs change on edits; existing diff compensates for offsets, but rename/move identity remains incomplete | P1.1 |
| SQLite keeps current + reviewed baseline only | `store.py` | No arbitrary retained-history selection | P2.1 |
| ~~`.gitignore` not interpreted~~ git-aware ignore + secret exclusion/redaction | `ignore.py` | — | P1.3 (done) |
| `Edge` has `source/target/kind/call_sites`; richer evidence and labels live in the untyped `layers` dict | `models.py` | No first-class evidence class (static / inferred / observed) | P1.2 |
| ~~Impact only follows `calls` edges~~ typed traversal (calls/imports/contains) + tests via P3.2 | `context.py` | Contracts still not modeled | P1.4 (done) |
| ~~`compile_context` re-tokenizes per candidate~~ compiler v2 tokenizes each section once, has signature mode and dedupe | `context.py` | — | P4.1 (done) |
| `repository_tokens` counts module sources only | `context.py` | Now defined in `repository_tokens_definition`; still an indexed-source figure, not checkout size | P4.1 (done) |
| MCP `get_symbol` raises `StopIteration` on an unknown ID; `get_architecture` returns whole graph with source | `services/mcp/server.py` | Poor agent ergonomics, large responses | P0.4 (done) |
| MCP `analyze_repository` docstring says TS/JS but `analyze` also runs Java | `services/mcp/server.py` | Misleading tool description | P0.4 (done) |
| Allowed-root check duplicated in API and MCP; `synthesize` (AI) not exposed over MCP | both | Drift risk; MCP/API parity gap | P0.4 (done) |
| Extension analysis runs are manual; snapshots go stale on edit | `extension.ts` | Freshness check before context compilation, stale note on test runs, structured test results shown; recorded F5 pending | P3.6 |

## Phase overview

```text
P0 Reproduce ──► P1 Foundations ──► P2 Snapshots + Diff ──► P3 Tests + Agent loop
                                                                 │
                            P6 Incremental + scale ◄── P5 Sponsors ◄── P4 Context + Benchmark
                                                                 │
                                                          P7 Backlog (history, PR mode, health, data flow, runtime)
```

Dependencies: the existing baseline diff can support the first loop now. Tests and compiled-context handoff are missing; the benchmark needs a reusable loop harness. Stable IDs and historical retention extend comparison separately. Sponsor integrations require a working flow and confirmed requirements.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped (with reason in the log).

---

## Track A — AI-generated architecture (priority)

**Goal:** point CodeMRI at any repository and get a source-grounded architecture map that does not depend on rules written for one project.
**Exit:** live runs on three different repositories (MemMunkDB, `examples/system-design`, one unfamiliar repository) with every relationship citing real source, and a labelled comparison of single-pass against agentic exploration.

- [x] **A0. Live-run plumbing.** `GET /ai/status` (key set or not, model name, pid; never the key); the missing-config error names the missing variable; provider errors surface OpenAI's message with `sk-…` redacted. *Done 2026-09-19.* Found that `--env-file` never overrides variables already in the shell and is read only at startup.
- [x] **A1. Validation repair and retry-with-feedback.** The first live run reached the model and then failed our validator ("unknown group or source path"). Directories are now accepted and expand to their files (so drilldown still works), unresolvable node paths are stripped, dangling edges and unverifiable citations are dropped (an edge with no valid citation is removed), and structural faults (schema, duplicate ids, unknown groups, invalid JSON) trigger one retry that returns the issues to the model. Every run writes `.codemri/ai-last-run.json` (raw output, issues, repairs; never the key). *Done 2026-09-19.* **Correction:** I first guessed the failure was a directory path. The run log showed the real cause was an empty group on the external actor (see A1b); directory handling and path stripping were never exercised live (0 repairs), so they remain mock-tested only.
- [x] **A2. First live run (MemMunkDB).** *Done 2026-09-19.* `gpt-5.6-luna`, 13 files sent, 13 nodes, 22 edges, 5 groups, 2 attempts. Not hardcoded: none of the diagram's labels exist in our code (the local map's rules are unused in AI mode), and it differs from the local map. Structure and semantics spot-checked as broadly right (Bloom filter is real Guava code, size-tiered compaction and tombstone dropping are real). **Weakness: only 14 of 31 citations (45%) land on a line of real code**; 7 are blank lines and 10 are comments, imports or braces. Cause: the excerpts carry no line numbers, so the model estimates them. Fixed by A4a.
- [x] **A1b. Ungrouped actors.** Attempt 1 failed because the model put the HTTP client in group `""`. The prompt says "keep external initiating actors ungrouped" but our schema requires a real group, so every run with an actor spends a second API call. Treat an empty group as ungrouped (the renderer already has a fallback group) instead of retrying. **Done 2026-09-20:** `semantic.py` accepts an empty group as ungrouped; unknown non-empty groups still fail validation (`tests/test_semantic.py`). Live effect (one fewer API call per run with an actor) not re-measured.
- [x] **A3. Ignore and secret hygiene before sending code.** Interpret `.gitignore`; skip `.venv-*` and other virtualenvs (the analyzer scanned `.venv-old` as source and produced 1,681 nodes); redact secret-shaped strings in excerpts. This is P1.3 pulled forward. **Done 2026-09-20** via P1.3 (`ignore.py`).
- [~] **A4a. Citations the user can trust.** Implemented and mock-tested (29 tests); **awaiting a live re-run to measure** against the 45% baseline from A2. Two language-agnostic parts: (1) excerpts are line-numbered (`N| code`), so the model reads numbers instead of estimating; (2) every citation now carries a `quote`, the exact text of the cited line. We locate the quote in the file, move the citation to the closest matching line, and drop it if the quote is not found on an acceptable line (not blank, not punctuation-only, not a comment in a language whose syntax we know, and an import only counts for IMPORTS or DEPENDS_ON). An edge left with no verified citation is dropped. Chosen over matching the cited line against the target's name because that fails on abbreviations (`wal.append` is the correct citation for "Write-Ahead Log"). Unlisted file types (docs, markup, unfamiliar languages) only have to avoid blank and brace-only lines. Run `python scripts/citation_quality.py` after each live run. Limit: verification proves the cited line exists and contains the quote, not that it proves the claim.
- [ ] **A4b. Excerpt selection.** Replace README-first-then-alphabetical truncation with GitDiagram-style selection: favour substantive runtime modules, spread excerpts across long files, keep imports for sampled calls, report exactly what was and was not sampled. Needed for repositories larger than the 140k-character budget; MemMunkDB (13 files) fits entirely, so this is untested.
- [ ] **A5. Reasoning effort and cost.** Configurable reasoning effort (default medium, as upstream), and report token usage and estimated cost from the API response.
- [~] **A6. Extension UX.** `/ai/status` is now documented in the README. Remaining: show mode, model, attempts, coverage, and repairs, with clearer progress and failure messages. From the first live diagram: edges take long looping routes around the canvas and cross nodes, and every edge is dashed because AI relationships are marked inferred by design, so add a legend explaining that. Also show each citation's `quote` next to `path:line` in the evidence list, so a reader sees the proving line without opening the file.
- [ ] **A7. Agentic exploration.** A tool-using loop (`list_dir`, `read_file`, `search`) with step and token budgets, feeding the same validator and repair path. Read-only tools, confined to the repository root.
- [ ] **A8. Compare and decide.** Single-pass against agentic on the three repositories: relationship accuracy against hand checks, cost, and time. Record results and keep the winner as default.

## Phase 0 — Reproduce and clean up

**Goal:** a trustworthy starting point. Use the current handoff order; fresh setup and manual acceptance remain distinct verification tasks.
**Exit:** fresh-clone setup works from README steps; first commit exists; README claims match reality.

- [x] **P0.1 Initial commit and repo hygiene.** Ignored `.venv-*/`, `.DS_Store`, `.vscode/*` except `launch.json` and `tasks.json`, and `.github/modernize/` (a VS Code tool-use recorder hook, not project code; ignored rather than deleted). Committed the tree as the baseline (56 files). *Done when:* `git status` is clean and `git ls-files` contains no venvs, caches, or snapshots. **Done 2026-09-19.**
- [ ] **P0.2 Fresh-setup reproduction.** In a scratch clone, follow README Quick start exactly (`venv`, `pip install -r requirements-lock.txt`, `npm ci`, `npm run build`, start uvicorn, warm tiktoken). Record any step that fails or is missing. *Done when:* the steps work verbatim, or README is corrected.
- [ ] **P0.3 Manual F5 acceptance pass.** Run the README demo checklist against MemMunkDB and `examples/system-design` in VS Code. This is the one thing automated tests do not cover. Log pass/fail per checklist item in the [log](#log). *Done when:* every checklist item has a recorded result.
- [x] **P0.4 Small correctness fixes.** MCP `get_symbol` returns a clear error for unknown IDs; correct the `analyze_repository` docstring; extract the allowed-root check into one shared function used by API and MCP; add a compact `get_architecture` option (no source bodies) so agents are not handed the whole graph. *Done when:* tests cover each, and API/MCP share the helper. **Done 2026-09-20:** `roots.resolve_allowed` shared by API/MCP; `get_symbol` raises `ValueError`; `get_architecture(compact=True)`; docstring names Java (`tests/test_mcp.py`).
- [x] **P0.5 API/MCP parity test.** One test analyzes via API, then reads the same snapshot through the MCP tool functions (same `CODEMRI_CACHE`), and asserts equal results. *Done when:* the test passes and lives in `tests/`. **Done 2026-09-20:** `tests/test_mcp.py::test_api_and_mcp_parity`.
- [~] **P0.6 README truthfulness sweep.** Source reconciliation completed 2026-09-20. Remaining: run fresh checks and manual F5 acceptance, and correct any resulting discrepancies. This documentation edit is not runtime verification.

## Phase 1 — Foundations for diff and the loop

**Goal:** the graph contract can support comparison, evidence classes, and safe input.
**Exit:** schema v3 documented and migrated; identity survives a no-op reanalysis and a line-shifting edit; ignored files are excluded.

- [ ] **P1.1 Stable symbol identity.** Replace byte-offset IDs with qualified identity (path + container chain + name + kind + arity, with a deterministic disambiguator for true collisions). Provide explicit old→new mapping for rename/move detection later. Test: reanalysis is identical; inserting lines above a symbol keeps its ID; overloads stay distinct. Test with non-ASCII source to keep UTF-16 columns correct. *Done when:* the fixtures above pass and existing tests are updated.
- [ ] **P1.2 Schema v3.** Add `snapshot_id`, `created_at`, `analyzer_version`, and a config fingerprint; give `Edge` first-class `evidence` (`static | inferred | observed`), optional `label`, and source location; record unresolved references with a reason instead of only a warning string. Keep v2 snapshots loadable via migration. Mirror the change in `apps/extension/src/extension.ts`. *Done when:* v2 files load, v3 round-trips through API, MCP, and the extension.
- [x] **P1.3 `.gitignore` and secret exclusion.** Interpret `.gitignore` during inventory and exclude common secret files (`.env*`, key files) from analysis and from AI excerpts. Record what was skipped in diagnostics. *Done when:* a fixture with an ignored secret never appears in graph, snapshot, or AI excerpt input. This gates any wider AI use. **Done 2026-09-20:** `ignore.py` (git-aware ignore, secret filename patterns, `redact_secrets`), shared `walk_repository` in `analyzer.py`, skip diagnostics in graph inventory, redaction counted in `coverage.redacted_secrets` (`tests/test_ignore.py`).
- [x] **P1.4 Typed-edge impact.** Refactor `impact()` to traverse by edge kind and direction (calls, imports, contains, and later tests), keep the reasons, and cover Java call edges. Keep the current lexical seeding and 3-hop bound as the default so existing behavior does not regress. *Done when:* existing impact tests pass unchanged plus new cases for import edges and Java. **Done 2026-09-20:** `impact(kinds=…)` traverses `TRAVERSALS` by kind/direction (calls reverse ≤3 hops is the unchanged default; imports reverse 1 hop; contains forward 1 hop), keeps reasons, reports `edges_followed`; Java call edges covered (`tests/test_impact_typed.py`).
- [ ] **P1.5 Accuracy fixtures.** Small labeled fixtures for import aliases, shadowing, re-exports, default imports, and Java overloads, with expected edges and expected unresolved cases. This becomes the regression baseline for "index quality". *Done when:* a report lists true/false/missing edges per fixture.

## Phase 2 — Retained snapshots and architecture diff

**Goal:** answer "what changed structurally between these two states?"
**Exit:** arbitrary historical-pair comparison and richer architecture changes are correct on fixtures and visible in the extension; current-versus-reviewed comparison already exists.

- [~] **P2.1 Retained snapshot store.** SQLite current/baseline storage and legacy JSON migration already exist. Extend SQLite with immutable historical snapshots, configurable retention, and lookup by snapshot ID. Preserve current/review semantics; do not replace SQLite with per-snapshot JSON files. *Done when:* revisions survive restart and retention preserves the reviewed baseline.
- [~] **P2.2 Diff engine.** `changes.py` already compares added/removed/modified symbols and graph edges while compensating for offset shifts. Add rename/move matching, signature detail, architecture-layer relationship comparison, new cycles, and affected entry points. *Done when:* new fixture pairs pass alongside existing line-shift tests.
- [~] **P2.3 API and MCP surface.** HTTP analyze/review and preview already expose baseline/proposal comparisons. Add arbitrary retained-snapshot comparison and MCP `diff_snapshots`, with parity tests; preserve current endpoints and tool names.
- [~] **P2.4 Extension diff view.** Existing graph/file review shows changed nodes/edges, removed-snapshot navigation, and approval controls. Add historical-pair selection and architecture-layer edge evidence inspection. Preserve proposal review. *Done when:* automated navigation checks and a recorded F5 check cover the additions.
- [ ] **P2.5 Boundary rules (optional).** Explicit config for allowed dependency directions (for example UI → API → service → DB); diff flags violations. Observed conventions stay suggestions only. Defer if Phase 3 is blocked on it.

## Phase 3 — Tests and the agent loop (headline)

**Goal:** a real, recorded run of `task → impact → context → patch → tests → reanalyze → diff`.
**Exit:** one end-to-end run on MemMunkDB with a real patch, real test results, and a real graph diff, with all artifacts saved.

- [x] **P3.1 Test discovery.** Represent tests as graph nodes with `TESTED_BY` edges from imports, direct calls, and naming conventions. Label as heuristic. Start with JUnit (MemMunkDB), then pytest and `node:test`. Wording: "no identified tests", never "untested". *Done when:* MemMunkDB's `LSMStoreTest` links to `LSMStore` symbols. **Done 2026-09-20:** `tests_graph.discover_tests` adds a `tests` layer and heuristic `tested_by` edges (import/call/name) for JUnit, pytest and node:test; MCP `find_tests` is read-only (`tests/test_tests_graph.py`).
- [x] **P3.2 Impacted-test selection.** From impact results, return the associated tests with the path that justifies each. *Done when:* a change to an `LSMStore` method selects the relevant tests, and an unrelated change selects none. **Done 2026-09-20:** `impacted_tests` returns tests with the justifying symbol/`via`; `impact()` includes `tests` (`tests/test_tests_graph.py`, `tests/test_engine.py`).
- [x] **P3.3 Runnable TS fixture.** Add `package.json` and real tests to `examples/shop` (needs a TS runner such as `tsx`, because Node 20 does not strip types) so the TS demo can also exercise the loop. *Done when:* `npm test` inside `examples/shop` runs and passes. **Done 2026-09-20:** `examples/shop` has `package.json` + `node:test` via `tsx` (5 tests).
- [x] **P3.4 Test runner.** Explicit, user-initiated execution of a selected test set (`mvn -Dtest=…`, `pytest`, `node --test`) with timeout, captured output, and structured results. Runs in an isolated git worktree or copy, never the user's checkout. Not exposed as a read-only MCP tool. *Done when:* results are stored and shown; a failing test is reported faithfully. **Done 2026-09-20:** `runner.py` (allow-listed tools, temporary copy excluding `.git`/`.codemri`, timeout, captured/truncated output, structured status incl. `no-tests`; aggregate precedence error > timeout > failed > passed > no_tests; the API only executes selectors it derived itself; commands run in their own process group and the whole tree is killed on timeout; proposal `before` content is checked against the copy so stale proposals are rejected; credential-shaped env vars are stripped; stdout/stderr are bounded while the child runs; tools resolve on a PATH without the copy; Surefire aggregate is used over per-class lines; after the launcher exits, descendants holding the pipes are killed at the deadline so runs cannot hang; copies carry git's tracked/ignored answer plus `.gitignore` rules so agent-created ignored files stay out of patches; benchmark rows carry `git_dirty`; agent stdin is fed on a thread so an unread prompt cannot bypass the timeout; credential files are left out of runner copies; Vitest/Jest/Mocha files get their own `npx` selector and unknown JS runners get none; all-skipped suites are not `no_tests`; the extension sizes the run-tests deadline from the selection count), stored in SQLite `test_runs`, `POST /graphs/{id}/tests/run` + `GET …/tests/runs`, extension "Run impacted tests" behind a modal confirmation; not an MCP tool (`tests/test_runner.py`, `tests/extension.test.cjs`).
- [~] **P3.5 Loop orchestrator.** Codex execution, isolated temporary copies, previews, file approval/discard and restoration exist. Chat currently sends task/conversation, not a compiled context pack. Add impact/context handoff, integrate P3.4 structured tests in the isolated copy, and expose a reusable CLI/harness recording prompts, patches, results, timings and diffs. Reuse proposal machinery; additional agent adapters are optional. *Done when:* fake-agent plumbing tests pass and a separately recorded real run proves the full loop. **2026-09-20:** plumbing delivered — chat sends a compiled context pack (`codemri.agentContextBudget`), "Run impacted tests" runs against the pending proposal in a fresh copy, and `python -m codemri.loop` / `loop.run_loop` records prompt, patch, tests, timings, graph diff and raw agent usage per run (`tests/test_loop.py`). **Remaining:** the separately recorded real run (needs a live agent; not done).
- [~] **P3.6 Freshness and refresh.** Stale warnings, `/freshness`, manual scans and post-proposal refresh already exist. Add structured loop/test results and verify freshness throughout compilation, execution, review and refresh. *Done when:* stale-source tests pass and a recorded F5 run shows the loop result. **2026-09-20:** stale-source tests pass — chat re-scans when `/freshness` disagrees with the graph before compiling context, `/tests/run` reports `freshness` and a stale note, structured test results render in the webview. **Remaining:** the recorded F5 run.
- [ ] **P3.7 Recorded demo run.** Save one full run under `benchmarks/runs/` labeled as recorded. *Done when:* the demo can replay it and it is clearly marked precomputed.

## Phase 4 — Context compiler v2 and benchmark

**Goal:** measure whether CodeMRI context helps, without reducing correctness.
**Exit:** at least three tasks, both variants, repeated runs, raw records preserved.

- [x] **P4.1 Compiler v2.** Tokenize the serialized pack once per candidate set (not per append); reserve budget for task and metadata; full source for edit targets, signatures for peripheral symbols; dedupe overlapping ranges; report shortfalls when mandatory content does not fit; define `repository_tokens` precisely. Keep current output shape compatible. *Done when:* existing context tests pass and new tests cover shortfall and signature mode. **Done 2026-09-20:** one tokenization per candidate section, reserved task/metadata budget, full source for direct/affected targets and signatures for peripheral callees, nested-range dedupe (`covered`), `shortfall`/`omissions`/`tiers`, `repository_tokens_definition`; v1 keys unchanged (`tests/test_context_v2.py`, `tests/test_engine.py`).
- [x] **P4.2 Retrieval evaluation.** Labeled task → relevant-symbol sets on the fixtures; report found, missed, and unnecessary. Decide from data whether embeddings are worth adding (README: measure before semantic ranking). *Done when:* a repeatable script prints precision and recall per task. **Done 2026-09-20:** `benchmarks/retrieval_eval.py` + `benchmarks/retrieval/labels.json` (6 hand-labeled tasks over `examples/shop`, `examples/system-design`, optional MemMunkDB) print per-task precision/recall for `impact()` and `compile_context()` and missed/unlabeled symbols (`tests/test_retrieval_eval.py`). First reading at budget 4000: context recall 1.0, precision 0.60 — over-inclusion, not misses, is the gap; no evidence yet that embeddings are needed.
- [~] **P4.3 Context UI.** Budget slider, copy text, token counts and selected-symbol highlighting exist. Add included/supporting/excluded labels, omission explanations and JSON export. Connect context-to-agent through P3.5. *Done when:* automated UI/message checks and a recorded F5 check cover additions. **2026-09-20:** included/supporting/excluded tiers with omission reasons and a "Copy JSON" export are in the webview; context-to-agent handoff is wired through P3.5. **Remaining:** the recorded F5 check.
- [~] **P4.4 Benchmark harness.** Under `benchmarks/`: fixed repo revision, task definitions, baseline vs CodeMRI runners with the same agent, model, tools, and timeout, plus raw usage capture. Reuses the P3.5 orchestrator. Do not seed CodeMRI runs with the known patch or hidden tests. *Done when:* one task runs both variants and produces a results row. **2026-09-20:** `benchmarks/run.py` runs a task file (`benchmarks/tasks/shop-coupon-floor.json`) with `baseline` and `codemri` variants through the same agent command/timeouts, records pinned revision, raw usage, and preprocessing/agent/test/total timings to `benchmarks/results.jsonl` plus full per-run artifacts. Verified only with a fake agent (`tests/test_benchmark.py`); **no real agent row exists yet**, so the "produces a results row" criterion is not claimed.
- [ ] **P4.5 Benchmark runs and report.** At least three tasks, repeated, median and range, preprocessing cost reported separately and included in first-use totals. Report failures too. *Done when:* the README results table is filled from `benchmarks/` records, not hand-entered.

## Phase 5 — Sponsor integrations

**Gate:** none of these start until the owner supplies the current 2026 challenge pack and its requirements are recorded here. The README treats all four alignments as unverified. Add an integration only if it is part of the working flow.

- [ ] **P5.0 Verify requirements.** Record each sponsor's actual rules, eligibility, and required integration in the [log](#log). *Owner input needed.*
- [~] **P5.1 OpenAI.** A live MemMunkDB run is recorded under A2. Remaining: A4a follow-up live citation measurement, confirmed sponsor requirement evidence, and optional enrichment only if P4.2 supports it. Do not claim live results from mocks.
- [ ] **P5.2 Token Company.** Feed the P4 measurements (including preprocessing cost) into whatever the track requires; verify what "product use" means before building. *Done when:* end-to-end usage and cost are measured.
- [ ] **P5.3 Cognition (Devin).** Real Devin integration consuming a context pack (through the P3.5 agent command template or its API). Exported context alone does not count. *Done when:* a Devin session completes a task with a CodeMRI pack.
- [ ] **P5.4 Warp.** Verify MCP client configuration for Warp rather than assuming the generic example works; document a working setup. *Done when:* Warp calls the CodeMRI tools in a real session.

## Phase 6 — Incremental indexing and scale

**Goal:** make analysis fast and the UI responsive on larger repositories.

- [ ] **P6.1 Content-hash cache.** Skip unchanged files, re-extract changed ones, remove deleted symbols and edges, include analyzer and grammar and schema versions in cache keys.
- [ ] **P6.2 Dependent invalidation.** Re-resolve edges when exports, imports, or signatures change.
- [ ] **P6.3 Atomic partial publish.** Never mix old nodes with new edges across a refresh.
- [ ] **P6.4 Bounded rendering.** Graph virtualization and node limits in the webview; large-repo fixture and budgets.
- [~] **P6.5 Freshness and rebuild UI.** Manual analysis, stale indicators and a freshness endpoint exist. Integrate them with incremental indexing, full cache rebuild and background indexing status after P6.1–P6.3.
- [ ] **P6.6 Language depth.** TypeScript language-service resolution and full Java overload and type resolution, driven by the P1.5 fixtures.

## Phase 7 — Backlog (P2)

Not scheduled. Pull an item forward only when an earlier phase makes it cheap.

- Git history, "Why does this exist?", and two-snapshot time machine
- PR mode (merge-base diff → impact → summary → tests → context)
- Repository health dashboard (cycles, coupling, high-impact symbols without identified tests)
- Data-flow mode and sensitive-data path tracing
- Static candidate path view; runtime and coverage ingestion (observed edges)
- Natural-language graph queries returning answer plus subgraph
- Additional languages and framework adapters
- Shared annotations, task memory, secure remote graph service

---

## Demo track

Keep two scripts in sync with what actually works.

| Version | Available after | Content |
|---|---|---|
| Demo v1 (README 90-second demo) | P0 | Java architecture → drilldown → evidence → TS impact → context pack |
| Demo v2 | P3 | Replace part of navigation with a recorded patch → tests → diff, clearly labeled as recorded |
| Demo v3 | P4 | Add measured token and correctness results from the benchmark |

Do not make network latency or billing a dependency of the main demo. AI architecture generation stays an optional separate segment.

## Risks and open questions

| # | Item | Status |
|---|---|---|
| R1 | Sponsor requirements are unverified. | Blocks Phase 5; needs owner input (P5.0). |
| R2 | Which agent runs the first benchmarked loop? | Codex integration already exists; use it by default. Devin handoff does not itself constitute a product integration. |
| R3 | Stable IDs (P1.1) touch every consumer. High regression risk. | Mitigate with the schema migration and fixture tests before merging. |
| R4 | Test-to-code mapping is heuristic, so impacted-test selection can miss tests. | Label as heuristic; run the broader suite as a backstop in benchmarks. |
| R5 | Isolation for running test and agent commands. | Preserve existing temporary-copy isolation; add test-runner controls without editing the original checkout. |
| R6 | `.github/modernize/` origin and whether to keep it. | Resolved in P0.1: tool residue, ignored. The files remain on disk; delete them if you do not use that VS Code extension. |
| R7 | The F5 flow cannot be automated here; it depends on manual passes. | Track results in the log after each phase. |

## How to maintain this file

- When a task starts, mark `[~]` and update **Current phase** and **Next task** at the top.
- When it finishes, mark `[x]`, add a log entry with the evidence (test name, command, commit).
- If reality contradicts the plan (a task is wrong, bigger than expected, or unnecessary), change the plan in the same commit and say why in the log. Do not leave stale tasks.
- New work goes into the phase where it belongs; anything unscheduled goes in Phase 7.
- Keep README's "What works now" limited to shipped, tested behavior; move a feature there only when its task is `[x]`.
- A phase is done only when its exit line is true and `npm run check`, `npm test`, and the F5 flow pass.

## Log

- **2026-09-20** — Implemented the handoff sequence on branch `devin/1789894939-roadmap-handoff` (commits: P0.4/A1b/A3+P1.3, P0.5, P3.3, P3.1/P3.2, P3.4, P3.5/P3.6/P4.4, P4.1/P4.2/P4.3, P1.4). Baseline before work: `npm run check` clean, 24 Node + 46 Python tests passing, no failures. After: `npm run check` clean, 24 Node + 83 Python tests passing (5 pre-existing deprecation warnings). Not done and not claimed: recorded real agent run (P3.5/P3.7), F5 checks (P0.3/P3.6/P4.3), fresh-clone reproduction (P0.2), real benchmark rows/report (P4.4 row/P4.5), A4a live citation measurement, and all of Phase 5 (owner requirements + live integrations). `benchmarks/results.jsonl` and `benchmarks/runs/` are git-ignored so generated rows are never mistaken for committed results. A4b/A5 (Track A) were left for a follow-up.

- **2026-09-20** — Reconciled README/roadmap against local source. Marked snapshot/diff, Codex loop, freshness and context UI tasks partial; documented delivered Create/navigation features; retained historical live AI evidence and pending citation measurement. Corrected obsolete JSON-store plan and added remote handoff guidance because substantial implementation is modified/untracked locally. No tests, paid requests, or F5 checks were run for this documentation-only audit.

Newest first. One entry per meaningful change to plan or status.

- **2026-09-19** — A4a implemented (mock-tested, live measurement pending): numbered excerpts plus quote-verified citations, with a `scripts/citation_quality.py` report. Design constraint from the owner: it must generalise beyond LSM trees, so the rules use no vocabulary or per-project heuristics; comment syntax is keyed by file extension and unknown types fall back to the minimal blank/brace rule. A stricter alternative (require the cited line to mention the target's name) was rejected because it fails on abbreviations.

- **2026-09-19** — A2 done: the AI workflow runs live on MemMunkDB and the diagram renders. Read the run log to check the "not hardcoded" question (it holds) and to measure quality (citations weak: 45% on real code). Corrected the A1 entry: the original failure was an empty actor group, not a directory path; the retry loop is what made the run succeed. Added A1b and split A4 into A4a (trustworthy citations) and A4b (excerpt selection).

- **2026-09-19** — Track A started. Debugged the first live run in three steps: (1) the backend reported the model as missing although `.env` was correct, so I added `/ai/status` and named-variable errors; (2) once configuration loaded, OpenAI answered and our validator rejected the graph because the prompt allows directory paths while the validator did not; (3) ported GitDiagram's repair-and-retry approach (A1). Twenty-five Python tests pass; live behaviour after A1 is unverified until A2. Also noted that `.env.example` had been filled with the real values during setup; it was restored and never committed.

- **2026-09-19** — P0.1 done. Rewrote `.gitignore` (grouped; added `.venv-*/`, `.DS_Store`, `.vscode/*` with the two shared files re-included, `.github/modernize/`). Audited the staged set before committing: 56 files, no venvs, caches, snapshots, or secret patterns. Committed `AGENTS.md` (a read-only ChatGPT project mirror) unchanged so the tree is clean; if it gets replaced on a future sync, expect a diff there. `.venv-old/` (78 MB) is ignored but still on disk and can be deleted.

- **2026-09-19** — Created roadmap. Read README, verified baseline (`tsc` clean, 17 pytest passing, Node tests passing, Java 23 + Maven present). Found that TS fixtures have no tests and only MemMunkDB can run a patch → test loop today (drives P3.1 and P3.3). Recorded owner decisions: no deadline, agent loop + architecture diff as headline, all four sponsors as candidates, solo build with Claude.
