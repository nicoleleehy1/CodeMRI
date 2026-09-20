# Benchmarks

Harness for measuring whether CodeMRI context helps an agent, without changing anything else.

- `tasks/*.json` — task definitions: repo path, task text, budget, timeouts. The task text is all the agent gets;
  the CodeMRI variant additionally receives the context pack compiled *from that text*. Known patches and hidden
  tests are never given to either variant.
- `run.py` — runs one task with both variants (`baseline` = task only, `codemri` = task + pack) using the same agent
  command, then appends a row to `results.jsonl` and stores full artifacts under `runs/`.
- `runs/` — per-run `run.json`, `prompt.txt`, `patch.diff`, `tests.json`, `graph-diff.json`. Every record carries
  `recorded: false` until a person verifies and labels a real run; mock-agent runs are plumbing checks only.

```bash
python benchmarks/run.py --task benchmarks/tasks/shop-coupon-floor.json --repeat 3 -- \
  codex -a never -s workspace-write -c 'sandbox_workspace_write.writable_roots=[]' exec --json --skip-git-repo-check -
```

Reported separately in each row: preprocessing time (`analyze` + `compile_context`), agent time, test time, raw agent
usage objects as emitted by the agent's JSON output, test status/counts, files changed and graph nodes/edges changed.
No results table exists yet (P4.5): nothing in this directory is a measured outcome until real runs are recorded.
