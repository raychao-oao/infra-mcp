# Infrastructure Management MCP

Centralized infrastructure resource management with MCP (Model Context Protocol) server for scalable allocation of VPS servers, Cloudflare Tunnels, ports, and domains across your projects.

---

## 📋 專案資訊

- **專案類型**: Infrastructure as Code / MCP Server
- **開發狀態**: In Development
- **版本**: v0.1.0
- **最後更新**: 2025-12-28

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
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env with Cloudflare API tokens and VPS credentials

# 4. Initialize resource database
python main/init_db.py

# 5. Start MCP server (development)
python main/mcp_server.py
```

### Using MCP Tools in Projects

```bash
# From any project that needs infrastructure:

# Allocate a port for your service
<use MCP tool: allocate_port>
  project: "my-app"
  service: "web-server"
  preferred_port: 3000

# Register a Cloudflare Tunnel
<use MCP tool: register_tunnel>
  project: "my-app"
  tunnel_name: "myapp"
  hostname: "myapp.your-domain.com"
  target_port: 3000

# Deploy to VPS
<use MCP tool: deploy_to_vps>
  project: "my-app"
  server: "prod"
  service_type: "flask"
```

## 🚢 Production Deployment

### Current Deployment

**Server**: prod.your-domain.com (your VPS provider)
**Endpoint**: https://infra.your-domain.com
**Status**: ✅ Live (deployed 2025-12-28)

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
# 1. 複製客戶端檔案到你的專案
curl -O https://raw.githubusercontent.com/.../examples/infra_client.py
curl -O https://raw.githubusercontent.com/.../examples/new_project_setup.py
chmod +x new_project_setup.py

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
│   ├── mcp_server.py          # MCP server 入口
│   ├── tools/                 # MCP tools 實作
│   │   ├── allocate_port.py
│   │   ├── register_tunnel.py
│   │   ├── deploy_to_vps.py
│   │   └── list_resources.py
│   ├── models/                # 資料模型
│   │   ├── resource.py
│   │   └── allocation.py
│   └── db/                    # 資料庫操作
│       └── manager.py
├── configs/                   # 設定檔
│   ├── servers.yml            # VPS 伺服器配置
│   ├── cloudflare.yml         # Cloudflare 服務配置
│   └── resources.json         # 資源分配資料庫
├── scripts/                   # 管理腳本
│   ├── ai_helpers.sh          # AI 協作輔助
│   ├── prompts/               # AI prompt 模板
│   └── wrappers/              # CLI wrappers
├── logs/                      # 日誌輸出
├── docs/                      # 專案文檔
│   ├── Architecture.md        # 架構設計文檔
│   ├── MCP-API.md             # MCP Tools API 規格
│   ├── Data-Models.md         # 資料模型設計
│   ├── Implementation-Plan.md # 實作計畫
│   ├── documentation-standards.md
│   └── ai_collaboration/      # AI 協作輸出
├── CLAUDE.md                  # Claude Code 協作指引
├── PROJECT.md                 # 專案核心知識庫
└── README.md                  # 本檔案
```

詳細架構說明請參考 [`docs/Architecture.md`](./docs/Architecture.md)。

## 🛠️ 技術棧

**MCP Server**
- Python 3.11+ (MCP server implementation)
- Model Context Protocol (MCP) SDK
- JSON-based resource database (Phase 1)
- Future: PostgreSQL/SQLite (Phase 2+)

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
- [`PROJECT.md`](./PROJECT.md) - 專案核心知識庫
- [`CLAUDE.md`](./CLAUDE.md) - Claude Code 協作指引
- [`docs/documentation-standards.md`](./docs/documentation-standards.md) - 文檔撰寫規範

**架構設計文檔**:
- [`docs/Architecture.md`](./docs/Architecture.md) - MCP Server 完整架構設計
- [`docs/MCP-API.md`](./docs/MCP-API.md) - MCP Tools API 規格與使用範例
- [`docs/Data-Models.md`](./docs/Data-Models.md) - 資源資料模型定義
- [`docs/Implementation-Plan.md`](./docs/Implementation-Plan.md) - 三階段實作計畫

## 👥 團隊

- **Project Lead**: [Name] ([email])
- **Technical Lead**: [Name] ([email])
- **Contributors**: [列出貢獻者]

## 📄 License

[License Type] - See [LICENSE](./LICENSE) file for details.

## 🔗 相關連結

- [External Resource 1](URL)
- [External Resource 2](URL)

---

For detailed development workflows and AI collaboration guidelines, please refer to:
- Claude Code: [`CLAUDE.md`](./CLAUDE.md)
- Project Info: [`PROJECT.md`](./PROJECT.md)
