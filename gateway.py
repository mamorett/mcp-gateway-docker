import json, asyncio, os, logging, sys
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from mcp.server.sse import SseServerTransport
from mcp.server import Server
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from mcp.types import Tool

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("mcp-gateway")

CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "/etc/mcp/config.json")

class RobustMCPGateway:
    def __init__(self):
        self.server = Server("k8s-mcp-gateway")
        self.sessions = {}
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
                        logger.info(f"✅ {name} pronto!")
                        
                        # Il processo resta in vita finché non crasha
                        await asyncio.Future()
            except BaseExceptionGroup as eg:
                logger.error(f"❌ Errore TaskGroup {name}: {eg.exceptions}")
            except Exception as e:
                logger.error(f"❌ Errore {name}: {type(e).__name__} - {e}")
            finally:
                self.sessions.pop(name, None)
                logger.info(f"🔄 Riavvio {name} tra 5 secondi...")
                await asyncio.sleep(5)

    async def startup(self):
        if not os.path.exists(CONFIG_PATH):
            print("❌ ERRORE: File config non trovato!")
            return
            
        with open(CONFIG_PATH) as f:
            config = json.load(f).get("mcpServers", {})

        for name, cfg in config.items():
            params = StdioServerParameters(
                command=cfg["command"],
                args=cfg.get("args", []),
                env={**os.environ, **cfg.get("env", {})}
            )
            self.running_tasks.append(asyncio.create_task(self._manage_child_server(name, params)))

    def setup_handlers(self):
        @self.server.list_tools()
        async def list_tools():
            """Recupera i tool e aggiunge il prefisso del server per evitare collisioni."""
            all_tools = []
            for server_name, session in list(self.sessions.items()):
                try:
                    res = await session.list_tools()
                    for t in res.tools:
                        # Prefisso univoco: "nomeserver__nometool"
                        prefixed_name = f"{server_name}__{t.name}"
                        
                        # Creiamo un nuovo oggetto Tool modificato
                        new_tool = Tool(
                            name=prefixed_name,
                            description=f"[{server_name}] {t.description}",
                            inputSchema=t.inputSchema
                        )
                        all_tools.append(new_tool)
                except Exception as e:
                    logger.error(f"Errore caricamento tool da {server_name}: {e}")
            return all_tools

        @self.server.call_tool()
        async def call_tool(name, arguments):
            """Analizza il prefisso, trova il server e inoltra il nome originale."""
            if "__" not in name:
                raise Exception(f"Formato tool non valido. Atteso prefisso: {name}")

            # Dividiamo il nome in due parti: "otc-cloudeye" e "get_status"
            server_name, original_tool_name = name.split("__", 1)

            if server_name not in self.sessions:
                raise Exception(f"Server {server_name} attualmente offline")

            # Chiamiamo il server figlio usando il NOME ORIGINALE del tool
            logger.info(f"📲 Routing: {server_name} -> {original_tool_name}")
            return await self.sessions[server_name].call_tool(original_tool_name, arguments)

    async def handle_sse(self, request):
        async with self.sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await self.server.run(streams[0], streams[1], self.server.create_initialization_options())

    async def handle_post(self, request):
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