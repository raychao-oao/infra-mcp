# Infrastructure MCP Server - Complete Architecture Design

**文檔版本**: v1.0
**最後更新**: 2025-12-28
**狀態**: Design Phase

---

## 📖 Executive Summary

OAO Infrastructure Management 是一個基於 MCP (Model Context Protocol) 的集中式基礎設施資源管理系統。透過 MCP Server 提供標準化工具，讓所有專案都能透過 Claude Code 統一申請和管理基礎設施資源（VPS、Cloudflare Tunnels、Port、Domain），避免資源衝突並提升組織擴展性。

### 核心價值

1. **集中管理，避免衝突**
   - 所有 port 分配、tunnel 註冊、domain 使用都記錄在中央資料庫
   - 自動偵測並防止資源衝突（port 重複使用、subdomain 碰撞等）

2. **標準化申請流程**
   - 專案透過統一的 MCP tools 申請資源
   - 無需手動編輯配置檔案或 SSH 到伺服器
   - 降低人為錯誤和配置不一致

3. **可擴展架構**
   - 輕鬆新增 VPS 伺服器
   - 支援多個 Cloudflare 帳號
   - 未來可整合更多雲服務（AWS、GCP等）

4. **完整可追溯性**
   - 記錄誰在何時申請了什麼資源
   - 方便審計和成本分析
   - 簡化資源回收流程

---

## 🎯 Design Goals

### Must Have (Phase 1)
- ✅ MCP Server 基本框架（支援 Claude Desktop 整合）
- ✅ 4 個核心 MCP Tools（allocate_port, register_tunnel, deploy_tunnel, list_resources）
- ✅ JSON 檔案型資源資料庫
- ✅ 基本資源衝突偵測
- ✅ prod VPS 支援
- ✅ 參考 Deployment Scripts（可選使用）

### Should Have (Phase 2)
- 📋 SQLite/PostgreSQL 資料庫
- 📋 資源自動回收機制
- 📋 使用統計和成本分析
- 📋 Web UI（查看資源使用狀況）
- 📋 支援多台 VPS 伺服器

### Could Have (Phase 3)
- 💡 Cloudflare Workers 自動部署
- 💡 Cloudflare R2 storage 管理
- 💡 自動化 SSL 憑證管理
- 💡 負載均衡配置
- 💡 備份和災難恢復

---

## 🏗️ System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code / Claude Desktop             │
│                    (在任意專案中使用 MCP tools)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ MCP Protocol
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure MCP Server                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐        │
│  │ allocate    │  │ register    │  │ deploy       │        │
│  │ _port       │  │ _tunnel     │  │ _tunnel      │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘        │
│         │                 │                 │                │
│         └─────────────────┴─────────────────┘                │
│                           │                                  │
│                           ▼                                  │
│                  ┌─────────────────┐                         │
│                  │ Resource Manager │                         │
│                  │  (資源分配邏輯)   │                         │
│                  └────────┬─────────┘                         │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐                │
│         ▼                 ▼                 ▼                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐         │
│  │ Port Pool   │  │ Tunnel      │  │ VPS Server   │         │
│  │ Manager     │  │ Registry    │  │ Deployer     │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘         │
│         │                 │                 │                │
└─────────┼─────────────────┼─────────────────┼────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
   ┌─────────────────────────────────────────────────┐
   │          Resource Database (JSON/SQLite)        │
   │  - Port allocations                              │
   │  - Tunnel registrations                          │
   │  - Server deployments                            │
   │  - Resource ownership                            │
   └──────────────────────┬──────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌──────────┐   ┌─────────────┐  ┌────────────┐
   │ prod     │   │ Cloudflare  │  │ Future VPS │
   │ VPS      │   │ API         │  │ Servers    │
   └──────────┘   └─────────────┘  └────────────┘
```

### Component Details

#### 1. MCP Server Core
**責任**:
- 處理來自 Claude 的 MCP tool 呼叫
- 參數驗證和錯誤處理
- 回傳結果給 Claude

**技術**:
- Python 3.11+
- MCP SDK (Anthropic)
- FastAPI (optional, for future Web UI)

#### 2. Resource Manager
**責任**:
- 統一的資源分配邏輯
- 衝突偵測（port 重複、subdomain 碰撞）
- 資源狀態追蹤（allocated, in-use, released）

**關鍵功能**:
```python
class ResourceManager:
    def allocate_port(self, project, service, preferred_port=None):
        # 1. 檢查 preferred_port 是否可用
        # 2. 如果不可用，從 port pool 分配下一個可用 port
        # 3. 記錄分配資訊到資料庫
        # 4. 回傳分配的 port
        pass

    def register_tunnel(self, project, tunnel_name, hostname, target_port):
        # 1. 驗證 hostname 未被使用
        # 2. 驗證 target_port 已被分配給該專案
        # 3. 建立 tunnel 配置檔案
        # 4. 註冊到資料庫
        pass
