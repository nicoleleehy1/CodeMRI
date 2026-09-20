"""P4.2 retrieval evaluation: score CodeMRI's context selection against hand-labeled tasks.

    python benchmarks/retrieval_eval.py [--labels benchmarks/retrieval/labels.json] [--budget 4000] [--json out.json]

For each labeled task the script analyzes the fixture, runs impact() and compile_context(), and reports which
labeled symbols were found (full source), found only as a signature, or missed, plus the unlabeled production
symbols that were included. Precision/recall are computed over non-test symbol nodes. Fixtures that are not
present (optional tasks) are skipped and reported as such; nothing here is a model or agent measurement.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/engine'))
from codemri.analyzer import analyze  # noqa: E402
from codemri.context import compile_context, impact  # noqa: E402


def is_test_path(path: str) -> bool:
    lowered = path.lower()
    return 'test' in lowered.split('/')[-1] or '/tests/' in f'/{lowered}' or '/test/' in f'/{lowered}'


def prf(found: set, relevant: set, retrieved: set) -> dict:
    precision = len(found) / len(retrieved) if retrieved else 0.0
    recall = len(found) / len(relevant) if relevant else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'precision': round(precision, 3), 'recall': round(recall, 3), 'f1': round(f1, 3)}


def evaluate_task(task: dict, budget: int) -> dict:
    repo = ROOT / task['repo']
    if not repo.exists():
        return {'id': task['id'], 'status': 'skipped', 'reason': f'{task["repo"]} not present'}
    graph = analyze(repo)
    key = {n.id: f'{n.path}::{n.name}' for n in graph.nodes if n.kind != 'module' and not is_test_path(n.path)}
    relevant = set(task['relevant'])
    unknown = sorted(relevant - set(key.values()))
    result = impact(graph, task['task'])
    context = compile_context(graph, task['task'], budget)
    seeds = {key[i] for i in result['affected'] if i in key}
    full = {key[i] for i in context['selected'] + context['covered'] if i in key}
    supporting = {key[i] for i in context['supporting'] if i in key}
    retrieved = full | supporting
    return {
        'id': task['id'], 'status': 'ok', 'repo': task['repo'], 'task': task['task'], 'budget': budget,
        'labels': sorted(relevant), 'unknown_labels': unknown,
        'impact': {**prf(seeds & relevant, relevant, seeds), 'retrieved': sorted(seeds)},
        'context': {
            **prf(retrieved & relevant, relevant, retrieved),
            'found_full': sorted(full & relevant), 'found_signature': sorted(supporting & relevant),
            'missed': sorted(relevant - retrieved), 'unlabeled_included': sorted(retrieved - relevant),
            'tokens': context['tokens'], 'shortfall': context['shortfall'],
        },
    }


def evaluate(labels_path: Path, budget: int) -> dict:
    labels = json.loads(labels_path.read_text())
    rows = [evaluate_task(t, budget) for t in labels['tasks']]
    scored = [r for r in rows if r['status'] == 'ok']
    def mean(section, metric):
        return round(sum(r[section][metric] for r in scored) / len(scored), 3) if scored else 0.0
    return {'labels': str(labels_path), 'budget': budget, 'tasks': rows,
            'summary': {'scored': len(scored), 'skipped': len(rows) - len(scored),
                        'impact': {m: mean('impact', m) for m in ('precision', 'recall', 'f1')},
                        'context': {m: mean('context', m) for m in ('precision', 'recall', 'f1')}}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--labels', default=str(ROOT / 'benchmarks/retrieval/labels.json'))
    parser.add_argument('--budget', type=int, default=4000)
    parser.add_argument('--json', help='write the full report here')
    args = parser.parse_args(argv)
    report = evaluate(Path(args.labels), args.budget)
    for row in report['tasks']:
        if row['status'] != 'ok':
            print(f"{row['id']}: skipped ({row['reason']})"); continue
        c = row['context']
        print(f"{row['id']}: impact P/R {row['impact']['precision']}/{row['impact']['recall']}  "
              f"context P/R {c['precision']}/{c['recall']}  missed={c['missed']} extra={c['unlabeled_included']}"
              + (f"  UNKNOWN LABELS={row['unknown_labels']}" if row['unknown_labels'] else ''))
    s = report['summary']
    print(f"mean over {s['scored']} tasks: impact P/R/F1 {s['impact']['precision']}/{s['impact']['recall']}/{s['impact']['f1']}  "
          f"context P/R/F1 {s['context']['precision']}/{s['context']['recall']}/{s['context']['f1']}  (skipped {s['skipped']})")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
