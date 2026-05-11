# Security Configuration Templates

這些模板提供了符合 Zero Trust 架構的安全配置範例。

## 核心原則

**所有服務必須綁定到 127.0.0.1（localhost），只通過 Cloudflare Tunnel 對外提供訪問。**

## 模板列表

### 1. docker-compose.secure.yml

Docker Compose 安全配置模板。

**關鍵配置**：
```yaml
ports:
  - "127.0.0.1:${APP_PORT}:${APP_PORT}"
```

**使用方法**：
```bash
# 複製模板
cp templates/docker-compose.secure.yml ~/PRJ/your-project/docker-compose.yml

# 編輯變數
export PROJECT="your-project"
export SERVICE="your-service"
export APP_PORT="8080"

# 替換變數（可選）
envsubst < docker-compose.yml > docker-compose.tmp
mv docker-compose.tmp docker-compose.yml

# 啟動服務
docker compose up -d
```

### 2. Caddyfile.secure

Caddy 安全配置模板。

**關鍵配置**：
```caddyfile
your-domain.com:80 {
    bind 127.0.0.1
    reverse_proxy localhost:8080
}
```

**使用方法**：
```bash
# 複製模板
sudo cp templates/Caddyfile.secure /etc/caddy/sites/your-project-your-service.caddy

# 編輯配置
sudo nano /etc/caddy/sites/your-project-your-service.caddy

# 驗證配置
sudo caddy validate --config /etc/caddy/Caddyfile

# 重啟 Caddy
sudo systemctl restart caddy
```

### 3. systemd.secure.service

Systemd 服務安全配置模板。

**關鍵配置**：
```ini
Environment="HOST=127.0.0.1"
Environment="PORT=8080"
ExecStart=... --bind 127.0.0.1:8080 ...
```

**使用方法**：
```bash
# 複製模板
sudo cp templates/systemd.secure.service /etc/systemd/system/your-project-your-service.service

# 編輯配置
sudo nano /etc/systemd/system/your-project-your-service.service

# 重新載入 systemd
sudo systemctl daemon-reload

# 啟用並啟動服務
sudo systemctl enable your-project-your-service
sudo systemctl start your-project-your-service

# 檢查狀態
sudo systemctl status your-project-your-service
```

## 變數說明

| 變數 | 說明 | 範例 |
|------|------|------|
| `${PROJECT}` | 專案名稱 | `PAC`, `tcm-go` |
| `${SERVICE}` | 服務名稱 | `dashboard`, `api` |
| `${HOSTNAME}` | 公開域名 | `pac.nowhere.tw` |
| `${APP_PORT}` | 應用端口 | `8080`, `5000` |

## 安全檢查清單

部署前請確認：

- [ ] Docker ports 格式為 `127.0.0.1:port:port`
- [ ] Caddy 配置包含 `bind 127.0.0.1`
- [ ] Systemd 環境變數 `HOST=127.0.0.1`
- [ ] 應用程式綁定到 `127.0.0.1` 而非 `0.0.0.0`
- [ ] UFW 防火牆只開放 SSH (port 22)
- [ ] 服務通過 Cloudflare Tunnel 對外訪問

## 驗證部署

使用 Infrastructure MCP 工具驗證：

```bash
# 1. 驗證服務安全配置
validate_service_security(project="...", service="...", server="...")

# 2. 檢查監聽端口
check_listening_ports(server="...")

# 3. 測試服務健康狀態
check_service_health(server="...", project="...", service="...")
```

## 常見錯誤

### 錯誤 1：端口公開暴露

**問題**：
```yaml
ports:
  - "8080:8080"  # ❌ 錯誤
```

**修正**：
```yaml
ports:
  - "127.0.0.1:8080:8080"  # ✅ 正確
```

### 錯誤 2：Caddy 缺少 bind 指令

**問題**：
```caddyfile
example.com:80 {
    reverse_proxy localhost:8080  # ❌ 缺少 bind
}
```

**修正**：
```caddyfile
example.com:80 {
    bind 127.0.0.1  # ✅ 必須添加
    reverse_proxy localhost:8080
}
```

### 錯誤 3：環境變數綁定錯誤

**問題**：
```ini
Environment="HOST=0.0.0.0"  # ❌ 錯誤
```

**修正**：
```ini
Environment="HOST=127.0.0.1"  # ✅ 正確
```

## 參考資源

- [Infrastructure MCP Security Tools Guide](../docs/security-tools-guide.md)
- [PROJECT.md](../PROJECT.md)
- [Zero Trust Architecture](https://www.cloudflare.com/learning/security/glossary/what-is-zero-trust/)

---

**版本**：1.0
**最後更新**：2026-01-28
