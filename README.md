# CodeMRI

**Compile codebases into context.** One persistent code world model, two consumers: developers in VS Code and coding agents through MCP.

**HackMIT 2026 · Local-first code understanding and agent context.**

This HackMIT prototype starts with a repository-wide system architecture view, then drills into modules and symbols. It inventories multiple languages, manifests, and deployment configuration; Tree-sitter provides Java and TS/JS symbol analysis. The persistent graph connects to source locations in VS Code. Local analysis, graph navigation, impact analysis, and context compilation need no API key or hosted service. AI architecture generation is optional and requires an OpenAI API key.

<img width="3232" height="1972" alt="3332112F-BB6D-473D-8CD5-6BCDAFF16B2B" src="https://github.com/user-attachments/assets/be735377-ec83-40b1-804c-b88e9cad1c91" />
<img width="3232" height="1972" alt="F891241F-8C54-406F-9C61-20D049AEE0D6" src="https://github.com/user-attachments/assets/52f03912-a538-417c-99a2-29da1175cbd7" />
<img width="1626" height="1500" alt="C7C93FE8-FE21-45EB-95B3-7784098E51D6" src="https://github.com/user-attachments/assets/4543dcef-01af-4747-b793-314d31082c98" />
<img width="1278" height="1630" alt="D87F3B04-54FF-410B-BA17-C4EE8379303F" src="https://github.com/user-attachments/assets/a69a7c51-933c-443d-ace7-c8b6d3455589" />


## Product thesis

Coding agents repeatedly reconstruct repository structure before making changes. CodeMRI persists that structural knowledge and makes it useful in two places: an evidence-backed architecture view beside the source, and a focused context pack for an agent.

The current prototype connects **repository → architecture → source navigation → heuristic impact → token-budgeted context**. The extension also supports isolated Codex proposals, file approval, baseline graph comparison, and architecture drafts. The remaining loop work connects compiled context to agent execution and structured test verification. The sections through **Current limitations and next steps** document the supplied implementation; **Product roadmap and design** describes remaining work and identifies existing foundations. [ROADMAP.md](ROADMAP.md) is the actionable task list, reconciled against the local source on 2026-09-20; read its handoff instructions before implementation.

> One persistent code world model. Two consumers: developers and coding agents.

## Contents

