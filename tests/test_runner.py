"""P3.4: isolated test runner with structured, stored results."""
from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
from codemri.analyzer import analyze
from codemri.context import impact
from codemri.runner import run_tests, merge_junit, parse_commands, summarize, aggregate_status, Command
from codemri.store import Store
from services.api import main

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / 'examples/shop'
HAS_TSX = (SHOP / 'node_modules/.bin/tsx').exists()


def test_refuses_unknown_tools_and_dedupes():
    with pytest.raises(ValueError):
        parse_commands([{'tool': 'bash', 'args': ['-c', 'echo hi']}])
    cmds = parse_commands([{'selector': {'tool': 'node', 'args': ['--test', 'a.js']}}, {'tool': 'node', 'args': ['--test', 'a.js']}])
    assert len(cmds) == 1


def test_junit_selectors_fold_into_one_maven_run():
    cmds = merge_junit([Command('mvn', ['-q', '-Dtest=T#a', 'test']), Command('mvn', ['-q', '-Dtest=T#b', 'test']), Command('node', ['--test', 'x.js'])])
    assert [c.tool for c in cmds] == ['mvn', 'node'] and '-Dtest=T#a,T#b' in cmds[0].args


def test_output_summaries():
    assert summarize('mvn', 'Tests run: 5, Failures: 1, Errors: 0, Skipped: 1', '')['failed'] == 1
    assert summarize('node', '# pass 3\n# fail 0\n# skipped 0\n', '') == {'passed': 3, 'failed': 0, 'skipped': 0, 'no_tests_ran': False}
    assert summarize('pytest', '2 failed, 7 passed in 0.3s', '')['failed'] == 2
    assert summarize('node', '# tests 0\n# pass 0\n', '')['no_tests_ran']


def test_runner_reports_failure_faithfully_and_leaves_checkout_untouched(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'math.js').write_text('module.exports = { add: (a, b) => a + b };\n')
    (repo / 'math.test.js').write_text("const test = require('node:test'); const assert = require('node:assert');\nconst { add } = require('./math');\ntest('adds', () => assert.strictEqual(add(1, 2), 3));\n")
    before = {p: p.read_text() for p in repo.rglob('*') if p.is_file()}
    selection = [{'name': 'math.test.js', 'path': 'math.test.js', 'selector': {'tool': 'node', 'args': ['--test', 'math.test.js']}}]
    ok = run_tests(repo, selection, timeout=60)
    assert ok['status'] == 'passed' and ok['totals'] == {'passed': 1, 'failed': 0, 'skipped': 0}
    assert ok['runs'][0]['cwd'] != str(repo) and not Path(ok['runs'][0]['cwd']).exists()
    broken = run_tests(repo, selection, files=[{'path': 'math.js', 'after': 'module.exports = { add: (a, b) => a - b };\n'}], timeout=60)
    assert broken['status'] == 'failed' and broken['applied_files'] == ['math.js']
    assert broken['runs'][0]['exit_code'] != 0 and 'adds' in broken['runs'][0]['stdout']
    assert {p: p.read_text() for p in repo.rglob('*') if p.is_file()} == before
    assert run_tests(repo, [], timeout=60)['status'] == 'no_tests'


def test_timeout_is_reported(tmp_path):
    (tmp_path / 'slow.js').write_text('setTimeout(() => {}, 60000);\n')
    result = run_tests(tmp_path, [{'tool': 'node', 'args': ['slow.js']}], timeout=5)
    assert result['status'] == 'timeout' and result['runs'][0]['status'] == 'timeout' and 'Timed out' in result['runs'][0]['stderr']


@pytest.mark.skipif(not HAS_TSX, reason='run npm install in examples/shop first')
def test_api_runs_impacted_shop_tests_and_stores_results(tmp_path, monkeypatch):
    work = tmp_path / 'shop'
    shutil.copytree(SHOP, work, symlinks=True)
    store = Store(tmp_path / 'cache')
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(tmp_path))
    client = TestClient(main.app)
    repo_id = client.post('/analyze', json={'root': str(work)}).json()['repo_id']
    run = client.post(f'/graphs/{repo_id}/tests/run', json={'query': 'change applyCoupon', 'timeout': 120}).json()
    assert run['status'] == 'passed', run
    assert sorted(s['path'] for s in run['selection']) == ['tests/checkout.test.ts', 'tests/pricing.test.ts']
    assert run['totals']['passed'] == 4
    broken = client.post(f'/graphs/{repo_id}/tests/run', json={'query': 'change applyCoupon', 'timeout': 120,
        'files': [{'path': 'src/coupons.ts', 'before': None, 'after': 'export function applyCoupon(total: number, discount: number): number {\n  return total - discount;\n}\n'}]}).json()
    assert broken['status'] == 'failed' and broken['totals']['failed'] >= 1
    assert (work / 'src/coupons.ts').read_text().startswith('export function applyCoupon(total: number, discount: number): number {\n  return Math.max')
    assert broken['freshness']['matches'] is True
    (work / 'src/analytics.ts').write_text((work / 'src/analytics.ts').read_text() + '\n// edited after analysis\n')
    stale = client.post(f'/graphs/{repo_id}/tests/run', json={'query': 'change trackPage', 'timeout': 120}).json()
    assert stale['freshness']['matches'] is False and 'stale' in stale['note']
    runs = client.get(f'/graphs/{repo_id}/tests/runs').json()
    assert [r['status'] for r in runs] == ['passed', 'failed', 'passed'] and runs[0]['revision'] == run['revision']
    assert client.post(f'/graphs/{repo_id}/tests/run', json={'selection': [{'tool': 'sh', 'args': ['-c', 'true']}]}).status_code == 400


def test_aggregate_status_precedence():
    assert aggregate_status(['passed', 'no_tests']) == 'passed'
    assert aggregate_status(['no_tests', 'no_tests']) == 'no_tests'
    assert aggregate_status(['passed', 'error']) == 'error'
    assert aggregate_status(['failed', 'timeout', 'passed']) == 'timeout'
    assert aggregate_status(['failed', 'passed']) == 'failed'
    assert aggregate_status([]) == 'no_tests'


def test_api_only_runs_selectors_codemri_derived(tmp_path, monkeypatch):
    (tmp_path / 'repo').mkdir()
    (tmp_path / 'repo/math.js').write_text('module.exports = { add: (a, b) => a + b };\n')
    (tmp_path / 'repo/math.test.js').write_text("const test = require('node:test'); const assert = require('node:assert');\nconst { add } = require('./math');\ntest('add', () => assert.equal(add(1, 2), 3));\n")
    monkeypatch.setattr(main, 'store', Store(tmp_path / 'cache'))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(tmp_path))
    client = TestClient(main.app)
    repo_id = client.post('/analyze', json={'root': str(tmp_path / 'repo')}).json()['repo_id']
    evil = client.post(f'/graphs/{repo_id}/tests/run', json={'selection': [{'tool': 'node', 'args': ['-e', 'process.exit(0)']}]})
    assert evil.status_code == 400 and 'Unknown test selector' in evil.text
    ok = client.post(f'/graphs/{repo_id}/tests/run', json={'selection': [{'tool': 'node', 'args': ['--test', 'math.test.js']}], 'timeout': 60}).json()
    assert ok['status'] == 'passed' and ok['selection'][0]['path'] == 'math.test.js'
