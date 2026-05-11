# Infrastructure Management MCP

Centralized infrastructure resource management with MCP (Model Context Protocol) server for scalable allocation of VPS servers, Cloudflare Tunnels, ports, and domains across your projects.

---

## 📋 專案資訊

- **專案類型**: Infrastructure as Code / MCP Server
- **開發狀態**: Active
- **版本**: v1.0.0
- **最後更新**: 2026-05-11

## 🌐 管理的基礎設施

### VPS Servers
- **prod.your-domain.com** - Production (your VPS provider)
- [Future servers...]

### Cloudflare Services
- **Domains**: your-domain.com
- **Tunnels**: app, sandbox [+ future tunnels]
- **Services**: DNS, CDN, Access, Pages, Workers, R2

### Resource Allocation
- **Port Pool**: 3000-9999 (managed centrally)
- **Tunnel Registry**: Active tunnel configurations
- **Domain Mapping**: Subdomain to service mapping

## 🚀 快速開始

### Prerequisites

- Python 3.11+ (for MCP server)
- Node.js 18+ (for Claude Desktop integration)
- Access to Cloudflare account
- SSH access to managed VPS servers

### Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd infra-mcp

# 2. Install Python dependencies
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env with your server names, Cloudflare tokens, and SSH credentials

# 4. Start MCP server (development)
python main/server.py
# Server starts at http://127.0.0.1:8000
```

### Using MCP Tools in Projects

```bash
# All tools are called via the /mcp endpoint (JSON-RPC 2.0)

# Allocate a port for your service
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"allocate_port","arguments":{"project":"my-app","service":"web","server":"prod"}}}'

# Register a Cloudflare Tunnel
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"register_main_tunnel","arguments":{"vps_server":"prod","tunnel_name":"my-app","cloudflare_tunnel_id":"<tunnel-id>"}}}'

# Deploy a service
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"deploy_service","arguments":{"project":"my-app","service":"web","server":"prod"}}}'
```

## 🔒 Security

> **Warning**: The `/mcp` endpoint executes SSH commands on your servers. It **must** be protected by authentication before exposure to any network.

**The server binds to `127.0.0.1` by default** — it should not be directly reachable from the internet. The recommended deployment pattern is:

```
Internet → Cloudflare Access (auth) → Cloudflare Tunnel → localhost:8000/mcp
```

Any reverse proxy with authentication works: Cloudflare Access, nginx + auth, Tailscale, etc.

**Never expose `/mcp` without authentication.**

---

## 🚢 Production Deployment

### Current Deployment

**Server**: your-server (SSH alias configured in `~/.ssh/config`)
**Endpoint**: https://infra.your-domain.com (behind Cloudflare Access)
**Status**: Deploy to your own infrastructure using the setup in `deploy/`

**Architecture**:
```
Internet
    ↓
Cloudflare Access (Access Policy)
    ↓
Cloudflare Tunnel (infra-mcp)
    ↓
Caddy (localhost:8001)
    ↓
FastAPI MCP Server (localhost:8000)
    ↓
SQLite Database
```

**Services Running**:
- `infra-mcp.service` - FastAPI MCP Server (port 8000)
- `cloudflared-infra-mcp.service` - Cloudflare Tunnel
- `caddy.service` - Reverse proxy (port 8001)

### Deploy to Production

```bash
# 1. Configure deployment settings
# Edit deploy/deploy.sh if needed (server, user, paths)

# 2. Run deployment script
./deploy/deploy.sh

# 3. SSH to server and configure environment
ssh YOUR_USER@prod.your-domain.com
cd /home/YOUR_USER/infra-mcp
nano .env  # Add production credentials

# 4. Start services
sudo systemctl enable --now infra-mcp
sudo systemctl status infra-mcp

# 5. Setup Cloudflare Tunnel (if not exists)
# Use vps-tunnel-management skill for tunnel operations
# Service: cloudflared-infra-mcp
# Config: ~/.cloudflared/config-infra-mcp.yml

# 6. Configure Cloudflare Access
# Access is configured via API to use a reusable policy
# Policy allows: your@email.com

# 7. Verify deployment
curl -I https://infra.your-domain.com
# Should return HTTP 302 (redirect to Cloudflare Access login)
```

### Access the MCP Server

**Prerequisites**:
- Authenticated with Cloudflare Access (allowed email: your@email.com)
- Valid session cookie or Service Token

**Test Endpoints**:
```bash
# Health check
curl https://infra.your-domain.com/health

# MCP endpoint (requires authentication)
curl -X POST https://infra.your-domain.com/mcp \
  -H "Content-Type: application/json" \
  -H "CF-Access-Client-Id: YOUR_CLIENT_ID" \
  -H "CF-Access-Client-Secret: YOUR_CLIENT_SECRET" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_resources",
      "arguments": {}
    }
  }'
