# Infrastructure MCP Server - Implementation Plan

**文檔版本**: v1.0
**最後更新**: 2025-12-28
**狀態**: Planning Phase

---

## 📖 Executive Summary

Infrastructure MCP Server 將分三個階段實作，每個階段都能獨立運作並為下一階段奠定基礎。

### 開發原則

1. **Incremental Delivery**: 每個 Phase 完成後即可投入使用
2. **Quick Wins First**: Phase 1 專注最小可行產品（MVP）
3. **Learn & Iterate**: 每個 Phase 結束後回顧並調整計畫
4. **Documentation First**: 先文檔後實作，確保設計清晰

---

## 🎯 Phase Overview

| Phase | 目標 | 預計時間 | 狀態 |
|-------|------|---------|------|
| Phase 1 | MVP - 基本 MCP Server + 4 個 tools | 2-3 weeks | Planning |
| Phase 2 | 改進 - SQLite + 監控 + Web UI | 3-4 weeks | Not Started |
| Phase 3 | 擴展 - 多伺服器 + CI/CD 整合 | 4-6 weeks | Not Started |

---

## 🚀 Phase 1: Minimum Viable Product (MVP)

### 目標

建立可運作的 MCP Server，支援基本的資源分配和部署功能。

### 功能清單

#### Core Features (Must Have)

- ✅ **MCP Server 框架**
  - Python MCP SDK 整合
  - 與 Claude Desktop 連接
  - 基本錯誤處理

- ✅ **4 個 MCP Tools**
  1. `allocate_port` - Port 分配
  2. `register_tunnel` - Tunnel 註冊
  3. `deploy_tunnel` - Tunnel 部署
  4. `list_resources` - 資源查詢

- ✅ **資源管理**
  - JSON 檔案型資料庫
  - Port pool 管理（3000-9999）
  - 基本衝突偵測（port 重複、hostname 碰撞）

- ✅ **VPS 操作**
  - SSH 連線到 prod
  - 檔案傳輸（rsync）
  - systemd service 建立和管理

- ✅ **Cloudflare 整合**
  - DNS CNAME 記錄建立
  - Tunnel config 生成

#### Nice to Have

- 📋 基本日誌記錄
- 📋 Configuration validation
- 📋 Dry-run mode（預覽操作不執行）

### 技術棧

- **語言**: Python 3.11+
- **MCP SDK**: `mcp` package
- **SSH**: `paramiko` or `fabric`
- **Cloudflare API**: `cloudflare` Python SDK
- **Storage**: JSON files

### 檔案結構

```
infra-mcp/
├── main/
│   ├── mcp_server.py           # MCP server 主程式
│   ├── __init__.py
│   │
│   ├── tools/                  # MCP tools 實作
│   │   ├── __init__.py
│   │   ├── allocate_port.py
│   │   ├── register_tunnel.py
│   │   ├── deploy_tunnel.py
│   │   └── list_resources.py
│   │
│   ├── models/                 # 資料模型
│   │   ├── __init__.py
│   │   ├── port_allocation.py
│   │   ├── tunnel.py
│   │   └── deployment.py
│   │
│   ├── managers/               # 資源管理器
│   │   ├── __init__.py
│   │   ├── port_manager.py
│   │   ├── tunnel_manager.py
│   │   └── deployment_manager.py
│   │
│   ├── providers/              # 外部服務提供者
│   │   ├── __init__.py
│   │   ├── ssh_provider.py     # SSH 連線
│   │   └── cloudflare_provider.py
│   │
│   └── db/                     # 資料庫操作
│       ├── __init__.py
│       ├── json_store.py       # Phase 1: JSON storage
│       └── base.py             # Abstract interface
│
├── configs/
│   ├── servers.yml             # VPS 配置
│   ├── cloudflare.yml          # Cloudflare 配置
│   └── resources.json          # 資源分配資料
│
├── .env.example                # 環境變數範本
├── requirements.txt            # Python dependencies
└── setup.py                    # Package setup
```

### 實作步驟

#### Week 1: 基礎建設

