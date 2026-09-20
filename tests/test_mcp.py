import asyncio
import json
import os
import sys
from pathlib import Path
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fastapi.testclient import TestClient
from codemri.roots import resolve_allowed
from codemri.store import Store
from services.api import main
from services.mcp import server

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / 'examples/shop'

def test_mcp_stdio_roundtrip(tmp_path):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m','services.mcp.server'],
            cwd=str(ROOT), env={**os.environ,'CODEMRI_CACHE':str(tmp_path),'CODEMRI_ALLOWED_ROOT':str(ROOT)})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert {'analyze_repository','get_architecture','compile_agent_context'} <= {t.name for t in tools.tools}
                analysis = await client.call_tool('analyze_repository', {'root':str(SHOP)})
                assert not analysis.isError
                repo_id = json.loads(analysis.content[0].text)['repo_id']
                context = await client.call_tool('compile_agent_context', {'repo_id':repo_id,'task':'applyCoupon','budget':1000})
                assert not context.isError
                assert json.loads(context.content[0].text)['tokens'] <= 1000
                assert 'applyCoupon' in json.loads(context.content[0].text)['text']
                missing = await client.call_tool('get_symbol', {'repo_id':repo_id,'symbol_id':'nope'})
                assert missing.isError and 'Unknown symbol ID' in missing.content[0].text
                outside = await client.call_tool('analyze_repository', {'root':'/'})
                assert outside.isError and 'CODEMRI_ALLOWED_ROOT' in outside.content[0].text
    asyncio.run(run())


def test_allowed_root_helper_is_shared_by_api_and_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(tmp_path))
    assert resolve_allowed(str(tmp_path / 'inner')) == (tmp_path / 'inner').resolve()
    with pytest.raises(PermissionError):
        resolve_allowed('/')
    assert main.allowed_or_403.__module__ == 'services.api.main'
    assert server.resolve_allowed is resolve_allowed and main.resolve_allowed is resolve_allowed


def test_compact_architecture_and_symbol_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'store', Store(tmp_path))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(ROOT))
    repo_id = server.analyze_repository(str(SHOP))['repo_id']
    compact = server.get_architecture(repo_id)
    full = server.get_architecture(repo_id, compact=False)
    assert len(compact['nodes']) == len(full['nodes']) and len(compact['edges']) == len(full['edges'])
    assert all('source' not in n and 'call_occurrences' not in n for n in compact['nodes'])
    assert all('call_sites' not in e for e in compact['edges'])
    assert any(n['source'] for n in full['nodes'])
    assert len(json.dumps(compact)) < len(json.dumps(full))
    symbol_id = next(n['id'] for n in compact['nodes'] if n['name'] == 'applyCoupon')
    assert server.get_symbol(repo_id, symbol_id)['source']
    with pytest.raises(ValueError, match='Unknown symbol ID'):
        server.get_symbol(repo_id, 'missing')
    assert 'Java' in server.analyze_repository.__doc__


def test_api_and_mcp_parity_on_the_same_cache(tmp_path, monkeypatch):
    """P0.5: analyze through the API, read the same snapshot through MCP tool functions."""
    store = Store(tmp_path)
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setattr(server, 'store', store)
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(ROOT))
    client = TestClient(main.app)
    api = client.post('/analyze', json={'root': str(SHOP)}).json()
    repo_id = api['repo_id']
    via_mcp = server.get_architecture(repo_id, compact=False)
    via_api = client.get(f'/graphs/{repo_id}').json()
    assert via_mcp == via_api == api['graph']
    query = {'query': 'change applyCoupon', 'budget': 1200}
    assert client.post(f'/graphs/{repo_id}/impact', json=query).json() == server.impact_analysis(repo_id, 'change applyCoupon')
    assert client.post(f'/graphs/{repo_id}/context', json=query).json() == server.compile_agent_context(repo_id, 'change applyCoupon', 1200)
    symbol_id = next(n['id'] for n in api['graph']['nodes'] if n['name'] == 'applyCoupon')
    callers = server.find_callers(repo_id, symbol_id)
    assert callers == [e['source'] for e in via_api['edges'] if e['kind'] == 'calls' and e['target'] == symbol_id]
