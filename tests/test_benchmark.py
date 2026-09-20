"""P4.4: one task runs both variants with the same fake agent and yields a results row per run."""
from pathlib import Path
import json
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
import run as bench  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HAS_TSX = (ROOT / 'examples/shop/node_modules/.bin/tsx').exists()

FAKE_AGENT = '''
import sys, pathlib
sys.stdin.read()
p = pathlib.Path('src/coupons.ts')
p.write_text(p.read_text() + '\\nexport const COUPON_FLOOR = 0;\\n')
'''


@pytest.mark.skipif(not HAS_TSX, reason='run npm install in examples/shop first')
def test_task_runs_both_variants_and_writes_rows(tmp_path):
    agent = tmp_path / 'agent.py'
    agent.write_text(FAKE_AGENT)
    results, runs = tmp_path / 'results.jsonl', tmp_path / 'runs'
    rows = bench.run_task(ROOT / 'benchmarks/tasks/shop-coupon-floor.json', [sys.executable, str(agent)], 1, results=results, runs_dir=runs)
    assert [r['variant'] for r in rows] == ['codemri', 'baseline']
    assert all(r['agent_command'] == [sys.executable, str(agent)] and r['recorded'] is False for r in rows)
    assert rows[0]['context_tokens'] > 0 and rows[1]['context_tokens'] == 0
    assert all(r['tests'] == 'passed' and r['files_changed'] == 1 for r in rows), rows
    lines = [json.loads(l) for l in results.read_text().splitlines()]
    assert len(lines) == 2 and {l['variant'] for l in lines} == {'codemri', 'baseline'}
    assert all((runs / Path(l['artifacts']).name / 'run.json').exists() for l in lines)
    assert all('preprocessing_ms' in l and 'agent_usage_raw' in l for l in lines)
    codemri_prompt = (runs / Path(lines[0]['artifacts']).name / 'prompt.txt').read_text()
    assert 'Math.max(0, total - discount)' in codemri_prompt, 'pack should surface the current applyCoupon source, not a solution'
    assert 'COUPON_FLOOR' not in codemri_prompt
