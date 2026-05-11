# PROJECT.md - 專案核心知識庫

**專案名稱**: OAO Infrastructure Management
**專案類型**: Infrastructure as Code / MCP Server
**檔案版本**: v2.0_20260204_000000
**建立時間**: 2025-12-28 14:30:00
**最後更新**: 2026-02-04 00:00:00

---

## 📖 專案摘要

OAO Infrastructure Management 是一個基於 MCP (Model Context Protocol) 的集中式基礎設施資源管理系統。透過 **31 個標準化的 MCP tools**，讓所有專案都能透過 Claude Code 統一申請和管理基礎設施資源，包括：

- **VPS 伺服器**: 管理 4 台 VPS（prod, staging, dev1, dev2）
- **Service Deployment**: Flask/Node.js/Static/Docker 服務部署
- **Security Tools**: 全面的安全審計與驗證工具
- **Cloudflare Integration**: DNS、Tunnel、Access 完整管理
- **Port 分配**: 中央管理 port pool（3000-9999）
- **Domain 管理**: 統一管理 subdomain 分配（your-domain.com）

**目標使用者**: 所有需要基礎設施資源的專案（透過 Claude Code 或 MCP 客戶端操作）

**核心價值**: Zero Trust 架構、避免資源衝突、標準化部署流程、完整安全審計、可追溯性

---

## 🌐 管理的基礎設施

### VPS Servers (4 台)

**prod** (Production)
- Provider: Netcup RS 1000 G12 (Germany)
- Specs: AMD EPYC 9645 (4 cores), 7.8GB RAM, 256GB NVMe
- OS: Debian 13 (trixie)
- Access: `ssh prod` (configured in ~/.ssh/config, IP: YOUR_SERVER_IP)
- Security: Only port 22 open, full Cloudflare Tunnel architecture
- Services: Infrastructure MCP Server (systemd: infra-mcp.service)

**staging** (Dev/ARM)
- Provider: Oracle Cloud JP
- Specs: ARM-based (4 cores), 23GB RAM, 210GB
- Access: `ssh staging`
- Purpose: ARM architecture testing

**dev1** (Dev/x86)
- Provider: Oracle Cloud JP
- Specs: x86 (2 cores), 1GB RAM, 47GB
- Access: `ssh dev1`
- Purpose: Lightweight service testing

**dev2** (Dev/x86)
- Provider: Oracle Cloud JP
- Specs: x86 (2 cores), 1GB RAM, 45GB
- Access: `ssh dev2`
- Purpose: Lightweight service testing

### Cloudflare Services

**Managed Domains**:
- `your-domain.com` - Primary domain

**Active Tunnels**:
- app.your-domain.com → localhost:8080 (prod)
- sandbox.your-domain.com → localhost:5000 (prod)
- infra.your-domain.com → localhost:8000 (prod) - Infrastructure MCP Server

**Cloudflare Features Integrated**:
- DNS Management (full CRUD via API)
- Cloudflare Tunnel (via cloudflared CLI and API)
- Cloudflare Access (IP restrictions, email authentication)
- Automatic DNS record creation for tunnels

---

## 🏗️ Architecture

### High-Level Design

```
Projects (via Claude Code)
        ↓
   MCP Protocol
        ↓
Infrastructure MCP Server
├── allocate_port
├── register_tunnel
├── deploy_to_vps
└── list_resources
        ↓
Resource Manager → JSON Database
        ↓
    ┌───┴───┐
    ↓       ↓
prod  Cloudflare API
```

