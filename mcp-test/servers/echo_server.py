import asyncio
from mcp.server.stdio import stdio_server
from mcp.server import Server
s = Server("local-echo")
@s.list_tools()
async def lt(): return [{"name": "echo", "description": "test", "inputSchema": {"type":"object"}}]
async def main():
    async with stdio_server() as (r, w): await s.run(r, w, s.create_initialization_options())
if __name__ == "__main__": asyncio.run(main())
