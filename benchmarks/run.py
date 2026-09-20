"""P4.4 benchmark harness: run one task with the baseline and the CodeMRI variant using the *same* agent command,
model, tools and timeouts, and append one raw results row per run.

    python benchmarks/run.py --task benchmarks/tasks/shop-coupon-floor.json --repeat 1 -- codex -a never -s workspace-write exec --skip-git-repo-check -

Rows land in benchmarks/results.jsonl; full artifacts (prompt, patch, test output, graph diff) under
benchmarks/runs/<timestamp>-<task>-<variant>-<n>/. Every record is `recorded: false` until a human labels a real run.
The CodeMRI variant only receives what the compiler produces for the task text; the harness never seeds it with the
known patch or hidden tests. Runs with a mock agent are plumbing checks, not results.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/engine'))
from codemri.loop import VARIANTS, run_loop  # noqa: E402


def git_revision(path: Path) -> str | None:
    try:
        return subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def load_task(path: Path) -> dict:
    task = json.loads(path.read_text())
    for key in ('id', 'repo', 'task'):
        if key not in task:
            raise ValueError(f'{path}: missing "{key}"')
    return task


def results_row(task: dict, record: dict, repeat_index: int, out: Path, agent: list[str] | None, git_rev: str | None) -> dict:
    o = record['outcome']
    usage = record['agent'].get('usage', [])
    tokens = {k: sum(u.get(k, 0) for u in usage if isinstance(u.get(k), (int, float))) for k in ('input_tokens', 'output_tokens', 'cached_input_tokens')}
    return {
        'task': task['id'], 'variant': record['variant'], 'repeat': repeat_index, 'recorded': record['recorded'],
        'agent_command': agent, 'agent_status': o['agent'], 'git_revision': git_rev, 'graph_revision': record['revision'],
        'tests': o['tests'], 'tests_passed': o['tests_passed'], 'tests_failed': o['tests_failed'],
        'files_changed': o['files_changed'], 'graph_nodes_changed': o['graph_nodes_changed'], 'graph_edges_changed': o['graph_edges_changed'],
        'context_tokens': o['prompt_tokens_context'], 'agent_usage_raw': usage, 'agent_tokens': tokens,
        'preprocessing_ms': record['timings_ms']['analyze'] + record['timings_ms']['impact'] + record['timings_ms']['compile_context'],
        'agent_ms': record['timings_ms']['agent'], 'tests_ms': record['timings_ms']['tests'], 'total_ms': record['timings_ms']['total'],
        'artifacts': str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out), 'started': record['started'],
    }


def run_task(task_path: Path, agent: list[str] | None, repeat: int = 1, variants=VARIANTS, results: Path | None = None,
             runs_dir: Path | None = None) -> list[dict]:
    task = load_task(task_path)
    repo = (ROOT / task['repo']).resolve() if not Path(task['repo']).is_absolute() else Path(task['repo'])
    results = results or ROOT / 'benchmarks/results.jsonl'
    runs_dir = runs_dir or ROOT / 'benchmarks/runs'
    git_rev = git_revision(repo)
    rows = []
    for n in range(1, repeat + 1):
        for variant in variants:
            stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
            out = runs_dir / f'{stamp}-{task["id"]}-{variant}-{n}'
            record = run_loop(repo, task['task'], agent, out, variant, task.get('budget', 4000), task.get('seed_ids'),
                              task.get('test_timeout', 300), task.get('agent_timeout', 1800))
            row = results_row(task, record, n, out, agent, git_rev)
            rows.append(row)
            results.parent.mkdir(parents=True, exist_ok=True)
            with results.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(row, sort_keys=True) + '\n')
            print(json.dumps({k: row[k] for k in ('task', 'variant', 'repeat', 'agent_status', 'tests', 'tests_passed', 'tests_failed', 'files_changed', 'total_ms')}))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], usage='%(prog)s --task TASK.json [--repeat N] -- AGENT_COMMAND...')
    parser.add_argument('--task', required=True, type=Path)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--variant', choices=VARIANTS, action='append', help='Restrict to one variant (default: both)')
    parser.add_argument('--results', type=Path)
    parser.add_argument('--runs-dir', type=Path)
    parser.add_argument('agent', nargs='*')
    args = parser.parse_args(argv)
    run_task(args.task, args.agent or None, args.repeat, tuple(args.variant or VARIANTS), args.results, args.runs_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
