# Infrastructure MCP Security Tools Guide

Infrastructure MCP Server 提供了一套完整的安全審計和運維工具，用於管理和監控 VPS 服務的安全配置。

## 安全審計工具

### 1. check_listening_ports

檢查 VPS 上所有監聽端口，識別未綁定到 127.0.0.1 的安全風險。

**用途**：
- 發現公開暴露的服務端口
- 驗證 Zero Trust 架構合規性
- 定期安全審計

**使用範例**：
```json
{
  "server": "staging"
}
```

**返回結果**：
- `summary`: 端口統計（總數、localhost only、潛在風險）
- `all_ports`: 所有監聽端口列表
- `security_risks`: 風險端口詳情

### 2. validate_service_security

驗證單個服務的安全配置，包括 Docker、Caddy、實際端口綁定。

**用途**：
- 部署後安全驗證
- 故障排查
- 配置審查

**使用範例**：
```json
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "auto_fix": false
}
```

**檢查項目**：
- Caddy 配置是否有 `bind 127.0.0.1`
- Docker port bindings 是否使用 `127.0.0.1:port:port`
- systemd 服務的 HOST 環境變數
- 實際端口綁定狀態

**auto_fix 功能**：
設置 `"auto_fix": true` 可自動修復部分問題（如 Caddy bind 指令）

### 3. audit_all_services

批量審計所有已部署服務的安全配置，生成完整報告。

**用途**：
- 全面安全審計
- 生成合規報告
- 批量修復安全問題

**使用範例**：
```json
{
  "server": "prod",
  "auto_fix": false
}
```

**返回結果**：
- `summary`: 總體統計（總服務數、安全/脆弱服務數、安全評分）
- `by_server`: 按 VPS 分組統計
- `services`: 每個服務的詳細審計結果

## 配置管理工具

### 4. get_caddy_config

獲取 Caddy 配置文件內容（主配置或服務專屬配置）。

**用途**：
- 檢視當前配置
- 排查路由問題
- 配置備份

**使用範例**：
```json
// 獲取主配置
{
  "server": "staging"
}

// 獲取服務專屬配置
{
  "server": "staging",
  "project": "tcm-go",
  "service": "poc"
}
```

### 5. get_tunnel_config

獲取 Cloudflare Tunnel 配置。

**用途**：
- 檢視 ingress 規則
- 確認 tunnel ID
- 診斷路由問題

**使用範例**：
```json
{
  "server": "dev2"
}
```

**返回結果**：
- `tunnel_id`: Tunnel UUID
- `credentials_file`: 憑證檔案路徑
- `ingress_rules`: 路由規則列表

## 服務重啟工具

### 6. restart_service

重啟服務組件（systemd service、Docker 容器、Caddy、Tunnel）。

**用途**：
- 套用配置變更
- 恢復故障服務
- 完成部署流程

**使用範例**：
```json
// 重啟主服務
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "component": "service"
}

// 重啟 Caddy
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "component": "caddy"
}

// 重啟 Tunnel
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "component": "tunnel"
}
```

**component 選項**：
- `service`: 主服務（systemd 或 Docker）
- `caddy`: Caddy web server
- `tunnel`: Cloudflare Tunnel

## 日誌管理工具

### 7. get_service_logs

獲取服務日誌（systemd、Docker、Caddy、Tunnel）。

**用途**：
- 故障排查
- 性能分析
- 安全事件調查

**使用範例**：
```json
// 獲取服務日誌
{
  "server": "prod",
  "project": "PAC",
  "service": "dashboard",
  "component": "service",
  "lines": 100
}

// 獲取 Caddy 日誌
{
  "server": "staging",
  "component": "caddy",
  "lines": 50
}

// 獲取 Tunnel 日誌
{
  "server": "dev2",
  "component": "tunnel",
  "lines": 50
}
```

**參數說明**：
- `lines`: 返回日誌行數（預設 50，最大 1000）
- `component`: 日誌來源（service/caddy/tunnel）