### Directory Structure

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
│   │   ├── port_allocation.py
│   │   ├── tunnel.py
│   │   └── deployment.py
│   ├── managers/              # 資源管理器
│   │   ├── port_manager.py
│   │   ├── tunnel_manager.py
│   │   └── deployment_manager.py
│   ├── providers/             # 外部服務提供者
│   │   ├── ssh_provider.py
│   │   └── cloudflare_provider.py
│   └── db/                    # 資料庫操作
│       ├── json_store.py      # Phase 1: JSON
│       └── base.py
├── configs/                   # 設定檔
│   ├── servers.yml            # VPS 配置
│   ├── cloudflare.yml         # Cloudflare 配置
│   └── resources.json         # 資源分配資料
├── scripts/                   # 管理腳本
│   ├── ai_helpers.sh          # AI 協作輔助
│   ├── prompts/               # AI prompt 模板
│   └── wrappers/              # CLI wrappers
├── logs/                      # 日誌輸出
├── docs/                      # 專案文檔
│   ├── Architecture.md        # 架構設計
│   ├── MCP-API.md             # MCP Tools API 規格
│   ├── Data-Models.md         # 資料模型
│   ├── Implementation-Plan.md # 實作計畫
│   ├── documentation-standards.md
│   └── ai_collaboration/
├── CLAUDE.md                  # Claude Code 協作指引
├── AGENTS.md                  # Codex CLI 協作指引
├── GEMINI.md                  # Gemini CLI 協作指引
├── PROJECT.md                 # 本檔案
├── README.md                  # 專案說明
├── .env.example               # 環境變數範本
├── requirements.txt           # Python dependencies
└── .gitignore
```

完整架構說明請參考 [`docs/Architecture.md`](./docs/Architecture.md)。

### MCP Server Components

**31 個 MCP Tools** 分為 7 大類：

**1. Port & Resource Management (3 tools)**
- `allocate_port` - Port 資源分配（3000-9999）
- `release_port` - 釋放 port 分配
- `list_resources` - 資源使用查詢（ports, tunnels, deployments）

**2. Service Deployment (6 tools)**
- `register_service` - 註冊服務配置（Flask/Node.js/Static/Docker/Flask+Static）
- `deploy_service` - 部署服務到 VPS（生成 systemd/Caddy/DNS）
- `stop_service` - 停止服務（保留配置）
- `purge_service` - 完全清理服務（可選刪除檔案）
- `upgrade_service` - 升級服務類型（如 static → flask+static）
- `get_service_info` - 獲取服務詳細資訊（URL、配置、狀態）

**3. Security Tools (3 tools)**
- `check_listening_ports` - 檢查外部暴露端口（安全風險偵測）
- `validate_service_security` - 驗證單一服務安全配置
- `audit_all_services` - 全面安全審計（所有已部署服務）

**4. Cloudflare Tunnel Management (3 tools)**
- `register_main_tunnel` - 註冊主 tunnel（每個 VPS 一個）
- `list_main_tunnels` - 列出所有已註冊 tunnels
- `get_tunnel_config` - 獲取 tunnel 配置檔案

**5. DNS Management (4 tools)**
- `create_dns_record` - 建立 DNS 記錄（A/AAAA/CNAME/TXT/MX）
- `update_dns_record` - 更新 DNS 記錄
- `delete_dns_record` - 刪除 DNS 記錄
- `list_dns_records` - 列出 zone 所有記錄

**6. Cloudflare Access (4 tools)**
- `create_access_application` - 建立存取應用（保護 URL）
- `delete_access_application` - 刪除存取應用
- `list_access_applications` - 列出所有應用
- `list_access_policies` - 列出存取政策

**7. Service Operations (8 tools)**
- `restart_service` - 重啟服務組件（service/caddy/tunnel）
- `get_caddy_config` - 獲取 Caddy 配置檔案
- `get_service_logs` - 獲取服務日誌（systemd/Docker/Caddy/Tunnel）
- `check_service_health` - 健康檢查（服務 + 系統資源）
- `create_cloudflare_tunnel` - 建立 tunnel（Cloudflare API）
- `delete_cloudflare_tunnel` - 刪除 tunnel
- `list_cloudflare_tunnels` - 列出 tunnels（API）
- `get_tunnel_token` - 獲取 tunnel 連線 token

**Resource Manager**:
- Port Pool 管理（3000-9999，SQLite 追蹤）
- Service Deployment 追蹤（project, service, server, type, port, hostname）
- Main Tunnel 註冊（每 VPS 一個主 tunnel）
- 衝突偵測（port 重複、hostname 碰撞）
- 安全狀態追蹤（SECURE/VULNERABLE/UNKNOWN）

**External Integrations**:
- SSH Library: asyncssh（async/await 架構）
- Cloudflare API: v4 REST API（DNS, Tunnel, Access）
- systemd service 管理（via SSH subprocess）
- Docker Compose 管理（via SSH subprocess）
- Caddy 配置管理（/etc/caddy/sites/）

### Technology Stack

**MCP Server (v2.0)**
- Language: Python 3.11+
- Framework: FastAPI (MCP over HTTP with SSE)
- Protocol: MCP Tools via HTTP POST + Server-Sent Events
- Storage: **SQLite** (infrastructure.db) - 已從 JSON 升級
- Deployment: systemd service (infra-mcp.service on prod)
- Port: 8000 (bound to 127.0.0.1, exposed via Cloudflare Tunnel)

**Infrastructure Management**
- SSH Library: **asyncssh** (async/await 架構)
- Cloudflare Integration: Cloudflare API v4 (REST) + cloudflared CLI
- VPS Management: systemd via SSH subprocess（4 台 VPS）
- Service Types: Flask, Node.js, Static, Docker, Flask+Static
- Configuration: Python code-based（不使用 YAML）

**Security Architecture**
- Zero Trust: 所有服務 bind 127.0.0.1（無外部暴露）
- External Access: 僅透過 Cloudflare Tunnel
- Security Validation: 部署前後自動檢查
- Templates: 安全配置模板（Docker/Caddy/systemd）

**Deployment Tools**
- File Transfer: rsync（SSH）
- Service Management: systemd（Flask/Node.js）、Docker Compose
- Reverse Proxy: Caddy（/etc/caddy/sites/*.caddy）
- Tunnel Daemon: cloudflared（systemd service）
- Process Monitoring: journalctl、Docker logs

**Development**
- Version Control: Git
- AI Collaboration: Claude Code (scripts/ai_helpers.sh)
- Task Management: Built-in task tracker（12 tasks completed）
- Documentation: Comprehensive docs/ directory（10 MD files）

---

## 🔧 Development Workflow

### Environment Setup

**Prerequisites**:
- Python 3.11+ installed
- Access to Cloudflare account (API token)
- SSH access to production VPS
- Claude Desktop (for MCP integration testing)

**Installation**:
```bash
# 1. Clone repository
git clone <repository-url>
cd infra-mcp

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment variables
cp .env.example .env
# Edit .env:
#   CLOUDFLARE_API_TOKEN=your_token
#   SSH_KEY_PATH=~/.ssh/id_ed25519

