# Infrastructure MCP Server - Quick Start Guide

**Goal**: Get the Infrastructure MCP Server running and test your first tool in 5 minutes

---

## 🚀 Quick Start (Local Development)

### 1. Environment Setup (2 minutes)

```bash
# Clone the repo (if you haven't already)
cd ~/PROJECTS
git clone https://github.com/raychao-oao/infra-mcp infra-mcp
cd infra-mcp

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env if you need to use the Cloudflare API
```

### 2. Start the MCP Server (1 minute)

```bash
# Start the server
python main/server.py

# You should see:
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 3. Test Your First Tool (2 minutes)

**Run in another terminal** (all operations go through the `/mcp` endpoint in JSON-RPC 2.0 format):

```bash
# 1. List all available tools
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools | length'
# Expected output: 38

# 2. List all tool names
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq -r '.result.tools[].name' | head -5
# Expected output: allocate_port, release_port, list_resources, ...

# 3. Test list_resources tool
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_resources","arguments":{"resource_type":"all"}}}' | jq

# 4. Test allocate_port
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"allocate_port","arguments":{"project":"test","service":"demo","server":"prod"}}}' | jq
```

---

## 🎯 Common Tasks

### View Allocated Ports

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_resources","arguments":{"resource_type":"ports"}}}' | jq
```

### Check Server Security Status

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"audit_all_services","arguments":{"server":"prod"}}}' | jq
```

### List All Registered Main Tunnels

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_main_tunnels","arguments":{}}}' | jq
```

### View Service Info

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_service_info","arguments":{"project":"my-app","service":"web","server":"prod"}}}' | jq
```

---

## 🔧 Using MCP Tools via Claude Code

### Claude Desktop Setup

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

For a remote/production server protected by Cloudflare Access:

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

Restart Claude Desktop to load the new server.

### Using in Claude Code

Add the same config to `.claude/settings.json` in your project, or use the global `~/.claude/settings.json`. Then ask directly in the conversation:
- "Allocate a port on prod for test-api"
- "Check the security status of prod"
- "List all deployed services"

---

## 📊 38 MCP Tools by Category

### 1. Port Management (3)
- allocate_port, release_port, check_listening_ports

### 2. Service Management (12)
- register_service, deploy_service, stop_service, purge_service, upgrade_service, get_service_info
- get_service_logs, check_service_health, restart_service, get_caddy_config
- validate_service_security, audit_all_services

### 3. Tunnel Registry (3)
- register_main_tunnel, list_main_tunnels, get_tunnel_config

### 4. Cloudflare Tunnel API (7)
- create_cloudflare_tunnel, delete_cloudflare_tunnel, list_cloudflare_tunnels, get_tunnel_token
- list_public_hostnames, add_public_hostname, remove_public_hostname

### 5. DNS Management (4)
- create_dns_record, update_dns_record, delete_dns_record, list_dns_records

### 6. Cloudflare Access (4)
- create_access_application, delete_access_application, list_access_applications, list_access_policies

### 7. Gitea (4)
- create_gitea_repo, list_gitea_repos, get_gitea_repo, delete_gitea_repo

### 8. Inventory (1)
- list_resources

See [`docs/MCP-API.md`](docs/MCP-API.md) for full API documentation.

---

## 🐛 Troubleshooting

### Port 8000 Already in Use

```bash
# Find the process using port 8000
lsof -i :8000

# Kill that process
kill -9 <PID>
```

### Virtual Environment Not Found

```bash
# Recreate it
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### SQLite Database Permission Error

```bash
# Ensure the database file has correct permissions
chmod 644 configs/resources.db
```

---

## 📚 Next Steps

**Learn more**:
- See [`docs/MCP-API.md`](docs/MCP-API.md) for all tool API specifications
- See [`docs/Architecture.md`](docs/Architecture.md) for system architecture

**Production deployment**:
- SSH to prod: `ssh prod`
- Check production status: `systemctl status infra-mcp`

---

**Last updated**: 2026-05-16
**Version**: Infrastructure Management MCP v1.0.0