```

#### 3. Port Pool Manager
**責任**:
- 管理可用 port 範圍（3000-9999）
- 追蹤已分配 port
- 支援 port 回收

**Port 分配策略**:
- System ports (0-1023): 保留不使用
- Registered ports (1024-2999): 保留不使用
- User ports (3000-9999): 可分配範圍
- 優先分配用戶偏好的 port（如果可用）
- 否則分配範圍內最小未使用 port

#### 4. Tunnel Registry
**責任**:
- 管理 Cloudflare Tunnel 配置
- 生成 tunnel config YAML
- 更新 DNS 記錄（透過 Cloudflare API）
- 在 VPS 上建立/更新 systemd service

**Tunnel 生命週期**:
```
1. 註冊階段 (register_tunnel)
   - 建立 config-<tunnel-name>.yml
   - 設定 DNS CNAME 記錄

2. 部署階段 (deploy_tunnel)
   - 複製 config 到 VPS
   - 建立 systemd service
   - 啟動 tunnel

3. 運行階段
   - 監控 tunnel 狀態（未來功能）
   - 日誌管理

4. 回收階段（未來功能）
   - 停止 tunnel
   - 刪除 DNS 記錄
   - 釋放 port
```

#### 5. VPS Server Deployer
**責任**:
- SSH 連線到 VPS 伺服器
- 部署應用程式（Flask, Node.js, etc.）
- 建立 systemd service
- 啟動並監控服務

**支援的部署類型**:
- Flask application (Python)
- Express/Fastify application (Node.js)
- Static site (Caddy/Nginx)
- Docker container (Phase 2)

---

## 📊 Data Models

### Resource Allocation Record

```json
{
  "allocation_id": "alloc_20251228_001",
  "resource_type": "port",
  "resource_value": 3000,
  "project": "my-app",
  "service": "web-server",
  "allocated_at": "2025-12-28T10:00:00Z",
  "allocated_by": "claude-code",
  "status": "in-use",
  "notes": "Main application server"
}
```

### Tunnel Registration Record

```json
{
  "tunnel_id": "tunnel_20251228_001",
  "tunnel_name": "myapp",
  "project": "my-app",
  "hostname": "myapp.your-domain.com",
  "target_service": "http://localhost:3000",
  "target_port": 3000,
  "vps_server": "prod",
  "config_path": "/home/your_user/.cloudflared/config-myapp.yml",
  "credentials_file": "/home/your_user/.cloudflared/<tunnel-id>.json",
  "systemd_service": "cloudflared-myapp.service",
  "registered_at": "2025-12-28T10:15:00Z",
  "status": "active",
  "dns_configured": true
}
```

### VPS Server Configuration

```yaml
servers:
  prod:
    hostname: prod.your-domain.com
    ip: YOUR_SERVER_IP
    location: Germany
    provider: Netcup
    plan: RS 1000 G12
    specs:
      cpu: AMD EPYC 9645 (4 cores)
      ram: 7.8GB
      disk: 256GB NVMe
      network: 1Gbps
    os: Debian 13 (trixie)
    ssh:
      user: your_user
      port: 22
      key_path: ~/.ssh/id_ed25519
    capabilities:
      - flask_app
      - nodejs_app
      - static_site
      - cloudflared_tunnel
    port_range:
      start: 3000
      end: 9999
    status: active
```

詳細資料模型定義請參考 [`Data-Models.md`](./Data-Models.md)。

---

## 🔧 MCP Tools Specification

### 1. allocate_port

**用途**: 為專案服務分配可用 port

**輸入參數**:
```json
{
  "project": "string (required)",
  "service": "string (required)",
  "preferred_port": "number (optional)"
}
```

**輸出**:
```json
{
  "success": true,
  "allocated_port": 3000,
  "allocation_id": "alloc_20251228_001",
  "message": "Port 3000 allocated to my-app/web-server"
}
```

**使用範例**:
```
<user>: 我的專案需要一個 port 來運行 web server
<claude>: 使用 allocate_port tool
  project: "my-app"
  service: "web-server"
  preferred_port: 3000