**Day 1-2: 專案設置**
```bash
# 1. 建立 Python virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 2. 安裝基礎套件
pip install mcp anthropic-sdk paramiko pyyaml

# 3. 建立基本檔案結構
mkdir -p main/{tools,models,managers,providers,db}
touch main/__init__.py
# ... 建立其他 __init__.py
```

**Day 3-4: MCP Server 框架**
- 實作 `main/mcp_server.py`
- 設定 MCP server 基本架構
- 測試與 Claude Desktop 連接

**Day 5-7: JSON Storage & Models**
- 實作 `main/db/json_store.py`
- 定義 data models (port_allocation, tunnel, deployment)
- 建立測試資料
- Unit tests

#### Week 2: Core Tools Implementation

**Day 8-10: allocate_port**
- 實作 port pool 管理邏輯
- Port 衝突偵測
- Unit tests
- Integration test with MCP server

**Day 11-12: register_tunnel**
- Cloudflare API 整合
- DNS CNAME 建立
- Tunnel config YAML 生成
- Unit tests

**Day 13-14: list_resources**
- 資源查詢邏輯
- 資料格式化
- Filtering 功能
- Unit tests

#### Week 3: Deployment & Testing

**Day 15-18: deploy_tunnel**
- SSH 連線邏輯
- rsync 檔案傳輸
- systemd service 建立
- Flask app 部署
- Tunnel deployment
- Integration tests

**Day 19-20: End-to-End Testing**
- 完整流程測試（分配 port → 註冊 tunnel → 部署應用）
- 錯誤處理測試
- Edge cases

**Day 21: Documentation & Polish**
- 使用說明文檔
- Code cleanup
- 準備 demo

### 驗收標準

Phase 1 完成條件：

- [ ] MCP Server 可在 Claude Desktop 中使用
- [ ] 成功分配至少 5 個 ports（無衝突）
- [ ] 成功註冊至少 3 個 tunnels（含 DNS 配置）
- [ ] 成功部署至少 2 個 Flask 應用到 prod
- [ ] list_resources 能正確顯示所有資源
- [ ] 完整的錯誤處理（至少 80% error paths 有測試）
- [ ] 基本文檔完成（README, API docs）

### 已知風險與緩解

| 風險 | 影響 | 機率 | 緩解措施 |
|-----|------|------|---------|
| MCP SDK API 不熟悉 | High | Medium | 先建立簡單 demo 熟悉 SDK |
| SSH 自動化失敗 | Medium | Low | 手動測試 SSH 流程，準備 fallback |
| Cloudflare API 限制 | Low | Low | 使用 API token，注意 rate limit |
| JSON 檔案鎖定問題 | Medium | Medium | 實作簡單的檔案鎖定機制 |

---

## 🔄 Phase 2: Improvements & Scalability

### 目標

改進資料儲存、新增監控功能、建立 Web UI。

### 功能清單

#### Database Migration
- [ ] SQLite 資料庫取代 JSON
- [ ] Migration 工具（JSON → SQLite）
- [ ] Backward compatibility

#### Resource Management
- [ ] 資源自動回收機制
- [ ] Port 使用統計
- [ ] Tunnel 健康檢查（定期 ping）

#### Deployment Enhancements
- [ ] Node.js 應用部署支援
- [ ] 靜態網站部署支援
- [ ] 環境變數管理改進

#### Monitoring & Logging
- [ ] Deployment 健康監控
- [ ] Service uptime tracking
- [ ] Resource usage 統計
- [ ] Alert 機制（service down, high resource usage）

#### Web UI (Optional)
- [ ] Dashboard 查看所有資源
- [ ] 資源使用圖表
- [ ] 手動資源管理介面

#### New Tools
- [ ] `release_port` - 釋放 port
- [ ] `unregister_tunnel` - 移除 tunnel
- [ ] `undeploy_from_vps` - 下線應用
- [ ] `get_deployment_logs` - 查看部署日誌
- [ ] `restart_service` - 重啟服務

### 技術棧 (Additional)

- **Database**: SQLite 3
- **Monitoring**: Custom Python scripts + cron jobs
- **Web UI**: FastAPI + React (or simple HTML dashboard)