# 5. Initialize resource database
# configs/resources.json will be created on first run
```

**Claude Desktop Integration**:
```json
// Add to ~/.config/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "infrastructure": {
      "command": "python",
      "args": ["/Users/YOUR_USER/infra-mcp/main/mcp_server.py"]
    }
  }
}
```

### Development Workflow

**本地開發與測試**:
```bash
# 1. 啟動虛擬環境
cd ~/infra-mcp
source venv/bin/activate

# 2. 本地啟動 MCP server（開發測試）
python main/server.py
# Server 會在 http://localhost:8000 啟動

# 3. 測試 MCP tools（另一個終端）
# 列出所有可用 tools
curl -s http://localhost:8000/tools/list | jq '.tools | length'

# 測試安全審計
curl -s http://localhost:8000/tools/list | jq '.tools[] | select(.name=="audit_all_services")'

# 4. 查看即時日誌
tail -f logs/server.log
```

**實作新的 MCP Tool**:
```bash
# 1. 建立 tool 檔案
# main/tools/new_tool.py（包含 async function + validation）

# 2. 註冊到 server.py
# - 新增 import
# - 新增 tool schema（在 tools list）
# - 新增 call handler（在 elif chain）

# 3. 測試 tool
curl -X POST http://localhost:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"new_tool","arguments":{...}}'

# 4. Commit
git add main/tools/new_tool.py main/server.py
git commit -m "feat: implement new_tool"
```

**部署到 prod（生產環境）**:
```bash
# 1. 同步程式碼
rsync -av --delete \
    --exclude 'venv/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude 'logs/' --exclude 'infrastructure.db' \
    ~/infra-mcp/ prod:~/infra-mcp/

# 2. 重啟服務
ssh prod 'sudo systemctl restart infra-mcp'

# 3. 驗證部署
ssh prod 'systemctl status infra-mcp'
ssh prod 'sudo journalctl -u infra-mcp -n 50'

# 4. 測試 tools 數量
curl -s http://localhost:8000/tools/list | jq '.tools | length'
# 應該顯示: 31
```

**測試服務部署流程**:
```bash
# 透過 Claude Code 或 MCP 客戶端：
# 1. allocate_port（獲取 port）
# 2. register_service（註冊服務配置）
# 3. create_dns_record（建立 DNS CNAME）
# 4. deploy_service（執行完整部署）
# 5. validate_service_security（驗證安全性）

# SSH 驗證
ssh prod 'systemctl status <project>-<service>'
ssh prod 'sudo cat /etc/caddy/sites/<project>-<service>.caddy'
curl https://<hostname>
```

### Git Workflow

```bash
# 本地 Git
git add .
git commit -m "[commit message]"