<result>: Port 3000 已分配給 my-app/web-server
```

### 2. register_tunnel

**用途**: 註冊 Cloudflare Tunnel 配置

**輸入參數**:
```json
{
  "project": "string (required)",
  "tunnel_name": "string (required)",
  "hostname": "string (required)",
  "target_port": "number (required)",
  "vps_server": "string (default: prod)"
}
```

**輸出**:
```json
{
  "success": true,
  "tunnel_id": "tunnel_20251228_001",
  "hostname": "myapp.your-domain.com",
  "config_path": "/home/your_user/.cloudflared/config-myapp.yml",
  "dns_instructions": "CNAME record created: myapp.your-domain.com -> <tunnel-id>.cfargotunnel.com",
  "message": "Tunnel myapp registered successfully"
}
```

### 3. deploy_tunnel

**用途**: 部署 Cloudflare Tunnel 到 VPS 伺服器

**輸入參數**:
```json
{
  "tunnel_name": "string (required, must be registered first)",
  "server": "string (default: prod)"
}
```

**輸出**:
```json
{
  "success": true,
  "tunnel_name": "myapp",
  "server": "prod",
  "service_name": "cloudflared-myapp.service",
  "status": "running",
  "hostname": "myapp.your-domain.com",
  "connections": 4,
  "message": "Tunnel deployed and started successfully"
}
```

### 4. list_resources

**用途**: 列出所有資源使用狀況

**輸入參數**:
```json
{
  "resource_type": "all|port|tunnel|deployment (default: all)",
  "project": "string (optional, filter by project)",
  "server": "string (optional, filter by server)"
}
```

**輸出**:
```json
{
  "success": true,
  "resources": {
    "ports": [
      {
        "port": 3000,
        "project": "my-app",
        "service": "web-server",
        "status": "in-use"
      }
    ],
    "tunnels": [
      {
        "name": "myapp",
        "hostname": "myapp.your-domain.com",
        "project": "my-app",
        "status": "active"
      }
    ],
    "deployments": [
      {
        "project": "my-app",
        "server": "prod",
        "service": "myapp-web.service",
        "status": "running"
      }
    ]
  },
  "summary": {
    "total_ports_allocated": 1,
    "total_tunnels_active": 1,
    "total_deployments": 1
  }
}
```

完整 API 規格請參考 [`MCP-API.md`](./MCP-API.md)。

---

## 🔐 Security Considerations

### Authentication & Authorization

**Phase 1** (當前設計):
- MCP Server 運行在本地，只接受來自 Claude Desktop 的請求
- SSH key-based 認證到 VPS 伺服器
- Cloudflare API token 儲存在環境變數

**Phase 2** (未來改進):
- 支援多用戶（team members）
- 基於角色的權限控制（RBAC）
- 審計日誌記錄所有資源操作

### Secrets Management

- SSH private keys: `~/.ssh/id_ed25519`
- Cloudflare API token: 環境變數 `CLOUDFLARE_API_TOKEN`
- VPS sudo 密碼: 環境變數（prod 有 NOPASSWD sudo，暫不需要）
- 未來: 考慮使用 HashiCorp Vault 或 1Password CLI

### Network Security

- 所有 VPS 只開放 SSH port 22
- Web 流量全部透過 Cloudflare Tunnel (Zero Trust)
- Tunnel 憑證檔案權限設為 600 (僅 owner 可讀寫)

---

## 🚀 Deployment Strategy

### Development Environment

```bash
# Local machine
cd ~/infra-mcp/
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 設定環境變數
export CLOUDFLARE_API_TOKEN="your_token_here"

# 啟動 MCP server
python main/mcp_server.py
```

### Production Environment

**MCP Server 運行位置**: 本地開發機（Mac）
- 原因: MCP Server 需要與 Claude Desktop 整合
- 資料庫: 本地 JSON 檔案（Phase 1）或 SQLite（Phase 2）

**資源部署目標**: VPS 伺服器（prod 等）
- 透過 SSH 遠端部署
- systemd 管理服務生命週期

**未來考慮**:
- MCP Server 可以部署到雲端（支援遠端 team）
- 使用 HTTPS 和 authentication token 保護

---

## 📈 Scalability Plan

### 支援多台 VPS

```yaml
servers:
  prod:
    # ... 現有配置

  server2:
    hostname: server2.your-domain.com
    # ... 新伺服器配置

  server3:
    hostname: server3.your-domain.com
    # ... 新伺服器配置
```

Resource Manager 會自動：
- 選擇負載最低的伺服器
- 或由用戶指定部署目標伺服器

### 支援多個 Cloudflare 帳號

```yaml
cloudflare_accounts:
  primary:
    email: your@email.com
    api_token: ${CLOUDFLARE_API_TOKEN}
    domains:
      - your-domain.com

  client_a:
    email: client@example.com
    api_token: ${CLIENT_A_CF_TOKEN}
    domains:
      - client-domain.com
```

### Port Pool 擴展

當單一伺服器 port 不足時：
- 自動分配到其他 VPS
- 或提示用戶擴展伺服器數量

---

## 🎯 Success Metrics

### Phase 1 完成標準

- ✅ 成功透過 MCP tools 分配至少 5 個 ports
- ✅ 成功註冊至少 3 個 Cloudflare Tunnels
- ✅ 成功部署至少 2 個應用到 prod
- ✅ Zero port 衝突、zero subdomain 碰撞
- ✅ 完整的資源使用記錄（可追溯）

### Phase 2 目標

- 📊 支援至少 3 台 VPS 伺服器
- 📊 管理超過 20 個活躍 tunnels
- 📊 資源使用 dashboard（Web UI）
- 📊 自動化資源回收機制

### Phase 3 願景

- 💡 支援整個組織（10+ team members）
- 💡 整合 CI/CD pipeline
- 💡 成本追蹤和優化建議
- 💡 災難恢復和高可用性

---

## 📚 References

- [Model Context Protocol (MCP) Documentation](https://modelcontextprotocol.io/)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [systemd Service Management](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [VPS Tunnel Management Skill](~/.claude/skills/vps-tunnel-management/SKILL.md)
- [Local Tunnel Management Skill](~/.claude/skills/tunnel-management/SKILL.md)

---

**文檔維護**: 隨專案演進持續更新
**下次審查**: 2025-01-15
**維護責任**: Infrastructure Team
