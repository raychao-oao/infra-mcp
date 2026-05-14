# infra-mcp

**Infrastructure resource manager for AI agents** — allocate machines, ports, and names so your AI can deploy, not just code.

---

AI coding agents can write and test code. But when it's time to deploy, they hit a wall: which port is free? What's the hostname? How do I register a tunnel?

**infra-mcp** is a [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI agents a structured interface to infrastructure primitives: port allocation, DNS management, Cloudflare Tunnel registration, service deployment, and Git repo management — all via MCP tools callable from Claude, Cursor, or any MCP-compatible agent.

Think of it as the resource scheduler layer between your AI agent and your infrastructure.

## Tools

| Category | Tools |
|----------|-------|
| **Ports** | `allocate_port` `release_port` `check_listening_ports` |
| **Services** | `register_service` `deploy_service` `restart_service` `stop_service` `purge_service` `upgrade_service` `get_service_info` `get_service_logs` `check_service_health` `audit_all_services` `validate_service_security` `get_caddy_config` |
| **Tunnels** | `register_main_tunnel` `list_main_tunnels` `create_cloudflare_tunnel` `delete_cloudflare_tunnel` `list_cloudflare_tunnels` `get_tunnel_config` `get_tunnel_token` `list_public_hostnames` `add_public_hostname` `remove_public_hostname` |
| **DNS** | `create_dns_record` `update_dns_record` `delete_dns_record` `list_dns_records` |
| **Access** | `create_access_application` `delete_access_application` `list_access_applications` `list_access_policies` |
| **Git** | `create_gitea_repo` `list_gitea_repos` `get_gitea_repo` `delete_gitea_repo` |
| **Inventory** | `list_resources` |

## Quick Start

### Prerequisites

- Python 3.11+
- Cloudflare account (for DNS, Tunnels, Access tools)
- SSH access to managed VPS servers (for deployment tools)
- Gitea instance (optional, for Git tools)

### Installation

```bash
git clone https://github.com/raychao-oao/infra-mcp
cd infra-mcp

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your server names, Cloudflare tokens, and SSH credentials

python main/server.py
# Server starts at http://127.0.0.1:8000
```

### Connect to Claude

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "infrastructure": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

For remote deployment with authentication, see [Production Deployment](#production-deployment).

### Example: Let Claude allocate a port and deploy a service

```
You: Deploy my-app web service on the prod server

Claude: I'll allocate a port and deploy the service.
  → allocate_port(project="my-app", service="web", server="prod") → port 8432
  → deploy_service(project="my-app", service="web", server="prod", port=8432)
  → register_main_tunnel(...)
  Done. my-app is running at https://my-app.your-domain.com
```

## Security

> **Warning**: The `/mcp` endpoint executes SSH commands on your servers. Always protect it with authentication before exposing to any network.

**The server binds to `127.0.0.1` by default.** The recommended production pattern:

```
Internet → Cloudflare Access (auth) → Cloudflare Tunnel → localhost:8000/mcp
```

Any reverse proxy with authentication works: Cloudflare Access, nginx + auth, Tailscale, etc.

**Never expose `/mcp` without authentication.**

## Production Deployment

### Architecture

```
Internet
    ↓
Cloudflare Access  (identity-based auth)
    ↓
Cloudflare Tunnel  (infra-mcp)
    ↓
Caddy              (localhost:8001)
    ↓
FastAPI MCP Server (localhost:8000)
    ↓
SQLite Database
```

### Deploy

```bash
# 1. Configure deployment settings
# Edit deploy/deploy.sh (server, user, paths)

# 2. Deploy to server
./deploy/deploy.sh

# 3. Configure environment on server
ssh user@your-server
cd /home/user/infra-mcp
nano .env  # Add production credentials

# 4. Start services
sudo systemctl enable --now infra-mcp
sudo systemctl status infra-mcp
```

### Connect remotely with Service Token

```json
{
  "mcpServers": {
    "infrastructure": {
      "type": "http",
      "url": "https://infra.your-domain.com/mcp",
      "headers": {
        "CF-Access-Client-Id": "YOUR_CLIENT_ID",
        "CF-Access-Client-Secret": "YOUR_CLIENT_SECRET"
      }
    }
  }
}
```

### Management

```bash
sudo systemctl status infra-mcp
sudo systemctl restart infra-mcp
sudo journalctl -u infra-mcp -f
```

## Project Structure

```
infra-mcp/
├── main/
│   ├── server.py          # FastAPI + JSON-RPC 2.0 entry point
│   ├── config.py          # Environment variable loading
│   ├── utils.py           # Shared utilities
│   ├── tools/             # MCP tool implementations
│   │   ├── allocate_port.py
│   │   ├── deploy_service.py
│   │   ├── cloudflare/    # Cloudflare API tools (DNS, Tunnels, Access)
│   │   └── gitea/         # Gitea repo management
│   ├── models/            # SQLAlchemy data models
│   ├── db/                # Database access layer
│   └── providers/         # SSH / Cloudflare providers
├── configs/               # Runtime config (gitignored)
├── deploy/                # Deployment scripts and systemd units
├── examples/              # Client examples (Python SDK, setup scripts)
├── docs/                  # Architecture, API spec, data models
├── .env.example           # Environment variable template
└── requirements.txt
```

## Tech Stack

- **Python 3.11+** with FastAPI (HTTP, JSON-RPC 2.0)
- **SQLite + SQLAlchemy** (resource database)
- **asyncssh** (SSH command execution)
- **Cloudflare API** (DNS, Tunnels, Access)
- **systemd** (service management on VPS)

## Documentation

- [`docs/Architecture.md`](./docs/Architecture.md) — system design
- [`docs/MCP-API.md`](./docs/MCP-API.md) — full tool reference
- [`docs/Data-Models.md`](./docs/Data-Models.md) — resource data models
- [`docs/MCP-Client-Setup.md`](./docs/MCP-Client-Setup.md) — client configuration guide
- [`examples/`](./examples/) — Python client library and setup scripts

## License

MIT — see [LICENSE](./LICENSE)
