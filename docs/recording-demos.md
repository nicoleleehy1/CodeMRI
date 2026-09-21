# Recording demos

## LSM: add authentication

Choose **CodeMRI: Demo extension** in Run and Debug, then press F5. Its workspace is `examples/MemMunkDB`, restored to upstream commit `fba5ee2` without the authentication additions. Reanalyze before recording so the displayed architecture reflects the restored source. Replace any previous Create draft with a fresh draft; drafts persist in VS Code workspace state.

The previous authentication source and compiled build are backed up under `.codemri/demo-backups/memmunk-auth-20260920-073248/`. The backup is outside the demo repository and ignored by the parent repository.

## Stoich: create your next change

Choose **CodeMRI: Stoich create demo** in Run and Debug, then press F5. This opens the separate, unmodified clone in `examples/Stoich` (baseline `1a0fdb99dd1e0bec9ea6c0c649e024edd4559bee`). To recreate it on another machine:

```sh
git clone https://github.com/nicoleleehy1/Stoich.git examples/Stoich
```

Analyze the repository, open **Create your next change**, and choose a blank additive draft. Draw three components left to right:

```text
Compounds pane → CSV exporter → Browser download
```

Use these responsibilities and edge descriptions:

| Component | Responsibility |
| --- | --- |
| Compounds pane | Existing `app/components/CompoundsPane.tsx`: display the compounds from `app/lab/page.tsx`; add an Export CSV button. Reuse the existing pane. |
| CSV exporter | New browser-side utility: serialize name, iupac, smiles, role, and one_line into CSV with a header and correct escaping. |
| Browser download | Download the serialized CSV as `stoich-compounds.csv` using a Blob and temporary object URL; release the URL afterward. This is browser behavior, not a backend service. |

Label the first edge **passes currently displayed compounds on Export CSV click** and the second **downloads CSV in the browser**.

Paste this intent:

> Add an Export CSV button to the existing compounds pane. Export the currently displayed compounds with columns name, iupac, smiles, role, and one_line. Implement the CSV serializer as a small reusable client-side utility and download stoich-compounds.csv in the browser. Preserve the existing extraction and rendering behavior. Do not introduce an API endpoint, database collection, or model call.

Acceptance criteria:

- Export is disabled while loading or when there are no compounds.
- CSV includes the header and one row per displayed compound, in display order.
- Null values become empty cells; commas, quotes, and line breaks are escaped correctly.
- Clicking Export downloads `stoich-compounds.csv` and cleans up its object URL.
- Verify with a small compound fixture; export itself makes no network request.

Then run **Check locally**, **Assess & plan with Codex**, and **Implement reviewed plan**, and review the proposed diff. The feature is intentionally not implemented in the baseline so it can be created during recording. Source analysis needs no Stoich dependencies or service credentials; running the full Stoich application and its extraction features requires its own dependencies and external service configuration.
