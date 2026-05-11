# Infrastructure MCP Server - Quick Start Guide

**目標**: 5 分鐘內啟動 Infrastructure MCP Server 並測試第一個 tool

---

## 🚀 快速啟動（本地開發）

### 1. 環境設定（2 分鐘）

```bash
# Clone 專案（如果還沒有）
cd ~/PROJECTS
git clone <repository-url> infra-mcp
cd infra-mcp

# 建立虛擬環境
python3.11 -m venv venv
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 設定環境變數
cp .env.example .env
# 編輯 .env（如需使用 Cloudflare API）
```

### 2. 啟動 MCP Server（1 分鐘）

```bash
# 啟動 server
python main/server.py

# 看到以下訊息表示成功：
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 3. 測試第一個 Tool（2 分鐘）

**在另一個終端執行**（所有操作皆透過 `/mcp` endpoint，JSON-RPC 2.0 格式）：

```bash
# 1. 列出所有可用 tools
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools | length'
# 預期輸出: 31

# 2. 列出所有 tool 名稱
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq -r '.result.tools[].name' | head -5
# 預期輸出: allocate_port, release_port, list_resources, ...

# 3. 測試 list_resources tool
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_resources","arguments":{"resource_type":"all"}}}' | jq

# 4. 測試 allocate_port
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"allocate_port","arguments":{"project":"test","service":"demo","server":"prod"}}}' | jq
```

---

## 🎯 常見任務

### 查看已分配的 Ports

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_resources","arguments":{"resource_type":"ports"}}}' | jq
```

### 檢查伺服器的安全狀態

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"audit_all_services","arguments":{"server":"prod"}}}' | jq
```

### 列出所有已註冊的主 Tunnels

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_main_tunnels","arguments":{}}}' | jq
```

### 查看服務資訊

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_service_info","arguments":{"project":"my-app","service":"web","server":"prod"}}}' | jq
```

---

## 🔧 透過 Claude Code 使用 MCP Tools

### 在 Claude Desktop 中設定

編輯 `~/.config/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "infrastructure": {
      "command": "python",
      "args": ["/Users/YOUR_USER/infra-mcp/main/server.py"]
    }
  }
}
```

重啟 Claude Desktop，即可在對話中使用 infrastructure MCP tools。

### 在 Claude Code 中使用

Claude Code 會自動載入專案的 MCP server（如果在 `claude_desktop_config.json` 中設定）。

直接在對話中要求：
- "幫我在 prod 上分配一個 port 給 test-api"
- "檢查 prod 的安全狀態"
- "列出所有已部署的服務"

---

## 📊 31 個 MCP Tools 分類

### 1. Port & Resource (3)
- allocate_port, release_port, list_resources

### 2. Service Deployment (6)
- register_service, deploy_service, stop_service, purge_service, upgrade_service, get_service_info

### 3. Security Tools (3)
- check_listening_ports, validate_service_security, audit_all_services

### 4. Tunnel Management (3)
- register_main_tunnel, list_main_tunnels, get_tunnel_config

### 5. DNS Management (4)
- create_dns_record, update_dns_record, delete_dns_record, list_dns_records

### 6. Cloudflare Access (4)
- create_access_application, delete_access_application, list_access_applications, list_access_policies

### 7. Service Operations (8)
- restart_service, get_caddy_config, get_service_logs, check_service_health
- create_cloudflare_tunnel, delete_cloudflare_tunnel, list_cloudflare_tunnels, get_tunnel_token

完整 API 文檔請參考 [`docs/MCP-API.md`](docs/MCP-API.md)

---

## 🐛 疑難排解

### Port 8000 已被占用

```bash
# 檢查占用 8000 的程序
lsof -i :8000

# 終止該程序
kill -9 <PID>
```

### 虛擬環境找不到

```bash
# 重新建立
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### SQLite 資料庫權限錯誤

```bash
# 確保資料庫檔案有正確權限
chmod 644 infrastructure.db
```

---

## 📚 下一步

**學習更多**:
- 查看 [`docs/MCP-API.md`](docs/MCP-API.md) 了解所有 tool 的 API 規格
- 查看 [`docs/Architecture.md`](docs/Architecture.md) 了解系統架構

**生產部署**:
- SSH 到 prod: `ssh prod`
- 檢查生產狀態: `systemctl status infra-mcp`

---

**更新時間**: 2026-05-11
**適用版本**: Infrastructure Management MCP v1.0.0
