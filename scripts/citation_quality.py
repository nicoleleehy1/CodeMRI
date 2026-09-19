"""Report how many of the model's citations survived verification in the last AI run.

Usage: python scripts/citation_quality.py [path/to/ai-last-run.json]   (default: .codemri/ai-last-run.json)

Reads only the local run log written by Generate AI architecture; it never touches the API key.
Citations that survive were located by their quoted text on an acceptable line (not blank, comment,
brace-only, or an import cited for a non-import relationship). That shows the cited line exists and
contains the quote, not that the line proves the claim; spot-check a sample by hand.
"""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else '.codemri/ai-last-run.json')
log = json.loads(path.read_text())
last = log['attempts'][-1]
if 'accepted_edges' not in last:
    sys.exit(f'{path}: last attempt was not accepted (or predates citation verification). Issues: {last.get("issues")}')

raw = json.loads(last['raw'])
raw_edges = raw['edges']
raw_citations = sum(len(e['evidence']) for e in raw_edges)
kept_edges = last['accepted_edges']
kept_citations = sum(len(e['evidence']) for e in kept_edges)
moved = sum(r.startswith('Moved citation') for r in last['repairs'])
dropped_edges = sum(r.startswith('Dropped edge') for r in last['repairs'])

print(f"model {log['model']}, {log['files']} files sent, {len(log['attempts'])} attempt(s)")
print(f"edges:     {len(raw_edges)} proposed -> {len(kept_edges)} kept ({dropped_edges} dropped)")
print(f"citations: {raw_citations} proposed -> {kept_citations} kept")
if raw_citations:
    print(f"  right as given: {raw_citations - moved - (raw_citations - kept_citations)}  moved to the quoted line: {moved}  dropped: {raw_citations - kept_citations}")
for repair in last['repairs']:
    print('  -', repair)