### 實作時間

預計 3-4 週，可分為：
- Week 1: SQLite migration
- Week 2: Resource management improvements
- Week 3: Monitoring & new tools
- Week 4: Web UI (if needed)

### 驗收標準

- [ ] SQLite 資料庫運作正常
- [ ] 支援至少 10 個活躍 deployments
- [ ] 資源使用統計準確
- [ ] 健康監控能偵測 service failures
- [ ] Web UI 可查看所有資源（如果實作）

---

## 🌐 Phase 3: Multi-Server & Enterprise Features

### 目標

支援多台 VPS、整合 CI/CD、企業級功能。

### 功能清單

#### Multi-Server Support
- [ ] 支援至少 3 台 VPS
- [ ] 智能選擇最佳伺服器（based on load）
- [ ] 跨伺服器資源調度

#### CI/CD Integration
- [ ] GitHub Actions workflow 範本
- [ ] 自動部署 on push
- [ ] Deployment rollback 機制
- [ ] Blue-green deployment

#### Advanced Features
- [ ] Docker container 部署
- [ ] Load balancer 配置
- [ ] Database backup & restore
- [ ] SSL 憑證自動更新

#### Multi-User Support
- [ ] User authentication
- [ ] Role-based access control (RBAC)
- [ ] Team management
- [ ] Audit logs

#### Cost Management
- [ ] VPS 成本追蹤
- [ ] Cloudflare 用量統計
- [ ] 成本優化建議

#### High Availability
- [ ] Tunnel failover
- [ ] Application health checks
- [ ] Auto-restart on failure
- [ ] Disaster recovery plan

### 技術棧 (Additional)

- **Database**: PostgreSQL (遠端存取)
- **Container**: Docker + Docker Compose
- **CI/CD**: GitHub Actions
- **Authentication**: OAuth 2.0
- **Monitoring**: Prometheus + Grafana

### 實作時間

預計 4-6 週。

### 驗收標準

- [ ] 支援至少 3 台 VPS 同時運作
- [ ] CI/CD pipeline 自動部署成功
- [ ] Multi-user 支援至少 5 個 team members
- [ ] Cost tracking 準確
- [ ] High availability 測試通過

---

## 📊 Success Metrics

### Phase 1 Metrics

- **Functionality**: 4/4 tools working
- **Reliability**: < 5% error rate in deployments
- **Performance**: Deployment completes within 2 minutes
- **Documentation**: 100% API documented

### Phase 2 Metrics

- **Scalability**: Support 20+ active deployments
- **Monitoring**: 95% uptime detection accuracy
- **User Experience**: Web UI response < 1s

### Phase 3 Metrics

- **Enterprise Ready**: RBAC + audit logs
- **Cost Efficiency**: 20% cost optimization
- **Multi-Server**: Load distribution variance < 30%

---

## 🗓️ Timeline & Milestones

```
2025-12-28: Project Start
│
├─ Week 1-3: Phase 1 Development
│   ├─ 2025-12-28: Project setup
│   ├─ 2026-01-03: MCP framework ready
│   ├─ 2026-01-10: Tools implementation
│   └─ 2026-01-17: Phase 1 Complete ✅
│
├─ 2026-01-20: Phase 1 Review & Planning
│
├─ Week 5-8: Phase 2 Development
│   ├─ 2026-01-24: SQLite migration
│   ├─ 2026-01-31: Monitoring features
│   ├─ 2026-02-07: Web UI
│   └─ 2026-02-14: Phase 2 Complete ✅
│
├─ 2026-02-17: Phase 2 Review & Planning
│
└─ Week 10-15: Phase 3 Development
    ├─ 2026-02-21: Multi-server support
    ├─ 2026-02-28: CI/CD integration
    ├─ 2026-03-07: Multi-user features
    ├─ 2026-03-14: HA & DR
    └─ 2026-03-21: Phase 3 Complete ✅
```

---

## 🎯 Immediate Next Steps (Phase 1 Start)

### Step 1: Environment Setup (Day 1)

