import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

def test_mcp_stdio_roundtrip(tmp_path):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m','services.mcp.server'],
            cwd=str(ROOT), env={**os.environ,'CODEMRI_CACHE':str(tmp_path),'CODEMRI_ALLOWED_ROOT':str(ROOT)})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert {'analyze_repository','get_architecture','compile_agent_context'} <= {t.name for t in tools.tools}
                analysis = await client.call_tool('analyze_repository', {'root':str(ROOT/'examples/shop')})
                assert not analysis.isError
                repo_id = json.loads(analysis.content[0].text)['repo_id']
                context = await client.call_tool('compile_agent_context', {'repo_id':repo_id,'task':'applyCoupon','budget':1000})
                assert not context.isError
                assert json.loads(context.content[0].text)['tokens'] <= 1000
                assert 'applyCoupon' in json.loads(context.content[0].text)['text']
    asyncio.run(run())
