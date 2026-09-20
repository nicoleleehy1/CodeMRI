import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
from retrieval_eval import evaluate  # noqa: E402


def test_labeled_tasks_score_and_skip_missing_fixtures(tmp_path):
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps({'tasks': [
        {'id': 'coupon', 'repo': 'examples/shop', 'task': 'applyCoupon must never return a negative total',
         'relevant': ['src/coupons.ts::applyCoupon', 'src/pricing.ts::calculatePrice']},
        {'id': 'gone', 'repo': 'examples/does-not-exist', 'task': 'x', 'relevant': ['a::b']},
    ]}))
    report = evaluate(labels, 2000)
    coupon, gone = report['tasks']
    assert gone['status'] == 'skipped'
    assert coupon['context']['recall'] == 1.0 and coupon['context']['missed'] == []
    assert 0 < coupon['context']['precision'] <= 1
    assert report['summary']['scored'] == 1 and report['summary']['skipped'] == 1


def test_cli_prints_summary(tmp_path):
    out = tmp_path / 'report.json'
    proc = subprocess.run([sys.executable, str(ROOT / 'benchmarks/retrieval_eval.py'), '--budget', '2000', '--json', str(out)],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert 'mean over' in proc.stdout
    assert json.loads(out.read_text())['summary']['scored'] >= 5
