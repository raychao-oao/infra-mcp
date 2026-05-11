# MCP Client Setup Guide

Infrastructure MCP Server 客戶端設定指南

## 📋 目錄

- [Claude Desktop 設定](#claude-desktop-設定)
- [Cloudflare Access 認證](#cloudflare-access-認證)
- [Python SDK 整合](#python-sdk-整合)
- [直接 HTTP 呼叫](#直接-http-呼叫)
- [使用範例](#使用範例)
- [故障排除](#故障排除)

---

## Claude Desktop 設定

### 1. 找到設定檔

根據你的作業系統，編輯 Claude Desktop MCP 設定檔：

```bash
# macOS
~/Library/Application Support/Claude/claude_desktop_config.json

# Windows
%APPDATA%\Claude\claude_desktop_config.json

# Linux
~/.config/Claude/claude_desktop_config.json
```

### 2. 基本配置 (無認證，測試用)

如果暫時移除了 Cloudflare Access 保護：

```json
{
  "mcpServers": {
    "infrastructure": {
      "type": "http",
      "url": "https://infra.your-domain.com/mcp",
      "headers": {
        "Content-Type": "application/json"
      }
    }
  }
}
```

### 3. 生產配置 (含 Service Token)

**推薦用於生產環境**：

```json
{
  "mcpServers": {
    "infrastructure": {
      "type": "http",
      "url": "https://infra.your-domain.com/mcp",
      "headers": {
        "Content-Type": "application/json",
        "CF-Access-Client-Id": "YOUR_SERVICE_TOKEN_CLIENT_ID",
        "CF-Access-Client-Secret": "YOUR_SERVICE_TOKEN_CLIENT_SECRET"
      }
    }
  }
}
```

### 4. 重啟 Claude Desktop

設定完成後，重啟 Claude Desktop 讓配置生效。

---

## Cloudflare Access 認證

### 選項 A: Service Token (推薦)

**適用於**：自動化工具、MCP 客戶端、CI/CD

**步驟**：

1. **登入 Cloudflare Zero Trust Dashboard**
   - 前往 https://one.dash.cloudflare.com/
   - 選擇你的帳號

2. **建立 Service Token**
   ```
   Access → Service Auth → Create Service Token

   Name: MCP Client - [專案名稱]
   Token Duration: 1 year (或根據需求)
   ```

3. **複製 Token**
   - Client ID (顯示為一長串文字)
   - Client Secret (只顯示一次，務必保存)

4. **更新 Access Policy**

   需要修改 Infrastructure MCP Server 的 Access policy 以允許 Service Token：

   ```bash
   # 透過 API 或 Dashboard 更新 policy
   # 在 Dashboard:
   Access → Applications → Infrastructure MCP Server → Edit

   在 Policy 中新增 "Service Auth" rule:
   Include:
     - Service Token: [選擇你建立的 token]
   ```

5. **更新客戶端配置**

   將 Client ID 和 Secret 加入你的 MCP 客戶端配置（如上述 Claude Desktop 配置）

### 選項 B: 使用者認證 (人工操作)

**適用於**：手動測試、瀏覽器存取

**步驟**：

1. 在瀏覽器訪問 https://infra.your-domain.com
2. 使用允許的 email 登入 (目前: your@email.com)
3. 取得 session cookie
4. 在 API 請求中包含 cookie

**不推薦用於自動化**，因為 session 會過期。

### 選項 C: 移除 Access 保護 (僅開發測試)

**警告**：這會讓 MCP Server 公開暴露在網路上

```bash
# SSH 到 prod
ssh your_user@prod.your-domain.com

# 使用 Cloudflare API 移除 policy (不建議)
# 或在 Dashboard 暫時停用 Access Application
```

**強烈建議**：只在開發/測試時使用，並立即恢復保護。

---

## Python SDK 整合

### 安裝 MCP SDK

```bash
pip install mcp anthropic-mcp
```

### 基本使用範例

```python
# infra_client.py
import asyncio
import os
from typing import Optional
import httpx

class InfrastructureMCPClient:
    """Infrastructure MCP Server 客戶端"""

    def __init__(
        self,
        base_url: str = "https://infra.your-domain.com/mcp",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json"
        }

        # 加入 Cloudflare Access Service Token
        if client_id and client_secret:
            self.headers["CF-Access-Client-Id"] = client_id
            self.headers["CF-Access-Client-Secret"] = client_secret

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """呼叫 MCP tool"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            )
            response.raise_for_status()
            return response.json()

    async def allocate_port(
        self,
        project: str,
        service: str,
        preferred_port: Optional[int] = None
    ) -> dict:
        """分配 port"""
        return await self.call_tool("allocate_port", {
            "project": project,
            "service": service,
            "preferred_port": preferred_port
        })

    async def register_tunnel(
        self,
        project: str,
        tunnel_name: str,
        hostname: str,
        target_port: int
    ) -> dict:
        """註冊 Cloudflare Tunnel"""
        return await self.call_tool("register_tunnel", {
            "project": project,
            "tunnel_name": tunnel_name,
            "hostname": hostname,
            "target_port": target_port
        })

    async def list_resources(self) -> dict:
        """列出所有資源"""
        return await self.call_tool("list_resources", {})

# 使用範例
async def main():
    # 從環境變數讀取認證資訊
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 分配 port
    result = await client.allocate_port(
        project="my-app",
        service="web-server",
        preferred_port=5000
    )
    print(f"Allocated: {result}")

    # 註冊 tunnel
    tunnel_result = await client.register_tunnel(
        project="my-app",
        tunnel_name="my-app",
        hostname="myapp.your-domain.com",
        target_port=5000
    )
    print(f"Tunnel registered: {tunnel_result}")

    # 列出資源
    resources = await client.list_resources()
    print(f"All resources: {resources}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 在專案中使用

```python
# your_project/setup.py
from infra_client import InfrastructureMCPClient
import asyncio
import os

async def setup_infrastructure():
    """設定專案基礎設施"""
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 1. 分配 port
    port_result = await client.allocate_port(
        project="user-dashboard",
        service="flask-app"
    )
    port = port_result["result"]["content"][0]["text"].split()[-1]

    # 2. 註冊 tunnel
    await client.register_tunnel(
        project="user-dashboard",
        tunnel_name="user-dashboard",
        hostname="dashboard.your-domain.com",
        target_port=int(port)
    )

    print(f"✅ Infrastructure setup complete!")
    print(f"   Port: {port}")
    print(f"   URL: https://dashboard.your-domain.com")

if __name__ == "__main__":
    asyncio.run(setup_infrastructure())
```

---

## 直接 HTTP 呼叫

### 使用 curl

```bash
# 設定認證變數
export CF_CLIENT_ID="your_client_id"
export CF_CLIENT_SECRET="your_client_secret"

# 分配 port
curl -X POST https://infra.your-domain.com/mcp \
  -H "Content-Type: application/json" \
  -H "CF-Access-Client-Id: $CF_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "allocate_port",
      "arguments": {
        "project": "my-app",
        "service": "web-server",
        "preferred_port": 5000
      }
    }
  }'

# 列出資源
curl -X POST https://infra.your-domain.com/mcp \
  -H "Content-Type: application/json" \
  -H "CF-Access-Client-Id: $CF_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "list_resources",
      "arguments": {}
    }
  }'
```

### 使用 Postman/Insomnia

1. **設定 Request**
   - Method: POST
   - URL: https://infra.your-domain.com/mcp

2. **設定 Headers**
   ```
   Content-Type: application/json
   CF-Access-Client-Id: YOUR_CLIENT_ID
   CF-Access-Client-Secret: YOUR_CLIENT_SECRET
   ```

3. **設定 Body** (JSON)
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tools/call",
     "params": {
       "name": "allocate_port",
       "arguments": {
         "project": "test-project",
         "service": "api-server",
         "preferred_port": 8080
       }
     }
   }
   ```

---

## 使用範例

### 範例 1: 新專案初始化

```bash
# 1. 建立專案
mkdir my-new-app
cd my-new-app

# 2. 設定 Infrastructure Client
cat > setup_infra.py <<'EOF'
import asyncio
from infra_client import InfrastructureMCPClient
import os

async def main():
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 分配 port
    port = await client.allocate_port(
        project="my-new-app",
        service="web"
    )

    # 註冊 tunnel
    tunnel = await client.register_tunnel(
        project="my-new-app",
        tunnel_name="my-new-app",
        hostname="my-new-app.your-domain.com",
        target_port=int(port)
    )

    print("✅ Infrastructure ready!")

asyncio.run(main())
EOF

# 3. 執行設定
python setup_infra.py
```

### 範例 2: 從 Claude Desktop 使用

在 Claude Desktop 對話中：

```
User: 我要開發一個新的部落格系統，幫我設定基礎設施

Claude: 我來幫你向 Infrastructure MCP Server 申請資源

[使用 allocate_port]
project: "blog-system"
service: "nextjs-app"
preferred_port: 3000

結果: ✅ 已分配 port 3000

[使用 register_tunnel]
project: "blog-system"
tunnel_name: "blog"
hostname: "blog.your-domain.com"
target_port: 3000

結果: ✅ Tunnel 已註冊

你的部落格系統基礎設施已準備完成：
- Port: 3000
- Public URL: https://blog.your-domain.com
- 可以開始開發了！
```

### 範例 3: CI/CD 整合

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  setup-infrastructure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Infrastructure
        env:
          CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}
          CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}
        run: |
          # 呼叫 MCP Server 分配資源
          curl -X POST https://infra.your-domain.com/mcp \
            -H "Content-Type: application/json" \
            -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
            -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
            -d '{
              "jsonrpc": "2.0",
              "id": 1,
              "method": "tools/call",
              "params": {
                "name": "allocate_port",
                "arguments": {
                  "project": "'"$GITHUB_REPOSITORY"'",
                  "service": "production"
                }
              }
            }'
