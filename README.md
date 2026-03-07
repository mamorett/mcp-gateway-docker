# MCP Gateway Docker

A robust, containerized gateway for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). This project multiplexes multiple MCP servers (stdio-based) into a single, unified SSE (Server-Sent Events) endpoint, making it easy to expose various tools to LLMs and MCP clients.

## Features

- **Multi-Server Aggregation**: Connect multiple MCP servers defined in a single configuration file.
- **Auto-Reconnection**: Automatically monitors and restarts child processes if they crash or exit.
- **SSE Transport**: Exposes the unified server interface via HTTP SSE, compatible with modern MCP clients.
- **Containerized**: Includes a Dockerfile with Python 3.12 and Node.js 20, supporting both Python and Node-based MCP servers out of the box.
- **Health Monitoring**: Simple `/health` endpoint for orchestration (e.g., Kubernetes liveness probes).

## Architecture

The gateway acts as an MCP client to several "child" servers (via standard input/output) and simultaneously acts as an MCP server to external clients (via SSE).

```
[ Client ] <--- SSE / HTTP ---> [ MCP Gateway ] <--- stdio ---> [ MCP Server A ]
                                                <--- stdio ---> [ MCP Server B ]
```

## Configuration

The gateway is configured via a JSON file. By default, it looks for the config at `/etc/mcp/config.json`, but this can be overridden with the `MCP_CONFIG_PATH` environment variable.

### Example `config.json`

```json
{
  "mcpServers": {
    "everything": {
      "command": "npx",
      "args": [
        "-y",
        "--quiet",
        "@modelcontextprotocol/server-everything"
      ]
    },
    "custom-python-server": {
      "command": "python3",
      "args": [
        "/app/servers/my_server.py"
      ],
      "env": {
        "MY_API_KEY": "secret-value"
      }
    }
  }
}
```

## Quick Start

### 1. Build the Image

```bash
docker build -t mcp-gateway .
```

### 2. Run the Container

Mount your configuration file and any necessary server scripts:

```bash
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/config.json:/etc/mcp/config.json \
  -v $(pwd)/servers:/app/servers \
  --name mcp-gateway \
  mcp-gateway
```

## API Endpoints

- **`GET /sse`**: The SSE entry point. Connect your MCP client here.
- **`POST /messages`**: Endpoint for sending messages to the server (part of the SSE transport).
- **`GET /health`**: Returns `{"status": "ok"}`.

## Development

The gateway is built with:
- **Python 3.12**
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)**
- **Starlette** (ASGI Framework)
- **Uvicorn** (ASGI Server)

### Local Setup

1. Install dependencies using `uv` or `pip`:
   ```bash
   pip install mcp starlette uvicorn
   ```
2. Run the gateway:
   ```bash
   export MCP_CONFIG_PATH=./mcp-test/config/config.json
   python gateway.py
   ```

## License

MIT