```bash
cd ~/infra-mcp/

# 1. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install mcp anthropic-sdk paramiko cloudflare pyyaml
pip freeze > requirements.txt

# 3. Create .env file
cp .env.example .env
# Edit .env with your tokens
```

### Step 2: Create Basic Structure (Day 1)

```bash
# Create all necessary directories
mkdir -p main/{tools,models,managers,providers,db}

# Create __init__.py files
touch main/__init__.py
touch main/tools/__init__.py
touch main/models/__init__.py
touch main/managers/__init__.py
touch main/providers/__init__.py
touch main/db/__init__.py

# Create config files
touch configs/servers.yml
touch configs/cloudflare.yml
touch configs/resources.json
```

### Step 3: MCP Server Skeleton (Day 2)

建立 `main/mcp_server.py` 基本框架：

```python
#!/usr/bin/env python3
"""
Infrastructure MCP Server
Provides tools for managing VPS, Cloudflare Tunnels, and deployments
"""

import asyncio
from mcp import Server, Tool
from mcp.server import stdio_server

# Create MCP server instance
server = Server("infrastructure-mcp-server")

# Register tools
@server.tool()
async def allocate_port(
    project: str,
    service: str,
    preferred_port: int | None = None
):
    """Allocate a port for a project service"""
    # TODO: Implement
    pass

@server.tool()
async def register_tunnel(
    project: str,
    tunnel_name: str,
    hostname: str,
    target_port: int,
    vps_server: str = "prod"
):
    """Register a Cloudflare Tunnel"""
    # TODO: Implement
    pass

@server.tool()
async def deploy_tunnel(
    project: str,
    server: str,
    deployment_type: str,
    source_path: str,
    port: int,
    tunnel_name: str | None = None
):
    """Deploy application to VPS"""
    # TODO: Implement
    pass

@server.tool()
async def list_resources(
    resource_type: str = "all",
    project: str | None = None,
    server: str | None = None
):
    """List infrastructure resources"""
    # TODO: Implement
    pass

async def main():
    """Main entry point"""
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 4: Test MCP Server (Day 2)

```bash
# Run the server
python main/mcp_server.py

# Test in Claude Desktop:
# Add to claude_desktop_config.json:
{
  "mcpServers": {
    "infrastructure": {
      "command": "python",
      "args": ["/Users/your_user/infra-mcp/main/mcp_server.py"]
    }
  }
}
```

### Step 5: First Tool Implementation (Day 3-4)

選擇最簡單的 tool 開始：`list_resources`
- 實作 JSON store 讀取
- 返回基本資料
- 測試 MCP integration

---

## 📚 Learning Resources

### MCP (Model Context Protocol)
- Official docs: https://modelcontextprotocol.io/
- Python SDK: https://github.com/anthropics/mcp
- Examples: https://github.com/anthropics/mcp/tree/main/examples

### Cloudflare API
- API Docs: https://developers.cloudflare.com/api/
- Python SDK: https://github.com/cloudflare/cloudflare-python
- Tunnel Guide: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/

### systemd
- Service files: https://www.freedesktop.org/software/systemd/man/systemd.service.html
- journalctl: https://www.freedesktop.org/software/systemd/man/journalctl.html

---

## 🤝 Collaboration Workflow

### Using Claude Code

```bash
# 在 infra-mcp 專案中
source scripts/ai_helpers.sh

# 使用 AI 協助實作
claude_execute feature "實作 allocate_port tool"
# 這會執行：research → implement → review → document

# 或單步執行
ai_execute --task-type implement --prompt "實作 PortManager 類別"
ai_execute --task-type review --follow --prompt "審查 PortManager 實作"
```

### Git Workflow

```bash
# Feature branch
git checkout -b feature/allocate-port-tool

# Commit often
git add main/tools/allocate_port.py
git commit -m "feat: implement allocate_port tool

- Port pool management
- Conflict detection
- Unit tests
"

# Push and create PR
git push origin feature/allocate-port-tool
```

---

**文檔維護**: 每個 Phase 結束後更新
**下次審查**: Phase 1 Week 1 結束時
**維護責任**: Infrastructure Team (你 + Claude Code)