- [Quick start](#quick-start)
- [Current architecture](#architecture)
- [Repository-specific architecture maps](#gitdiagram-style-architecture)
- [What works now](#what-works-now)
- [API](#api)
- [MCP for coding agents](#mcp-for-coding-agents)
- [Validation](#validation)
- [HackMIT demo checklist](#hackmit-demo-checklist)
- [Current limitations and next steps](#current-limitations-and-next-steps)
- [Product roadmap and design](#product-roadmap-and-design)
- [Implementation priorities](#implementation-priorities)
- [90-second demo](#90-second-demo)
- [Benchmark plan](#benchmark-plan)
- [HackMIT sponsor alignment](#hackmit-sponsor-alignment)
- [Positioning](#positioning)

## Quick start

Requirements: a supported Node.js LTS compatible with this project (the existing setup specifies 20+), Python 3.11+, Git, and VS Code. Run these commands from this monorepo's root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
npm ci
npm run build
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

The tokenizer downloads its encoding on first context compilation; warm it once while online:

```sh
.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
```

Before launching the demo on a fresh checkout, clone the fixture as shown under [MemMunkDB demo](#memmunkdb-demo).

1. Open this monorepo in VS Code.
2. Press **F5**, using **CodeMRI: Demo extension**. This builds the extension and opens a separate Extension Development Host with `examples/MemMunkDB`.
3. In that new window, run **CodeMRI: Analyze Repository** from the command palette.
4. Start in Architecture. Click **LSM Store**, then open the implementation using its evidence link. For the TS symbol demo, open `examples/system-design` and drill into its checkout component. Move the editor cursor into another symbol to highlight its node or containing component. Use the layer selector or **All components** to navigate back. Click an edge to inspect evidence and open the referenced source.
5. Use the change laboratory to show blast radius and compile context. Copy the resulting pack for your coding agent.

To analyze a different repository, open its folder in the Extension Development Host. Restart the API with an explicit allowed parent directory:

```sh
CODEMRI_ALLOWED_ROOT=/absolute/path/to/projects python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

The backend must run on the same machine as the extension host. Set `codemri.apiUrl` if changing the port. Keep this unauthenticated development API on loopback. It intentionally does not enable browser CORS.

## Architecture

```text
apps/extension      VS Code host, source navigation, selection events
    media/          Local SVG webview: pan, zoom, search, impact highlighting
         | local HTTP / extension message bridge
services/api        FastAPI routes and input validation
         |
packages/engine     Tree-sitter → symbols + edges → persistent JSON snapshot
         |          Static impact expansion → token-budgeted context compiler
services/mcp        Agent tools over stdio; shares the engine and snapshot store
examples/system-design  System-design fixture: frontend, API, services, database, worker
examples/shop       Original small symbol-analysis fixture
```

`Graph` contains a schema version, canonical root, content revision, nodes, typed edges, and diagnostics. Nodes retain repository-relative paths, one-based source lines, UTF-16 columns, and source snippets. Calls point caller → callee; imports point importing module → imported module; containment points module → symbol.

Snapshots are stored transactionally in `.codemri/graphs.sqlite3`, outside the analyzed project by default when launched here. Existing JSON caches are migrated on the next scan. API and MCP must use the same working directory or the same absolute `CODEMRI_CACHE`. Snapshots include source code; keep them local and out of Git. Reanalysis updates the current snapshot and preserves the last-reviewed baseline. Editing source marks the panel stale; explicitly reanalyze to refresh it. Coding-chat runs analyze proposed edits in a separate copy; the working graph refreshes after explicit approval or discard. Symbol comparison matches declarations across offset changes.

## GitDiagram-style architecture

The highest level is now a **repository-specific system map**, with domain subsystem groups, actors, code components, storage cylinders, human-readable connection labels, and source evidence. Generic Frontend/API/Services buckets are no longer the final architecture diagram. ELK computes nested group layout and orthogonal connections; SVG renders locally in the VS Code webview. Double-click a component for its implementation module, then symbols; click a connection for source citations.

Two modes are deliberately distinct:

- **Analyze repository** runs locally without a key. The Java adapter discovers public classes, typed-receiver call patterns, HTTP contexts, served HTML resources, and filesystem access. JS/TS and Python retain existing import/call evidence. Source comments and HTML headings provide responsibility/UI context. It is a static, heuristic baseline, not complete semantic understanding or runtime tracing.
- **Generate AI architecture** adapts GitDiagram's architecture prompt and structured-graph approach. It reads the source inventory, README and bounded code excerpts, asks an OpenAI model for groups/nodes/relationships, then validates IDs, paths, and citation locations before persisting the result. AI relationships are marked inferred. Valid citation locations do not prove the model's interpretation is correct.

The AI output supports CALLS, IMPORTS, READS_FROM, WRITES_TO, ROUTES_TO, IMPLEMENTS, TESTED_BY, DEPENDS_ON, MUTATES, RETURNS, SERVES and DISPATCHES. The local adapter only emits relationships it can extract; it does not classify every database read/write or prove runtime behavior.

### AI setup (optional)

Create a local `.env` using `.env.example`; set `OPENAI_API_KEY` and `CODEMRI_ARCHITECTURE_MODEL` to a Responses API model available to your account that supports Structured Outputs. Never put a real key in source or chat. Start the backend with:

```sh
.venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

Click **Analyze repository**, then **Generate AI architecture**. The button sends sampled repository content to OpenAI and uses your API billing. Ordinary local analysis never makes an AI call. The input contains the inventoried file tree and up to 140,000 characters of excerpts (16,000 per file); omitted/truncated coverage is recorded. Errors preserve the current graph. Reanalysis refreshes the local graph; regenerate AI architecture after changes. Requests set `store: false`.

The roadmap records a live MemMunkDB generation on 2026-09-19. Quote-verified citation improvements have automated tests, but their follow-up live quality measurement remains pending. This documentation audit did not repeat paid requests. You must configure your key/model for generation. [Official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

### MemMunkDB demo

The demo launch configuration targets `examples/MemMunkDB`, a local checkout ignored by the parent project. On a fresh checkout, clone it before pressing F5:

```sh
git clone https://github.com/nicoleleehy1/MemMunkDB.git examples/MemMunkDB
```

The local map discovers RestServer, the HTML dashboard, LSMStore, Compactor, MemTable, WriteAheadLog, SSTable, SSTableIndex, the CLI demo, HTTP caller, and filesystem storage. It uses source patterns rather than a hardcoded MemMunkDB graph. Java modules display filenames and drill into AST-extracted methods/constructors. Double-clicking a function opens its source and shows a one-hop caller/callee graph; double-click another function to go deeper and use Back to retrace your steps. The other examples remain available by opening their folders manually.

**Analyze calls** (the former Analyze repository action) opens a source-derived repository graph. **Analyze hierarchy** runs the former Generate AI architecture action, scanning first if the saved snapshot is missing or stale. It sends sampled source to the configured AI backend. Navigate **repository → architecture component → module/package → file → declaration**, then double-click a class to see its methods or a function to explore its calls and nested declarations. Back restores the previous scope. The API also exposes `repository`, `packages`, `files`, and `hierarchy` projections; existing `architecture` and `modules` projections remain available.

**Find a symbol** lists matching indexed definitions and recorded call sites across the codebase, including file and line. Selecting a result opens the containing graph scope, selects its node, and reveals the source location. Navigation controls sit below the search and semantic-layer fields: Back on the left, Full Repository and Fit Graph on the right.

Class, function, and interface cards use dark navy containers, teal section headings, and wrapped chips. Class/interface cards show constructors, attributes, methods, and inheritance where present. Functions show parameters, local variables, nested functions, calls, return declarations/expressions, attributes, strings, and types. Type aliases, enums, constants, and globals are also inventoried for TS/JS. Other components retain the architecture shapes. ELK arranges dependency-driven columns and right-angle arrows. Long individual values are condensed; hover for their full text.

The graph sits on a dotted canvas with a muted gray frame. Clicking any node opens a pinned **Main node** panel on the left inside the same graph frame. A single click selects without changing graph depth; double-click (or Enter) drills down, while Space selects. The graph on the right remains available for drilldown and call exploration. A classification box identifies Architecture → Module/package → File/Class/Function/Interface, or the API endpoint, database entity, queue, or external-service category. Below it, **Function path** records the actual sequence of node clicks (including function-to-function jumps), with source links beside incoming calls or architecture relationships. Back restores the previous main node and path; closing the panel restores the full-width graph. Editor source navigation does not replace the pinned main node. Caller links open exact UTF-16 source columns in VS Code. Counts include each resolved source occurrence (including repeated calls by one caller), not runtime execution frequency; unresolved/dynamic calls are excluded. Reanalyze older snapshots to populate call locations.

Each card section has an SF Symbols order icon to switch between alphabetical and source order (first occurrence for calls, declaration order for other labels). Calls have direct source-occurrence count badges and a Select all/Clear calls control that highlights their labels, resolved callees, and connections. Clicking a call label opens a top-right popup with counts in the selected main function and across its reachable resolved subgraphs, plus exact source links. Recursive and converging paths count each physical source occurrence once, not once per traversal. Unresolved library calls are counted by exact label; their unknown subgraphs cannot be traversed. These are static source counts, not runtime execution counts. Older snapshots show unknown badges until reanalysis.

The local repository graph also includes detected literal Java HTTP contexts, common JS/TS route declarations, Python route decorators, SQL/Prisma entity declarations, and explicitly declared queue services. Discovery is partial, static, and source-backed; dynamic routes, undeclared infrastructure, and full runtime/type resolution are not inferred. Function call chips include source expressions, while graph call edges include resolved targets only. Restart the backend, rebuild/reload the extension, and **Analyze repository** again to populate the new hierarchy and card details in existing snapshots.

Architecture graph fields include `groups`, `mode`, `explanation`, node `shape`/`group`, and edge `label`/`evidence`. The same graph is returned through MCP `get_architecture`. Source-specific modules are linked through `component_id`/`module_id`; AI responsibilities may share an implementation file.

The adapted prompt retains GitDiagram's MIT copyright notice in `third_party/gitdiagram/LICENSE`; see `third_party/gitdiagram/NOTICE.md` for upstream revision and attribution. CodeMRI uses its own Python validation and VS Code rendering rather than embedding GitDiagram's hosted website.

## What works now

The implementation baseline documented here includes:

- Repository-wide inventory and evidence-backed system maps with nested ELK layout and local SVG rendering.
- Java classes, methods, constructors, and bounded receiver-type call tracing; MemMunkDB architecture drilldown and source evidence.
- Optional AI-generated architecture with validated references and explicitly inferred relationships; automated provider tests plus a historical live MemMunkDB run recorded in the roadmap; follow-up citation quality measurement remains pending.
- Functions, arrow-function variables, classes, methods, interfaces, and type aliases from TS/TSX/JS/JSX.
- Relative module import edges and direct identifier calls, including named import aliases.
- Interactive graph with source navigation, editor selection highlighting, pan/zoom, symbol search, and optional module nodes.
- Static change-impact prototype: lexical symbol/path seeds plus up to three reverse call hops, with reasons.
- Context compiler: relevant symbols, callers and direct dependencies packed into a real `cl100k_base` token budget; returns selected/excluded IDs and full-source token counts.
- SQLite working snapshots and reviewed baselines consumed by the shared engine; HTTP API and MCP read the same store.
- Baseline symbol/edge comparison, graph change highlighting, and review controls.
- Isolated Codex coding proposals, whole-file approval/discard, and pending-proposal restoration.
- Create mode: editable architecture drafts, local validation, read-only Codex assessment, and reviewed implementation proposals.
- Context-budget slider, copyable context, and selected-symbol highlighting.

These capabilities are present in source and have relevant automated tests; this documentation reconciliation is not a fresh test or manual F5 run.

## API

Open `http://127.0.0.1:8000/docs` for the generated request/response playground.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Service availability |
| `GET /ai/status` | Backend AI configuration status; never returns the key |
| `POST /analyze` | `{ "root": "/absolute/repository" }` → repository ID and graph |
| `GET /graphs/{repo_id}` | Load a persisted graph |
| `POST /graphs/{repo_id}/impact` | `{ "query": "change applyCoupon", "seed_ids": [] }` |
| `POST /graphs/{repo_id}/context` | Same request plus `"budget": 4000` |
| `GET /graphs/{repo_id}/freshness` | Compare indexed source revision without replacing saved graph |
| `POST /graphs/{repo_id}/architecture-ai` | Explicit AI architecture generation |
| `POST /graphs/{repo_id}/review` | `{ "revision": "..." }` → advance reviewed baseline |
| `POST /preview` | `{ "root": "...", "files": [{ "path": "...", "before": "...", "after": "..." }] }` → isolated proposal graph preview; null before/after represents addition/deletion |

`packages/engine/codemri/models.py` is the Python graph contract. The extension's matching interfaces are in `apps/extension/src/extension.ts`. Context and impact functions are isolated in `context.py` so semantic ranking can replace lexical matching without changing consumers.

## MCP for coding agents

Launch with `.venv/bin/python -m services.mcp.server` from the monorepo root. Example generic MCP client configuration (replace every absolute path):

```json
{
  "mcpServers": {
    "codemri": {
      "command": "/absolute/CodeMRI/.venv/bin/python",
      "args": ["-m", "services.mcp.server"],
      "env": {
        "PYTHONPATH": "/absolute/CodeMRI",
        "CODEMRI_ALLOWED_ROOT": "/absolute/projects",
        "CODEMRI_CACHE": "/absolute/CodeMRI/.codemri"
      }
    }
  }
}
```

Available tools: `analyze_repository`, `get_architecture`, `get_symbol`, `find_callers`, `find_callees`, `impact_analysis`, `compile_agent_context`. First analyze a repository, then use the returned `repo_id`. Stdout is reserved for the MCP protocol. These tools read code; they do not execute repository code or apply patches.

## Validation

Run these checks in the implementation repository. The coverage below describes the existing project documentation; updating this README does not constitute a fresh test run.

```sh
npm run check
npm run build
npm test
```

Tests cover the demo call chain, import aliases, reverse impact, token budgets, persistence, TSX and UTF-16 positions, ignored dependencies, content revisions, parse diagnostics, the API round trip, a real MCP stdio handshake/tool call, the extension navigation message bridge (mocked VS Code host), architecture drilldown membership, a Python-only repo, configuration revision changes, and evidence-backed edge types. The F5 demo remains the manual acceptance check for VS Code focus and navigation.

## HackMIT demo checklist

- [ ] Restart the backend and launch F5 with the MemMunkDB example.
- [ ] Run Analyze repository and show the grouped Java system map.
- [ ] Follow HTTP client → REST server → LSM store → mutable/persistent storage.
- [ ] Click the dashboard connection and open its source evidence.
- [ ] Click the WAL/compaction connections and inspect concrete calls.
- [ ] Click LSM Store → LSMStore.java → put(String key, String value).
- [ ] Follow maybeFlush() → flushMemTable() → SSTable.flush(...); use Back to return.
- [ ] If configured, generate AI architecture and compare its semantic labels/grouping to the local baseline.
- [ ] For impact/context, open `examples/system-design` and analyze its TS code.
- [ ] Demonstrate graph↔code sync and context compilation on `checkout`/`applyCoupon`.
- [ ] Show actual token counts, without claiming benchmarked agent savings.

## Current limitations and next steps

This is the foundation of the persistent semantic world model, not yet a complete semantic execution graph. Tree-sitter gives syntax, not type resolution. Direct identifier resolution is a prototype: lexical shadowing, re-exports, default/namespace imports, tsconfig aliases, dynamic dispatch, callbacks and framework-specific routes are not resolved reliably. Member calls are deliberately reported as unresolved. Files over 1 MB, symlinks, dependency/build folders are skipped; `.gitignore` is not yet interpreted. Large repositories need incremental indexing, limits and graph virtualization.

Impact is heuristic, not a guarantee that a change is safe. Context retrieval uses lexical matching and greedy whole-symbol packing; it does not prove dependency completeness. The budget covers the emitted text with `cl100k_base`, excluding any additional agent message wrappers. Other model tokenizers may differ. Snapshots can go stale; disk contents are the source of truth and unsaved edits are not indexed.

Stretch roadmap, in order:

1. Full Java type/overload resolution, TypeScript language-service resolution, incremental indexing and stable symbol identities.
2. Semantic summaries/embeddings and task-aware ranking with retrieval benchmarks.
3. Arbitrary historical snapshot comparison and PR mode; working-versus-reviewed symbol/edge comparison already exists.
4. Test discovery, impacted-test selection, and an explicit agent patch → test → graph-refresh loop.
5. Git history and provenance, execution traces, route/data relationships.

Implementation references: [Tree-sitter Python bindings](https://github.com/tree-sitter/py-tree-sitter), [VS Code webview API](https://code.visualstudio.com/api/extension-guides/webview), [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/).

### Java call tracing limits

Methods and constructors are extracted with Tree-sitter Java, with UTF-16 source columns.
Calls resolve by receiver type (fields, parameters, locals, static class references),
method name, and argument count. Basic inherited methods are included. Same-arity
overloads, generic/chained expression receivers, external libraries and dynamic dispatch
may remain unresolved. This is static navigation, not a captured runtime trace.

Architecture nodes/wiring are generated from repository data, not a saved MemMunkDB
map. Fixed rules classify roles/shapes and named API patterns; those heuristics can
misclassify unfamiliar systems. Group-relative ELK edges and labels are translated into
root coordinates before drawing, including edges kept in the root edge array.

## Product roadmap and design

**Use ROADMAP.md task statuses for implementation. Existing foundations are called out below; the remaining designs are proposals, not instructions to rebuild delivered features.** Preserve the existing Python engine, API/MCP contracts, npm workspace, and SVG/ELK webview. React Flow, a separate TypeScript MCP service, pnpm, and the earlier `apps/backend` layout were planning alternatives; they are not prerequisites or migration requirements.

### Recommended stack and repository layout

| Layer | Existing choice | Direction |
|---|---|---|
| Extension | TypeScript, VS Code API, local SVG webview | Extend the current message bridge and navigation |
| Layout | ELK nested layout and orthogonal edges | Improve focused views and large-graph performance |
| Analysis | Python, Tree-sitter Java and TS/JS, repository inventory | Improve resolution before adding broad language claims |
| API | FastAPI in `services/api` | Preserve validated repository boundaries |
| Persistence | SQLite current graph + reviewed baseline, legacy JSON migration | Add retained historical versions and incremental updates |
| Context | Lexical retrieval, greedy symbol packing, tiktoken | Measure retrieval quality before semantic ranking |
| Agent tools | Python MCP server over stdio | Keep API and MCP on the same engine/cache |
| AI architecture | Optional OpenAI structured output | Preserve inferred labels, source evidence, and disclosure |
| Workspace | npm lockfile and root Python environment | Use the existing Quick start; no re-scaffolding needed |

```text
CodeMRI/
├── apps/extension/          # Host, source navigation, local SVG webview
├── services/api/            # FastAPI entry point and routes
├── services/mcp/            # Python stdio MCP server
├── packages/engine/codemri/ # Models, analysis, impact, context, persistence
├── examples/
│   ├── MemMunkDB/           # Separately cloned, ignored Java demo
│   ├── system-design/       # TS architecture and impact/context demo
│   └── shop/                # Small symbol-analysis fixture
├── third_party/gitdiagram/ # Required upstream attribution
├── requirements-lock.txt
├── package.json
├── package-lock.json
└── .env.example
```

### Graph contract: current and future

The implementation contract is `packages/engine/codemri/models.py`, with matching extension interfaces in `apps/extension/src/extension.ts`. Current graphs carry schema/root/revision metadata, nodes, typed edges, diagnostics, source snippets, and source coordinates. Architecture adds groups, mode/explanation, node shapes/group membership, edge labels/evidence, and component/module links.

Future schema changes should be versioned and keep both consumers compatible. Add explicit snapshot identity, analyzer/model configuration versions, evidence classification, and unresolved-reference reasons where absent. Distinguish static extraction, inferred relationships, and observed runtime evidence.

Current symbol IDs include byte offsets and can change after edits. Stable qualified identities and explicit rename/move matching are future work; do not assume IDs already survive reanalysis. Preserve one-based source lines and UTF-16 editor columns, and test non-ASCII source navigation.

### VS Code UX extensions

Keep the architecture-first experience: system → component → module → symbol. Retain source evidence on edges, one-hop call navigation, Back, layer selection, and All components. Add modes only when their underlying analysis exists:

| Mode | Intended question |
|---|---|
| Architecture | How is this repository organized? |
| Calls | What calls this symbol, and what does it call? |
| Data | Where can this value flow? |
| Tests | Which tests are associated with this behavior? |
| History | How did this structure change over time? |

Pinned main-node panels, symbol cards, navigation paths, keyboard selection/drilldown, and call-count badges already exist. Remaining polish includes context-menu actions and editor CodeLens caller/test counts. Debounce selection events and prevent graph/editor feedback loops. Keep stale-state warnings until reanalysis finishes; automatic incremental refresh is not implemented yet.

Future command-palette shortcuts can cover Explain Current Symbol, Trace Current Symbol, Find Tests, Compile Agent Context, Ask About Architecture, View Git History, and Compare Architecture. Trace navigation, context compilation, and baseline comparison already exist inside the webview. These are additions to the existing Analyze Repository workflow, not a list of commands currently registered.

### Natural-language graph queries

Extend current symbol search with evidence-backed questions such as “Where is authentication handled?”, “What calls the payment provider?”, and “What happens after this route?” Return an answer and a focused subgraph together, with clickable source references. Use lexical retrieval first and optional embeddings later. Never turn unsupported model suggestions into verified static relationships.

### Semantic world model

Persist architecture, module, symbol, contract/resource, test, and historical layers. Relationships can include CALLS, IMPORTS, READS_FROM, WRITES_TO, ROUTES_TO, IMPLEMENTS, TESTED_BY, DEPENDS_ON, MUTATES, RETURNS, SERVES, and DISPATCHES, but supporting a label in the schema does not mean every analyzer can extract it.

AI may propose architectural groups and relationships in the optional generation mode. The local structural analysis remains independent of AI, and generated relationships stay inferred even when their citation locations validate. A static path is possible behavior, not an observed execution trace.


### Richer change impact and blast radius

The current implementation uses lexical symbol/path seeds and at most three reverse call hops. The following is a proposed richer algorithm, including future diff-based seeds:

Given a task, selected symbol, or Git diff:

1. Find seed symbols using exact names, source changes, lexical search, and optional embeddings.
2. Allow the user to inspect or correct seeds.
3. Traverse typed edges in the direction appropriate to the change.
4. Add relevant contracts, callers, resources, and tests.
5. Rank likely impact and retain the path explaining each inclusion.

Suggested initial edge weights are tunable heuristics:

| Relationship | Starting weight |
|---|---:|
| Direct call | 1.00 |
| Data write | 0.95 |
| Type dependency | 0.85 |
| Import | 0.55 |
| Semantic similarity | 0.35 |

One practical propagation score is:

```text
impact(v) = max over seed-to-v paths p:
            seed_relevance(p.start) × decay^length(p)
            × product(edge_weight(e) × edge_confidence(e))
```

Bound traversal by depth and score, track visited states, and stop cycles. A changed callee can affect callers; a changed caller does not necessarily require changing every callee. Keep impact candidates separate from dependencies included merely to understand a task.

Show **directly changed/targeted**, **likely affected**, and **possibly related** groups. These are review aids, not guarantees of breakage. An explanation should cite a concrete relationship and source location—for example, a value flowing into order serialization—rather than saying only “related to the change.”

### Context compiler evolution

The current compiler packs whole symbols using lexical relevance and a real `cl100k_base` budget, with selected/excluded IDs and full-source counts. Its budget excludes agent message wrappers. The following design extends it with richer ranking, dependency accounting, and representation choices.

#### Retrieval objective

For graph `G = (V, E)`, task `q`, budget `B`, and selected set `S`:

```text
maximize  relevance(S, q) + λ × dependency_coverage(S) − μ × redundancy(S)
subject to tokens(serialized_context(S)) ≤ B
```

This is a design objective; the hackathon implementation uses a greedy approximation, not an exact optimizer or a claim to find the globally smallest context.

#### Practical algorithm

1. Rank seed symbols with lexical matching and optional semantic similarity.
2. Expand through calls, types, data relationships, and tests.
3. Reserve budget for the task, graph explanation, metadata, and test instructions.
4. Include essential source and contracts first.
5. Rank additional candidates by marginal relevance/coverage gained per token.
6. Use full source for primary edit targets; use signatures or summaries for peripheral dependencies.
7. Deduplicate overlapping source ranges and preserve file boundaries.
8. Tokenize the final serialized pack and trim optional content until it fits.
9. Report excluded dependencies, unresolved edges, and any essential context that could not fit.

If mandatory content exceeds the budget, surface the shortfall and ask for a larger budget or narrower task. Never silently claim completeness. Budgeting must use the chosen model's tokenizer or identify counts as estimates.

#### Context pack

Include task and constraints, repository/snapshot identity, selected symbols, exact source ranges, relevant source, dependency explanations, contracts, tests and suggested commands, omissions, and token accounting. Offer Markdown for copy/paste and JSON for tools.

#### Heatmap and budget slider

The budget slider, copy action, and selected-symbol highlighting already exist. Remaining work is the included/supporting/excluded presentation, JSON export, and explicit context-pack handoff to the agent. The mockup below shows the target state.

```text
Context budget     2K ──────●────────── 32K

Included           CouponEngine, calculatePrice, CheckoutService
Supporting         Order type, checkout tests
Excluded           Analytics, recommendations, admin dashboard

[Copy Context] [Export JSON] [Send to Agent]
```

As the budget increases, add supporting contracts, tests, controllers, and nearby behavior. Use labels with the heatmap: required, strongly relevant, possibly relevant, and excluded. Raw scores belong in an advanced inspector.

**Illustrative only:** reducing a 73,421-token source corpus to a 6,814-token pack is approximately 90.7% less source context. That comparison does not measure total agent-token savings; agent retries, tool responses, and indexing/enrichment costs must also be counted.

### Future MCP tools and agent execution

Keep the shipped names documented above: `analyze_repository`, `get_architecture`, `get_symbol`, `find_callers`, `find_callees`, `impact_analysis`, and `compile_agent_context`. Future tools can add test discovery, cited symbol explanations, candidate paths, and change history. Avoid introducing a second incompatible naming scheme merely to match an earlier plan.

The next agent loop is:

```text
Task → impact → compile_agent_context → compatible agent
  → review patch → run tests → explicitly reanalyze → graph diff
```

Copying a context pack and local Codex coding proposals are implemented, including manual whole-file application, proposal graph previews, and reviewed-baseline comparisons. Coding chat currently passes task/chat text, not the compiled context pack. Remaining work connects impact/context to execution, adds a structured isolated test runner and result capture, and records the complete loop. The CLI can execute commands, but that alone is not test discovery or structured verification. Devin and Warp integrations remain unverified.

If the client provides activity events, show which symbols the agent reads/edits and which tests run. “Why this context?” should explain retrieval evidence, not expose or invent hidden model reasoning. Keep code-reading tools separate from authorized execution and patch actions.


### Architecture diff and PR mode

Working-versus-reviewed symbol/edge comparison and proposal overlays already exist. Extend them to arbitrary retained snapshots, architecture-layer semantic changes, and PR merge-base comparison:

```text
Before: CheckoutService → PaymentService
After:  CheckoutService → CouponEngine → PaymentService
                       ↘ PaymentService
```

Report added/removed symbols, modified signatures, changed dependencies, affected entry points, test mappings, and newly introduced cycles. Do not mistake line shifts for new symbols.

Architecture regression rules can flag a new dependency such as UI → database infrastructure when a configured boundary requires UI → API → service → database. Rules should be explicit; observed conventions alone are suggestions.

**PR mode** compares the PR head against its merge base, seeds impact analysis from changed symbols, and presents an architecture summary, affected tests, context pack, and unresolved risks. Keep line-level diffs available. Posting review comments is a later integration requiring an explicit user action.

### History, tests, and deeper analysis

#### Git history and time machine

A history slider selects indexed commits and shows symbols and edges appearing, disappearing, or moving. Start with two real snapshots and symbol-specific Git history before implementing continuous scrubbing.

The **Why does this exist?** action combines blame, commit diffs/messages, comments, and available PR/issue evidence. Link explanations to commits and distinguish documented intent from inference. When the reason is absent, say so. Avoid modifying the user's checkout to browse history; read Git objects or use isolated snapshots.

#### Tests and test mapping

Represent tests as graph nodes. Build mappings from imports, direct calls, fixture relationships, framework conventions, and later coverage/runtime data. Label heuristic associations separately from observed execution.

For a change, show related tests and run the selected subset through a configured runner. A green node means the displayed test result passed; it does not prove all behavior is correct. Run a broader suite as a regression check during benchmarking.

Test-gap detection can flag high-impact symbols with **no identified tests**. That wording is more accurate than “untested” when mapping is incomplete. An optional agent action can generate a test and return it for review.

#### Static paths and runtime traces

Trace a path from an entry point through controllers, services, and external resources. Animate source-backed steps for presentation, but label the view **static candidate path** unless instrumentation observed it. Later, ingest test coverage or runtime telemetry and visually distinguish observed edges.

#### Data-flow mode

Select a value such as `user.email` and explore input → validation → transformation → persistence. Begin with local assignments and explicit argument/return relationships. Interprocedural aliasing, dynamic properties, and full taint analysis are later work.

Sensitive-data tracing can eventually identify possible flows to logs or external APIs, with evidence and uncertainty attached. It should not be presented as a complete security audit.

#### Repository health

An optional dashboard summarizes symbol/module counts, cycles, highly coupled modules, configured boundary violations, and high-impact symbols without identified tests. Explain how each metric is calculated and link to its supporting subgraph.

### Caching and incremental indexing

Current persistence stores the latest graph and a last-reviewed baseline in SQLite. The following cache invalidation and incremental-update strategy is future work; the current UI marks edits stale and requires explicit reanalysis.

- Hash file contents; skip unchanged files.
- Re-extract changed files and remove deleted symbols/edges.
- Invalidate dependent resolution when exports, imports, or signatures change.
- Include analyzer, grammar, configuration, and schema versions in cache keys.
- Cache semantic summaries by source plus relevant dependency hashes, model, and prompt version.
- Cache embeddings by exact content and embedding-model version.
- Cache context results by task, budget, snapshot, and retrieval configuration.
- Batch file events and publish atomic snapshots so clients never mix old nodes with new edges.

Start with changed-file reparsing. Reusing Tree-sitter syntax trees is a later optimization; syntax-tree reuse alone does not update the semantic graph. Show indexing freshness and provide a full rebuild action.

## Implementation priorities

P0 means stabilize the existing prototype, not rebuild it using the original scaffold.

| Priority | Work | Completion evidence |
|---|---|---|
| P0 | Reproduce install/build and MemMunkDB launch | Fresh setup, local map, source links, drilldown, Back |
| P0 | Verify Java/TS navigation and evidence | Real source locations; unresolved cases remain visible |
| P0 | Demonstrate TS impact/context | Explain lexical seeds/reverse hops and actual token counts |
| P0 | Confirm API/MCP parity | Both read the same snapshot/cache; real tool handshake |
| P0 | Present limitations accurately | No claims of runtime traces, completed agent edits, or measured savings without evidence |
| P1 | Stable identities and better Java/TS resolution | Accuracy fixtures for overloads, imports, shadowing, and edits |
| P1 | Incremental indexing and bounded rendering | Correct invalidation, freshness, and responsive larger graphs |
| P1 | Retrieval benchmark and context UI | Measured quality, budget slider, explainable selection |
| P1 | Historical snapshots and richer architecture diff | Extend existing baseline diff to history, rename/move, cycles, and architecture-layer changes |
| P1 | Context handoff, tests, and one recorded agent loop | Extend existing Codex proposals with compiled context and structured test results |
| P2 | History, PR mode, health, data flow | Evidence-backed views on real repositories |
| P2 | Runtime observation, security, collaboration | Separate observed evidence and appropriate isolation |

Work in phases: **reproduce → harden analysis → measure retrieval → integrate one agent → add historical/advanced views**. Preserve the working demo before pursuing optional features. AI architecture generation is optional; distinguish the historical live run from follow-up improvements whose live quality remains unmeasured.

## 90-second demo

The current demo should showcase shipped behavior, with a brief transition from Java architecture to TS impact/context. Pre-open both example workspaces and run a rehearsal so the switch is predictable.

| Time | Action | Narration |
|---|---|---|
| 0–10s | Show MemMunkDB in the Extension Development Host. | “CodeMRI gives developers and agents one persistent map of a repository.” |
| 10–25s | Analyze and show the repository-specific system map. | “This local analysis finds the REST server, LSM store, storage structures, and their source evidence.” |
| 25–40s | Open LSM Store, a Java method, and a caller/callee step; use Back. | “We move from architecture into implementation and back to the source.” |
| 40–50s | Click a storage/dashboard edge and its citation. | “Relationships are inspectable, with static-analysis limits made explicit.” |
| 50–63s | Switch to the prepared system-design example and show checkout impact. | “For a proposed change, we expand from matching symbols through callers.” |
| 63–80s | Compile context and show the real token count and selected symbols. | “The compiler packs relevant code within this token budget, ready to copy or retrieve through MCP.” |
| 80–90s | Show the context pack and finish on the graph. | “CodeMRI compiles codebases into context.” |

Optional AI architecture generation can be shown in a separate segment after configuring and testing it. Do not make network latency or billing a dependency of the main demo.

Once the complete context/agent/test loop is verified, replace part of the navigation segment with a real patch, structured test result, and graph diff. Proposal editing and baseline diff already exist. Label recorded or precomputed runs. Context-size reduction alone is not evidence of end-to-end agent savings.


## Benchmark plan

Measure whether context retrieval improves efficiency **without reducing correctness**.

### Tasks and controls

Use a fixed repository revision and tasks such as changing checkout rules, adding a database field, fixing an authentication bug, and adding an OAuth provider. Keep the model/version, instructions, tools, timeout, environment, and starting state comparable.

Compare:

1. **Baseline:** agent with normal repository search/read tools.
2. **CodeMRI:** same agent with graph/context tools and the same fallback tools.

A full-repository token count is a separate descriptive reference, not a substitute for an actual baseline agent run. Do not seed the CodeMRI path with the known patch or hidden test answers. Repeat runs when possible and report failures as well as successful attempts.

### Measurements

| Metric | What to record |
|---|---|
| Input/output tokens | Full agent run, including tool responses and retries |
| Context-pack size | Serialized pack and tokenizer used |
| Tool calls/files read | Exploration and execution separately |
| Time | Indexing, retrieval, agent execution, and tests |
| Cost | Actual model usage at the recorded rate/date |
| Correctness | Targeted tests, broader suite, and patch review |
| Retrieval quality | Relevant symbols found/missed and unnecessary inclusions |
| Index quality | False/missing edges and unresolved references on labeled fixtures |
| Cache effects | Cold index, warm index, and incremental update results |

Report setup/enrichment cost separately and include it in first-use totals. Show amortization over repeated tasks rather than hiding preprocessing cost. Use median/range across repeated runs when available.

```text
input-token reduction = 100 × (baseline_input − codemri_input) / baseline_input
speedup = baseline_elapsed / codemri_elapsed
```

Do not calculate a ratio with a zero denominator. Token reduction and dollar savings are distinct because output, cached tokens, and model rates may differ.

### Results template

| Task | Variant | Input tokens | Output tokens | Tool calls | Time | Tests | Review |
|---|---|---:|---:|---:|---:|---|---|
| Multiple coupons | Baseline | — | — | — | — | Not run | Pending |
| Multiple coupons | CodeMRI | — | — | — | — | Not run | Pending |

Preserve prompts, commit hashes, raw usage records, test commands/results, patches, and configuration under `benchmarks/`. A single successful demo is evidence for that task, not a universal performance claim.

## HackMIT sponsor alignment

These are **candidate alignments from the project brainstorming**, not verified 2026 eligibility or prize claims. Check the event's current challenge pack and required integrations before submitting. The original conversation referenced a challenge PDF; this README does not reproduce or independently certify its rules.

| Candidate sponsor | CodeMRI connection | Evidence to prepare |
|---|---|---|
| Warp | Understanding, modifying, and testing software | A working developer workflow and any required actual integration |
| OpenAI | Semantic enrichment, task interpretation, coding-agent workflow | Meaningful API use plus a record of how Codex assisted implementation/testing |
| Token Company | Smaller model inputs, reuse, caching, context compilation | End-to-end measured usage and cost, including preprocessing; verify required product use |
| Cognition | Agent consumes a context pack and implements a change | A real Devin integration if pursued; exported context alone is not proof of integration |

Prioritize the product and demonstrable evidence. Add a sponsor integration only when it contributes to the working flow and meets the actual challenge requirements. Sponsor alignment cannot guarantee an award.

## Security and longer-term roadmap

Preserve the existing loopback-only API, allowed-root validation, local snapshot handling, and explicit AI-generation action. Strengthen secret exclusion and cache deletion before broader distribution. The current analyzer does not interpret `.gitignore`; do not assume ignored secrets are automatically excluded from analysis or AI excerpts. Bind the backend to loopback; validate repository roots and webview messages. Use a restrictive webview content security policy.

Repository comments, documentation, commit messages, and retrieved text are untrusted data. Preserve their provenance in context packs and keep them separate from agent instructions. Do not execute repository scripts merely to index source. Test execution and agent edits are explicit workflow actions.

Future work includes:

- Deeper TypeScript resolution and additional languages/framework adapters.
- Observed runtime paths and coverage-backed test selection.
- Interprocedural data-flow and possible sensitive-data exposure paths.
- Architecture rules, drift detection, and CI/PR summaries.
- Historical architecture snapshots and cited decision timelines.
- Shared team annotations and collaborative graph exploration.
- Task memory: reusable retrieval hints from successful changes, validated against current snapshots.
- Repository health trends and test-generation suggestions.
- Secure remote graph services with authentication, repository isolation, and access controls.

## Positioning

**Primary tagline:** Compile codebases into context.

**One-line pitch:** CodeMRI turns a repository into a persistent semantic graph so developers and coding agents can explore dependencies, assess change impact, and retrieve focused context for a task.

**Technical pitch:** AST analysis → symbol resolution → evidence-backed graph → task-conditioned retrieval → token-budgeted context compilation → agent execution → impact verification.

**Product promise:** See the system behind the source.

**Supporting lines:**

- One world model. Two consumers: developers and agents.
- Understand the architecture. Explain the impact. Compile the context.
- A semantic map beside your code—and a context engine behind your agent.

The current HackMIT deliverable is **real code → evidence-backed architecture → source navigation → heuristic impact → token-budgeted context**. The next milestone connects existing proposals and graph review into **compiled context → agent patch → structured tests → refreshed graph → verified diff**.


### Coding chat and graph review

Scroll to **Build with CodeMRI**, enter a prompt, and choose **Send to Codex**. Install the Codex CLI and run `codex login` first; set the machine setting `codemri.codexPath` if the executable is not on VS Code's PATH. Save dirty editor buffers before sending. Each turn runs in a separate temporary copy with recent chat context, the workspace-write sandbox, and no interactive elevation. The copy excludes Git metadata, dependency directories, and symlinks. Agent edits do not touch your working files. Stop cancels the agent; any partial edits still require approval.

After each run, **Changes have been made!** lists proposed file changes above the graph. Hover a row number (or focus it with the keyboard) to reveal its checkbox; selected checkboxes stay visible. Click a row to inspect red `−` removals, green `+` additions, and old/new line numbers. **Approve selected** applies entire selected files; **Delete selected** discards those proposals. Changes within a file are reviewed together. Newer disk edits, dirty editor buffers, and symlink targets block approval. Resolve pending proposals before the next prompt. A local manifest lets the extension restore pending proposals after reload while the temporary directory exists. Binary changes are not supported.

The preview graph shows proposed changes without replacing the stored working graph. Approving or discarding all proposals returns to the working graph; unsupported source files still have a text diff even if they have no graph nodes. Click a change or use Previous/Next to navigate. Yellow outlines and bold yellow labels indicate changed areas, and changed connections are thick yellow. Removed items open the previous snapshot; live-source navigation is disabled in that view. Full Repository returns to the current snapshot. **Mark reviewed** advances the baseline without committing or discarding code. External edits are included on the next manual scan; unsupported/unindexed files are outside this review's coverage.

SQLite is the recommended persistence for this local extension: it needs no database server and atomically updates graph snapshots and review baselines. API and MCP must share an absolute `CODEMRI_CACHE` for persistence across launch directories. The database contains source, so keep it outside version control. A future shared hosted service should use PostgreSQL for repository/session metadata and object storage for larger immutable graph snapshots; a dedicated graph database is unnecessary for the current in-memory traversals.

The agent integration follows [OpenAI's non-interactive Codex documentation](https://learn.chatgpt.com/docs/non-interactive-mode). Chat text is rendered as plain text. Authentication remains with the local CLI; CodeMRI does not collect an API key. This implementation supports Codex, not a Claude Code provider or full parity with either product's UI.

### Create: propose architecture changes

Open **Create** after analyzing a repository to edit a saved architecture draft. Add or remove components, edit responsibilities, draw typed connections, drag nodes, and undo/redo. Start from the existing architecture or a blank additive canvas. Layout changes do not request code changes.

Describe intent and acceptance criteria, then use **Check locally** (no model tokens), **Assess & plan with Codex** (read-only source assessment), and **Implement reviewed plan**. Implementation uses the existing temporary-copy/file-approval workflow. Source changes and semantic draft edits invalidate old plans. Drafts save locally in VS Code workspace state. Restart the backend and reload the rebuilt extension to enable the new freshness endpoint and editor.

See [Create mode scope and limitations](docs/create-mode.md) for persistence, removal semantics, verification, and the boundaries of feasibility checks.
