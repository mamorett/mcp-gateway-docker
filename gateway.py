import json, asyncio, os, logging, sys
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from mcp.server.sse import SseServerTransport
from mcp.server import Server
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# Setup logging immediato su stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("mcp-gateway")

print("🚀 Script avviato, controllo configurazione...")
CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "/etc/mcp/config.json")

class RobustMCPGateway:
    def __init__(self):
        self.server = Server("k8s-mcp-gateway")
        self.sessions = {}
        self.tool_map = {}
        self.running_tasks = []
        self.sse_transport = SseServerTransport("/messages")

    async def _manage_child_server(self, name, params):
        while True:
            try:
                logger.info(f"Connessione a: {name}")
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self.sessions[name] = session
                        
                        # Mappatura Tool
                        res = await session.list_tools()
                        for t in res.tools:
                            self.tool_map[t.name] = name
                        logger.info(f"✅ {name} pronto!")
                        
                        # LA MAGIA È QUI: blocchiamo il task all'infinito in modo pulito.
                        # Si sbloccherà da solo lanciando un'eccezione se il processo figlio muore.
                        await asyncio.Future()
                        
            except BaseExceptionGroup as eg:
                logger.error(f"❌ Errore TaskGroup {name}: {eg.exceptions}")
            except Exception as e:
                logger.error(f"❌ Errore {name}: {type(e).__name__} - {e}")
            finally:
                # Cleanup pulito
                self.sessions.pop(name, None)
                self.tool_map = {k: v for k, v in self.tool_map.items() if v != name}
                logger.info(f"🔄 Riavvio {name} tra 5 secondi...")
                await asyncio.sleep(5)

    async def startup(self):
        print(f"🔍 Caricamento config da {CONFIG_PATH}...")
        if not os.path.exists(CONFIG_PATH):
            print("❌ ERRORE: File config non trovato!")
            return
            
        with open(CONFIG_PATH) as f:
            data = json.load(f)
            config = data.get("mcpServers", {})

        for name, cfg in config.items():
            params = StdioServerParameters(
                command=cfg["command"],
                args=cfg["args"],
                env={**os.environ, **cfg.get("env", {})}
            )
            self.running_tasks.append(asyncio.create_task(self._manage_child_server(name, params)))

    def setup_handlers(self):
        @self.server.list_tools()
        async def list_tools():
            all_tools = []
            for s in list(self.sessions.values()):
                res = await s.list_tools()
                all_tools.extend(res.tools)
            return all_tools

        @self.server.call_tool()
        async def call_tool(name, arguments):
            s_name = self.tool_map.get(name)
            if not s_name or s_name not in self.sessions:
                raise Exception(f"Server {s_name} offline")
            return await self.sessions[s_name].call_tool(name, arguments)

    async def handle_sse(self, request):
        # Aggiunto il trattino basso a _send
        async with self.sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await self.server.run(streams[0], streams[1], self.server.create_initialization_options())

    async def handle_post(self, request):
        # Aggiunto il trattino basso a _send anche qui
        await self.sse_transport.handle_post_message(request.scope, request.receive, request._send)

gateway = RobustMCPGateway()
gateway.setup_handlers()

app = Starlette(
    routes=[
        Route("/sse", gateway.handle_sse),
        Route("/messages", gateway.handle_post, methods=["POST"]),
        Route("/health", lambda r: JSONResponse({"status": "ok"}))
    ],
    on_startup=[gateway.startup]
)

if __name__ == "__main__":
    print("📡 Avvio Uvicorn su porta 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)