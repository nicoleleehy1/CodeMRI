from codemri.analyzer import analyze
from codemri.changes import changes
from codemri.store import Store
from fastapi.testclient import TestClient
from services.api import main


def test_persistent_review_tracks_edits_removals_and_relationships(tmp_path):
    root=tmp_path/'repo'
    root.mkdir()
    source=root/'app.ts'
    source.write_text('export function first() { return 1; }\nexport function run() { return first(); }')
    before=analyze(root)
    store=Store(tmp_path/'cache')
    key=store.save(before)
    source.write_text('export function second() { return 2; }\nexport function run() { return second(); }')
    after=analyze(root)
    store.save(after)
    restarted=Store(tmp_path/'cache')
    review=restarted.review(key)['changes']
    assert {'added','removed','modified'} <= {n['status'] for n in review['nodes']}
    assert {'added','removed'} <= {e['status'] for e in review['edges']}
    assert restarted.load(key,baseline=True).revision==before.revision
    restarted.save(after)
    assert restarted.review(key)['changes']==review
    restarted.accept(key,after.revision)
    assert restarted.review(key)['changes']['nodes']==[]
    assert restarted.review(key)['changes']['edges']==[]


def test_line_movement_does_not_mark_unchanged_function(tmp_path):
    file=tmp_path/'app.ts'
    file.write_text('export function f() { return 1; }')
    before=analyze(tmp_path)
    file.write_text('\n\nexport function f() { return 1; }')
    after=analyze(tmp_path)
    assert not [n for n in changes(before,after)['nodes'] if n['name']=='f']


def test_review_rejects_stale_revision(tmp_path,monkeypatch):
    (tmp_path/'app.ts').write_text('export function f() {}')
    monkeypatch.setattr(main,'store',Store(tmp_path/'cache'))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT',str(tmp_path))
    client=TestClient(main.app)
    payload=client.post('/analyze',json={'root':str(tmp_path)}).json()
    assert 'baseline' in payload and 'changes' in payload
    route=f"/graphs/{payload['repo_id']}/review"
    assert client.post(route,json={'revision':'outdated'}).status_code==409
    assert client.post(route,json={'revision':payload['graph']['revision']}).status_code==200