```

---

## 故障排除

### 問題 1: 連線被拒絕 (403 Forbidden)

**原因**: Cloudflare Access 驗證失敗

**解決方法**:
1. 檢查 Service Token 是否正確
2. 確認 Access Policy 包含你的 Service Token
3. 驗證 headers 格式正確

```bash
# 測試 Service Token
curl -I https://infra.your-domain.com/health \
  -H "CF-Access-Client-Id: YOUR_ID" \
  -H "CF-Access-Client-Secret: YOUR_SECRET"

# 應該返回 200，不是 302 或 403
```

### 問題 2: 工具呼叫失敗

**原因**: MCP 請求格式錯誤

**解決方法**:
檢查 JSON-RPC 格式：
```json
{
  "jsonrpc": "2.0",         // 必須是 "2.0"
  "id": 1,                  // 任意數字
  "method": "tools/call",   // 固定為 "tools/call"
  "params": {
    "name": "tool_name",    // 工具名稱
    "arguments": {          // 工具參數
      // ...
    }
  }
}
```

### 問題 3: Claude Desktop 看不到 MCP Server

**原因**: 配置檔格式錯誤或位置不對

**解決方法**:
1. 確認配置檔位置正確
2. 檢查 JSON 格式（使用 JSONLint.com 驗證）
3. 重啟 Claude Desktop
4. 查看 Claude Desktop logs

```bash
# macOS 查看 logs
~/Library/Logs/Claude/