## 健康檢查工具

### 8. check_service_health

檢查服務和系統健康狀態。

**用途**：
- 監控服務狀態
- 系統資源監控
- 預防性維護

**使用範例**：
```json
// 檢查特定服務
{
  "server": "prod",
  "project": "PAC",
  "service": "dashboard",
  "include_system_stats": true
}

// 檢查基礎設施
{
  "server": "staging",
  "include_system_stats": true
}
```

**返回結果**：
- `service_health`: 服務狀態（如有指定）
- `infrastructure`: 基礎設施狀態（Caddy、Tunnel）
- `system_stats`: 系統資源統計（記憶體、磁碟、負載）
- `overall_health`: 總體健康狀態

## 最佳實踐

### 定期安全審計

**建議頻率**：每週一次

```bash
# 1. 檢查所有 VPS 的監聽端口
check_listening_ports(server="prod")
check_listening_ports(server="staging")
check_listening_ports(server="dev1")
check_listening_ports(server="dev2")

# 2. 審計所有服務
audit_all_services()
```

### 部署後驗證

每次部署新服務或修改配置後：

```bash
# 1. 驗證服務安全配置
validate_service_security(
    project="your-project",
    service="your-service",
    server="prod"
)

# 2. 檢查服務健康狀態
check_service_health(
    server="prod",
    project="your-project",
    service="your-service"
)

# 3. 檢查日誌確認正常啟動
get_service_logs(
    server="prod",
    project="your-project",
    service="your-service",
    lines=50
)
```

### 故障排查流程

當服務出現問題時：

```bash
# 1. 檢查健康狀態
check_service_health(server="prod", project="...", service="...")

# 2. 查看最近日誌
get_service_logs(server="prod", project="...", service="...", lines=100)

# 3. 檢查配置
get_caddy_config(server="prod", project="...", service="...")

# 4. 驗證安全配置
validate_service_security(project="...", service="...", server="prod")

# 5. 必要時重啟服務
restart_service(project="...", service="...", server="prod")
```

## 安全注意事項

1. **auto_fix 功能**：謹慎使用，建議先不帶 auto_fix 執行，確認問題後再啟用
2. **日誌敏感資訊**：日誌可能包含敏感資訊，注意保護
3. **重啟影響**：重啟服務會導致短暫中斷，選擇適當時機
4. **並發操作**：避免同時對同一服務執行多個操作

## 工具依賴關係

```
audit_all_services
  └── validate_service_security
        ├── get_caddy_config
        └── check_listening_ports

check_service_health
  └── get_service_logs (optional)

restart_service
  └── check_service_health (建議在重啟後執行)
```

## 故障排查指南

### 問題：check_listening_ports 報告端口暴露

**原因**：服務未綁定到 127.0.0.1

**解決方案**：
1. 使用 `validate_service_security` 找出具體服務
2. 使用 `auto_fix=true` 嘗試自動修復
3. 手動修改配置（Docker compose 或環境變數）
4. 使用 `restart_service` 重啟服務

### 問題：audit_all_services 顯示服務脆弱

**原因**：Caddy 配置缺少 bind 指令，或 Docker ports 配置錯誤

**解決方案**：
1. 檢查詳細的 `issues` 列表
2. 使用 `get_caddy_config` 查看配置
3. 使用 `auto_fix=true` 嘗試批量修復
4. 使用 `restart_service` 套用修復

### 問題：服務重啟失敗

**原因**：配置錯誤、端口衝突、依賴服務未運行

**解決方案**：
1. 使用 `get_service_logs` 查看錯誤日誌
2. 使用 `check_service_health` 檢查依賴服務
3. 使用 `check_listening_ports` 檢查端口衝突
4. 修正問題後再次重啟

---

**文檔版本**：1.0
**最後更新**：2026-01-28
**維護者**：Infrastructure MCP Team
