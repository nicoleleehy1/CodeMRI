from fastapi.testclient import TestClient
from services.api import main
from codemri.store import Store
from codemri.proposals import line_diff


def test_preview_does_not_write_working_files_or_persistent_graph(tmp_path, monkeypatch):
    root=tmp_path/'repo'
    root.mkdir()
    original='export function old() { return 1; }\n'
    (root/'app.ts').write_text(original)
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT',str(root))
    monkeypatch.setattr(main,'store',Store(tmp_path/'cache'))
    client=TestClient(main.app)
    snapshot=client.post('/analyze',json={'root':str(root)}).json()
    payload={'root':str(root),'files':[{'path':'app.ts','before':original,'after':'export function next() { return 2; }\n'},
                                    {'path':'new.ts','before':None,'after':'export const added = 3;\n'}]}
    response=client.post('/preview',json=payload)
    assert response.status_code==200, response.text
    body=response.json()
    assert body['graph']['root']==str(root)
    assert 'next' in {n['name'] for n in body['graph']['nodes']}
    assert (root/'app.ts').read_text()==original
    assert not (root/'new.ts').exists()
    assert main.store.load(snapshot['repo_id']).revision==snapshot['graph']['revision']
    assert {'removed','added'} <= {line['kind'] for line in body['files'][0]['lines']}
    payload['files'][0]['path']='../escape.ts'
    assert client.post('/preview',json=payload).status_code==400
    payload['root']='/'
    assert client.post('/preview',json=payload).status_code==403


def test_line_diff_preserves_line_numbers_and_literal_markup():
    lines=line_diff('keep\nold\n','keep\n<script>new</script>\n')
    removed=next(line for line in lines if line['kind']=='removed')
    added=next(line for line in lines if line['kind']=='added')
    assert removed['old']==2 and removed['new'] is None
    assert added['new']==2 and added['old'] is None
    assert added['text']=='<script>new</script>'
    assert line_diff(None,'')[0]['kind']=='hunk'