# 推送到遠端
git push origin [branch]
```

---

## 🔒 Security Measures

### Zero Trust Architecture
- **Network Binding**: 所有服務強制 bind 127.0.0.1（無外部暴露）
- **External Access**: 僅透過 Cloudflare Tunnel（加密、身份驗證）
- **Security Validation**: 部署前後自動檢查（check_listening_ports, validate_service_security）
- **Audit Trail**: 全面安全審計工具（audit_all_services）

### MCP Server Security
- **Authentication**: Cloudflare Access（Email authentication, IP restrictions）
- **HTTPS**: Cloudflare Tunnel TLS 加密
- **No Public Ports**: 除 SSH (22) 外無任何 port 對外開放
- **Access Control**: infra.your-domain.com 受 Cloudflare Access 保護

### Service Security
- **Docker**: 強制 127.0.0.1 port binding（templates/docker-compose.secure.yml）
- **Caddy**: 強制 bind 127.0.0.1（templates/Caddyfile.secure）
- **systemd**: 環境變數強制 HOST=127.0.0.1（templates/systemd.secure.service）
- **Validation**: deploy_service 自動驗證安全配置

### System Security
- **SSH Key Authentication**: 僅 SSH key 登入（無密碼）
- **Firewall**: 僅 port 22 開放（其他全部封閉）
- **Database**: SQLite 檔案權限限制（僅 infra-mcp user）
- **Logs**: systemd journalctl（限制存取權限）

---

## 📅 Implementation Status

### Phase 1: Core MCP Tools ✅ COMPLETED
- Port allocation & release
- Service deployment lifecycle
- Resource tracking

### Phase 2: Security & Operations ✅ COMPLETED
- Security audit tools (3 tools)
- Configuration management (2 tools)
- Service operations (restart, logs, health)

### Phase 3: Cloudflare Integration ✅ COMPLETED
- DNS Management (4 tools)
- Tunnel Management (4 tools)
- Access Management (4 tools)

### Phase 4: Documentation ✅ COMPLETED
- Security tools guide
- Secure configuration templates
- Future enhancements documentation

**Current Status**: 31 MCP tools deployed and operational on prod

**Pending Work**: Task #10 - Database schema extension for security tracking (documented in docs/future-enhancements.md)

---

## 👥 Infrastructure Access

**VPS Servers**:
- prod: `ssh prod` (Production MCP Server)
- staging: `ssh staging` (Dev/ARM)
- dev1: `ssh dev1` (Dev/x86)
- dev2: `ssh dev2` (Dev/x86)

**MCP Server**:
- URL: https://infra.your-domain.com (Cloudflare Access protected)
- Local: http://localhost:8000 (when testing)
- Database: ~/infra-mcp/infrastructure.db (SQLite on prod)

**Cloudflare**:
- Dashboard: https://dash.cloudflare.com
- Managed Domains: your-domain.com
- API: Integrated in MCP tools

---

## 📚 Documentation

**核心文檔**:
- [`CLAUDE.md`](CLAUDE.md) - Claude Code 協作指引（AI 工作流）
- [`PROJECT.md`](PROJECT.md) - 本檔案（專案知識庫）
- [`README.md`](README.md) - 專案說明

**架構與設計**:
- [`docs/Architecture.md`](docs/Architecture.md) - 完整架構設計文檔
- [`docs/MCP-API.md`](docs/MCP-API.md) - MCP Tools API 規格
- [`docs/Data-Models.md`](docs/Data-Models.md) - 資料模型定義
- [`docs/Implementation-Plan.md`](docs/Implementation-Plan.md) - 實作計畫

**操作指南**:
- [`docs/security-tools-guide.md`](docs/security-tools-guide.md) - 安全工具使用指南（8 tools）
- [`docs/MCP-Client-Setup.md`](docs/MCP-Client-Setup.md) - MCP 客戶端設定


**開發資源**:
- [`docs/documentation-standards.md`](docs/documentation-standards.md) - 文檔撰寫標準
- [`docs/future-enhancements.md`](docs/future-enhancements.md) - 未來增強計劃
- [`templates/`](templates/) - 安全配置模板（Docker/Caddy/systemd）

**外部參考**:
- [MCP Specification](https://modelcontextprotocol.io/) - Model Context Protocol 規格
- [Cloudflare API Docs](https://developers.cloudflare.com/api/) - Cloudflare API 文檔
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - FastAPI 框架文檔

---

## 🔄 Changelog

### 2026-02-04 - v2.0 (Major Update)
- 完成所有 31 個 MCP tools 實作與部署
- 從 JSON 升級至 SQLite 資料庫
- 完成 Zero Trust 安全架構
- 新增 8 個安全工具（檢查、驗證、審計）
- 完成 Cloudflare 完整整合（DNS, Tunnel, Access）
- 支援 4 台 VPS（prod, staging, dev1, dev2）
- 新增完整文檔（10 個 MD 檔案）

### 2025-12-28 - v1.0 (Initial)
- 初始專案建立
- 定義核心架構
- 規劃 4 個基礎 MCP tools

---

**文檔建立**: 2025-12-28 14:30:00
**最後更新**: 2026-02-04 00:00:00
**下次審查**: 2026-03-01