```

## 📱 客戶端使用

### 快速開始 - 在新專案中使用

**前置要求：Service Token 認證**

認證憑證已配置在 `~/.zshrc`，新終端機視窗會自動載入。如當前終端機尚未載入：
```bash
source ~/.zshrc
```

**方法 1: 使用便利腳本 (推薦)**

```bash
# 1. 複製客戶端範例到你的專案（從本 repo 的 examples/ 目錄）
cp examples/infra_client.py your-project/
cp examples/new_project_setup.py your-project/
chmod +x your-project/new_project_setup.py

# 2. 執行設定 (互動模式)
./new_project_setup.py

# 或使用命令列模式
./new_project_setup.py setup \
  --project my-app \
  --service web \
  --hostname myapp.your-domain.com \
  --port 5000
```

**方法 2: Claude Desktop 整合**

1. 編輯 Claude Desktop MCP 設定：
   ```bash
   # macOS
   nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. 新增 Infrastructure MCP Server：
   ```json
   {
     "mcpServers": {
       "infrastructure": {
         "type": "http",
         "url": "https://infra.your-domain.com/mcp",
         "headers": {
           "Content-Type": "application/json",
           "CF-Access-Client-Id": "YOUR_CLIENT_ID",
           "CF-Access-Client-Secret": "YOUR_CLIENT_SECRET"
         }
       }
     }
   }
   ```

3. 重啟 Claude Desktop，即可在對話中使用 MCP tools

**方法 3: Python SDK**

```python
from infra_client import InfrastructureMCPClient
import os
import asyncio

async def main():
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 分配 port
    result = await client.allocate_port("my-app", "web-server", 5000)
    print(result)

asyncio.run(main())
```

### 完整文檔

詳細的客戶端設定指南和使用範例：
- **[MCP Client Setup Guide](./docs/MCP-Client-Setup.md)** - 完整的客戶端配置指南
  - Claude Desktop 整合
  - Cloudflare Access 認證
  - Python SDK 使用
  - 故障排除

- **[範例程式碼](./examples/)** - 可直接使用的範例
  - `infra_client.py` - Python 客戶端函式庫
  - `new_project_setup.py` - 新專案設定腳本

### Management Commands

```bash
# SSH to server
ssh YOUR_USER@prod.your-domain.com

# Service management
sudo systemctl status infra-mcp
sudo systemctl restart infra-mcp
sudo systemctl stop infra-mcp

# View logs
sudo journalctl -u infra-mcp -f
sudo journalctl -u cloudflared-infra-mcp -f

# Tunnel management (use vps-tunnel-management skill)
sudo systemctl status cloudflared-infra-mcp
sudo systemctl restart cloudflared-infra-mcp

# Database location
ls -la /home/YOUR_USER/infra-mcp/configs/resources.db
```

## 🏗️ 專案架構

```
infra-mcp/
├── main/                      # MCP server 主程式
│   ├── server.py              # FastAPI + JSON-RPC 2.0 入口
│   ├── config.py              # 環境變數載入
│   ├── utils.py               # 共用工具函式
│   ├── tools/                 # MCP tools 實作（每個 tool 一個檔案）
│   │   ├── allocate_port.py
│   │   ├── deploy_service.py
│   │   ├── register_service.py
│   │   ├── list_resources.py
│   │   ├── cloudflare/        # Cloudflare API tools
│   │   └── gitea/             # Gitea repo management tools
│   ├── models/                # SQLAlchemy 資料模型
│   ├── db/                    # 資料庫存取層
│   └── providers/             # SSH / Cloudflare provider
├── configs/                   # 設定檔（gitignored）
│   └── resources.db           # SQLite 資料庫
├── deploy/                    # 部署設定
│   └── infra-mcp.service      # systemd unit file
├── docs/                      # 專案文檔
│   ├── Architecture.md        # 架構設計文檔
│   ├── MCP-API.md             # MCP Tools API 規格
│   ├── Data-Models.md         # 資料模型設計
│   └── MCP-Client-Setup.md    # MCP 客戶端設定指南
├── .env.example               # 環境變數範本
└── README.md                  # 本檔案
```

詳細架構說明請參考 [`docs/Architecture.md`](./docs/Architecture.md)。

## 🛠️ 技術棧

**MCP Server**
- Python 3.11+
- FastAPI (HTTP server, JSON-RPC 2.0 transport)
- SQLite + SQLAlchemy (resource database)
- asyncssh / subprocess (SSH command execution)

**Infrastructure Management**
- Cloudflare API (DNS, Tunnels, Access)
- SSH/paramiko (VPS deployment)
- systemd (Service management on VPS)
- cloudflared (Tunnel daemon)

**Deployment**
- Git-based version control
- Python virtual environments
- systemd services on VPS
- Future: Docker containerization

## 📚 文檔

**核心文檔**:

**架構設計文檔**:
- [`docs/Architecture.md`](./docs/Architecture.md) - MCP Server 完整架構設計
- [`docs/MCP-API.md`](./docs/MCP-API.md) - MCP Tools API 規格與使用範例
- [`docs/Data-Models.md`](./docs/Data-Models.md) - 資源資料模型定義
## 📄 License

MIT License — see [LICENSE](./LICENSE) file for details.

## 🔗 相關資源

---

For detailed architecture and API documentation, see [`docs/`](./docs/).
