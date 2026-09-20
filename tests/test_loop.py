"""P3.5 plumbing: the loop harness with a fake agent records prompt, patch, tests, graph diff and timings."""
from pathlib import Path
import json
import shutil
import sys
import subprocess
import pytest
from codemri.analyzer import analyze
from codemri.loop import build_prompt, collect_usage, run_loop, main

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / 'examples/shop'
HAS_TSX = (SHOP / 'node_modules/.bin/tsx').exists()

FAKE_AGENT = r'''
import sys, pathlib, json
prompt = sys.stdin.read()
p = pathlib.Path('src/coupons.ts')
p.write_text(p.read_text().replace('Math.max(0, total - discount)', 'total - discount'))
pathlib.Path('AGENT_SAW_CONTEXT').write_text(str('Relevant context compiled by CodeMRI' in prompt))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3}}))
'''


def test_prompt_variants_share_task_and_only_codemri_gets_context():
    pack = {'text': 'CONTEXT PACK'}
    assert 'CONTEXT PACK' in build_prompt('do it', 'codemri', pack)
    assert 'CONTEXT PACK' not in build_prompt('do it', 'baseline', pack)
    assert collect_usage('{"usage": {"a": 1}}\nnot json\n{"item": {"usage": {"b": 2}}}') == [{'a': 1}, {'b': 2}]


@pytest.mark.skipif(not HAS_TSX, reason='run npm install in examples/shop first')
def test_fake_agent_loop_records_everything_and_leaves_checkout_alone(tmp_path):
    work = tmp_path / 'shop'
    shutil.copytree(SHOP, work, symlinks=True)
    before = {p: p.read_bytes() for p in work.rglob('*') if p.is_file() and 'node_modules' not in p.parts}
    agent_script = tmp_path / 'agent.py'
    agent_script.write_text(FAKE_AGENT)
    out = tmp_path / 'run'
    record = run_loop(work, 'Change applyCoupon to allow negative totals', [sys.executable, str(agent_script)], out,
                      test_timeout=120, agent_timeout=60)
    assert record['recorded'] is False and record['variant'] == 'codemri'
    assert record['agent']['status'] == 'completed' and record['agent']['usage'] == [{'input_tokens': 12, 'output_tokens': 3}]
    assert sorted(record['patch']['changed_paths']) == ['AGENT_SAW_CONTEXT', 'src/coupons.ts']
    assert '-  return Math.max(0, total - discount);' in record['patch']['diff']
    assert record['tests']['status'] == 'failed', 'the fake patch breaks pricing tests; that must be reported'
    assert record['tests']['totals']['failed'] >= 1
    assert record['graph_diff']['revision'] != record['revision']
    assert set(record['timings_ms']) >= {'analyze', 'compile_context', 'copy', 'agent', 'diff', 'tests', 'reanalyze', 'total'}
    assert {p: p.read_bytes() for p in work.rglob('*') if p.is_file() and 'node_modules' not in p.parts} == before
    assert json.loads((out / 'run.json').read_text())['outcome']['tests'] == 'failed'
    assert (out / 'prompt.txt').read_text().startswith('Work only in the current directory')
    assert (out / 'patch.diff').read_text() and (out / 'tests.json').exists() and (out / 'graph-diff.json').exists()
    baseline = run_loop(work, 'Change applyCoupon to allow negative totals', [sys.executable, str(agent_script)], None,
                        variant='baseline', test_timeout=120, agent_timeout=60)
    assert baseline['context']['included_in_prompt'] is False
    assert 'compiled by CodeMRI' not in baseline['prompt'] and baseline['tests']['status'] == 'failed'


def test_cli_without_agent_reports_unchanged_copy(tmp_path, capsys):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n')
    code = main(['--root', str(tmp_path), '--task', 'touch f', '--out', str(tmp_path / 'out')])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['tests'] == 'no_tests' and summary['files_changed'] == 0
    record = json.loads((tmp_path / 'out/run.json').read_text())
    assert record['agent']['status'] == 'skipped' and record['graph_diff']['nodes'] == []


def test_baseline_skips_context_compilation_and_copy_keeps_tracked_ignored_files(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'generated').mkdir()
    (repo / 'generated/client.ts').write_text('export function client() { return 1; }\n')
    (repo / 'app.ts').write_text("import { client } from './generated/client';\nexport function run() { return client(); }\n")
    (repo / '.gitignore').write_text('generated/\n')
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'add', '-f', '.'], check=True)
    baseline = run_loop(repo, 'change run', None, None, variant='baseline', test_timeout=30)
    assert baseline['context']['included_in_prompt'] is False and baseline['context']['tokens'] == 0
    assert baseline['timings_ms']['compile_context'] < baseline['timings_ms']['analyze'] + 50
    assert 'generated/client.ts' in {n.path for n in analyze(repo).nodes}
    assert baseline['graph_diff']['nodes'] == [], 'a .git-less copy must not drop tracked files that match .gitignore'
    calls = []
    import codemri.loop as loop_module
    monkeypatch.setattr(loop_module, 'compile_context', lambda *a, **k: calls.append(a) or {'text': '', 'selected': [], 'excluded': [], 'tokens': 0, 'budget': 1, 'tokenizer': 'x', 'repository_tokens': 0})
    run_loop(repo, 'change run', None, None, variant='baseline', test_timeout=30)
    assert calls == []