# 檢查是否有 MCP 相關錯誤
```

### 問題 4: Port 衝突

**原因**: 請求的 port 已被其他專案使用

**解決方法**:
1. 不指定 preferred_port，讓系統自動分配
2. 使用 list_resources 查看已分配的 ports
3. 選擇其他未使用的 port

### 問題 5: 無法建立 Tunnel

**原因**: Hostname 已存在或 Cloudflare 配置問題

**解決方法**:
1. 使用 list_resources 查看已註冊的 tunnels
2. 選擇不同的 hostname
3. 檢查 Cloudflare DNS 設定

---

## 安全最佳實踐

### 1. 保護 Service Token

```bash
# 使用環境變數，不要寫死在程式碼中
export CF_ACCESS_CLIENT_ID="..."
export CF_ACCESS_CLIENT_SECRET="..."

# 或使用 .env 檔案（加入 .gitignore）
echo "CF_ACCESS_CLIENT_ID=..." >> .env
echo "CF_ACCESS_CLIENT_SECRET=..." >> .env

# 在程式中讀取
from dotenv import load_dotenv
load_dotenv()
```

### 2. 定期輪換 Token

- 每 3-6 個月更新 Service Token
- 建立新 token 後，先測試再刪除舊的
- 記錄 token 的建立日期和用途

### 3. 最小權限原則

- 不同專案使用不同的 Service Token
- 在 Access Policy 中限制 token 的權限範圍
- 監控 token 使用情況

---

## 支援

如有問題，請：
1. 查看此文檔的故障排除章節
2. 檢查 [MCP Server logs](https://infra.your-domain.com/health)
3. 聯繫專案維護者

---

**最後更新**: 2025-12-28
**版本**: v1.0
