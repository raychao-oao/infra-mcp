# Infrastructure Data Models

**文檔版本**: v1.0
**最後更新**: 2025-12-28
**狀態**: Design Phase

---

## 📖 Overview

本文檔定義 Infrastructure MCP Server 使用的所有資料模型，包括資源分配記錄、伺服器配置、Tunnel 註冊等。

### Storage Strategy

**Phase 1**: JSON 檔案
- 路徑: `configs/resources.json`
- 優點: 簡單、無需資料庫設置
- 缺點: 不支援並發寫入、無法處理大量資料

**Phase 2**: SQLite
- 優點: 關聯查詢、ACID 保證、更好的效能
- Migration path: 提供 JSON → SQLite 轉換工具

**Phase 3**: PostgreSQL
- 當需要支援多用戶、遠端存取時

---

## 🗂️ Core Data Models

### 1. Port Allocation

```json
{
  "allocation_id": "alloc_20251228_120530_001",
  "resource_type": "port",
  "port": 3000,
  "project": "my-app",
  "service": "web-server",
  "server": "prod",
  "allocated_at": "2025-12-28T12:05:30Z",
  "allocated_by": "claude-code",
  "status": "in-use",
  "notes": "Main Flask application server",
  "metadata": {
    "requested_port": 3000,
    "was_preferred": true
  }
}
```

**欄位說明**:
- `allocation_id`: 唯一識別碼，格式 `alloc_YYYYMMDD_HHMMSS_NNN`
- `resource_type`: 固定值 `"port"`
- `port`: 分配的 port 號碼 (3000-9999)
- `project`: 專案名稱（小寫、連字號）
- `service`: 服務名稱（該專案內的服務標識）
- `server`: 使用此 port 的 VPS 伺服器
- `allocated_at`: ISO 8601 timestamp
- `allocated_by`: 分配來源（`claude-code`, `manual`, `api`）
- `status`: 狀態值
  - `allocated`: 剛分配，尚未使用
  - `in-use`: 正在使用中
  - `reserved`: 保留（暫不使用但不釋放）
  - `released`: 已釋放（可回收）
- `notes`: 選填備註
- `metadata`: 額外資訊

**Indexes** (Phase 2 SQLite):
```sql
CREATE INDEX idx_port_number ON port_allocations(port);
CREATE INDEX idx_project ON port_allocations(project);
CREATE INDEX idx_status ON port_allocations(status);
```

### 2. Tunnel Registration

```json
{
  "tunnel_id": "tunnel_20251228_120600_001",
  "tunnel_name": "my-app",
  "cloudflare_tunnel_id": "abc123-def456-789ghi-jklmno",
  "project": "my-app",
  "hostname": "my-app.your-domain.com",
  "domain": "your-domain.com",
  "subdomain": "my-app",
  "target_service": "http://localhost:3000",
  "target_port": 3000,
  "vps_server": "prod",
  "config_path": "/home/your_user/.cloudflared/config-my-app.yml",
  "credentials_file": "/home/your_user/.cloudflared/abc123-def456.json",
  "systemd_service": "cloudflared-my-app.service",
  "registered_at": "2025-12-28T12:06:00Z",
  "registered_by": "claude-code",
  "status": "active",
  "dns_record": {
    "type": "CNAME",
    "name": "my-app",
    "target": "abc123-def456.cfargotunnel.com",
    "proxied": true,
    "cloudflare_zone_id": "zone123",
    "cloudflare_record_id": "record456",
    "configured_at": "2025-12-28T12:06:15Z"
  },
  "deployment": {
    "deployed_at": "2025-12-28T12:06:30Z",
    "service_enabled": true,
    "service_active": true,
    "last_checked": "2025-12-28T14:30:00Z"
  },
  "metadata": {
    "ingress_rules": [
      {
        "hostname": "my-app.your-domain.com",
        "service": "http://localhost:3000"
      }
    ]
  }
}
```

**欄位說明**:
- `tunnel_id`: 內部唯一識別碼
- `tunnel_name`: Tunnel 名稱（用於 config 檔名和 systemd service）
- `cloudflare_tunnel_id`: Cloudflare 生成的 UUID
- `hostname`: 完整 hostname
- `domain`: 頂級 domain（從 hostname 提取）
- `subdomain`: 子域名（從 hostname 提取）
- `target_service`: Tunnel 轉發目標（URL 格式）
- `target_port`: 目標 port（必須已透過 allocate_port 分配）
- `vps_server`: 部署此 tunnel 的 VPS
- `status`: 狀態值
  - `registered`: 已註冊，尚未部署
  - `active`: 已部署且正在運行
  - `inactive`: 已部署但未運行
  - `failed`: 部署失敗或運行異常
  - `decommissioned`: 已下線
- `dns_record`: DNS 配置資訊
- `deployment`: 部署狀態資訊

**Constraints**:
- `hostname` 必須唯一
- `tunnel_name` 必須唯一（per server）
- `target_port` 必須存在於 port_allocations 且屬於同一 project

### 3. VPS Deployment

```json
{
  "deployment_id": "deploy_20251228_120630_001",
  "project": "my-app",
  "server": "prod",
  "deployment_type": "flask_app",
  "source_info": {
    "local_path": "/Users/your_user/PROJECTS/my-app",
    "repository": "https://github.com/user/my-app.git",
    "branch": "main",
    "commit": "abc123def"
  },
  "target_info": {
    "remote_path": "/home/your_user/apps/my-app",
    "user": "your_user",
    "virtualenv": "/home/your_user/apps/my-app/venv"
  },
  "service": {
    "name": "my-app-web.service",
    "type": "systemd",
    "port": 3000,
    "enabled_on_boot": true,
    "restart_policy": "always"
  },
  "environment": {
    "FLASK_ENV": "production",
    "DATABASE_URL": "sqlite:///app.db",
    "PORT": "3000"
  },
  "deployed_at": "2025-12-28T12:06:30Z",
  "deployed_by": "claude-code",
  "status": "running",
  "health": {
    "last_checked": "2025-12-28T14:30:00Z",
    "uptime": "2h 24m",
    "memory_usage": "156MB",
    "cpu_usage": "2.3%"
  },
  "tunnel": {
    "tunnel_id": "tunnel_20251228_120600_001",
    "tunnel_name": "my-app",
    "service_name": "cloudflared-my-app.service"
  },
  "metadata": {
    "deployment_method": "rsync",
    "deployment_duration": "52.1s",
    "files_transferred": 234
  }
}
```

**欄位說明**:
- `deployment_id`: 唯一識別碼
- `deployment_type`: 部署類型
  - `flask_app`: Python Flask 應用
  - `nodejs_app`: Node.js 應用
  - `static_site`: 靜態網站
  - `docker_container`: Docker 容器（Phase 2）
- `status`: 部署狀態
  - `deploying`: 部署中
  - `running`: 正常運行
  - `stopped`: 已停止
  - `failed`: 失敗
  - `updating`: 更新中
- `health`: 健康狀態資訊（未來透過監控服務獲取）

### 4. VPS Server Configuration

儲存位置: `configs/servers.yml`

```yaml
servers:
  prod:
    # 基本資訊
    hostname: prod.your-domain.com
    ip: YOUR_SERVER_IP
    location: Germany
    provider: Netcup
    plan: RS 1000 G12

    # 硬體規格
    specs:
      cpu: AMD EPYC 9645 (4 dedicated cores)
      ram: 7.8GB ECC
      disk: 256GB NVMe
      network: 1Gbps

    # 系統資訊
    os: Debian 13 (trixie)
    kernel: 6.x

    # SSH 連線設定
    ssh:
      user: your_user
      port: 22
      key_path: ~/.ssh/id_ed25519
      has_nopasswd_sudo: true

    # 能力清單
    capabilities:
      - flask_app
      - nodejs_app
      - static_site
      - cloudflared_tunnel
      - docker  # Phase 2

    # Port 範圍
    port_range:
      start: 3000
      end: 9999

    # 路徑配置
    paths:
      apps: /home/your_user/apps
      cloudflared: /home/your_user/.cloudflared
      systemd: /etc/systemd/system
      logs: /var/log

    # 預裝軟體
    installed_software:
      python: 3.13.5
      pip: 24.x
      caddy: 2.10.2
      cloudflared: v2025.11.1
      git: 2.x

    # 狀態
    status: active
    last_health_check: 2025-12-28T14:30:00Z

    # 成本資訊（選填）
    cost:
      monthly: 11.99
      currency: EUR
      billing_cycle: monthly
```

**多伺服器範例**:
```yaml
servers:
  prod:
    # ... 如上

  greenserver:
    hostname: green.your-domain.com
    ip: 123.456.789.012
    location: Singapore
    provider: DigitalOcean
    plan: Droplet Premium
    # ... 其他欄位
    status: active

  stagingserver:
    hostname: staging.your-domain.com
    # ...
    status: maintenance
```

### 5. Cloudflare Configuration

儲存位置: `configs/cloudflare.yml`

```yaml
cloudflare:
  accounts:
    primary:
      email: your@email.com
      api_token: ${CLOUDFLARE_API_TOKEN}
      account_id: cf_account_123

      zones:
        - zone_id: zone_domain_123
          domain: your-domain.com
          nameservers:
            - dana.ns.cloudflare.com
            - tom.ns.cloudflare.com

      tunnels:
        - tunnel_id: 0a1a62fb-0ad5-4f6a-9e8c-f0129fcbaf92
          tunnel_name: pac
          credentials_file: ~/.cloudflared/0a1a62fb-0ad5-4f6a-9e8c-f0129fcbaf92.json
          created_at: 2024-12-15

        - tunnel_id: 5871ec4d-ace8-4173-b8c1-2216464780c9
          tunnel_name: sandbox
          credentials_file: ~/.cloudflared/5871ec4d-ace8-4173-b8c1-2216464780c9.json
          created_at: 2024-12-15

  # 可用的 domains（供 MCP tools 驗證）
  allowed_domains:
    - your-domain.com

  # DNS 記錄模板
  dns_templates:
    tunnel_cname:
      type: CNAME
      proxied: true
      ttl: 1  # Auto (Cloudflare managed)
```

---

## 🔄 Data Relationships

```
┌─────────────────┐
│ Port Allocation │
└────────┬────────┘
         │ 1
         │
         │ referenced by
         │
         ▼ 1
┌─────────────────────┐       ┌─────────────────┐
│ Tunnel Registration │ 1───1 │ VPS Deployment  │
└──────────┬──────────┘       └────────┬────────┘
           │ N                          │ N
           │                            │
           │                            │
           ▼ 1                          ▼ 1
     ┌──────────┐               ┌──────────┐
     │  Domain  │               │   VPS    │
     │  (YAML)  │               │ (YAML)   │
     └──────────┘               └──────────┘
```

**關聯說明**:
1. Tunnel Registration 必須引用一個已分配的 Port
2. VPS Deployment 可選關聯一個 Tunnel（如果該部署需要 tunnel）
3. 所有 Tunnel 必須使用 allowed_domains 中的 domain
4. 所有 Deployment 必須部署到已註冊的 VPS

---

## 📊 Database Schema (Phase 2 - SQLite)

### Table: port_allocations

```sql
CREATE TABLE port_allocations (
    allocation_id TEXT PRIMARY KEY,
    port INTEGER NOT NULL,
    project TEXT NOT NULL,
    service TEXT NOT NULL,
    server TEXT NOT NULL,
    allocated_at TIMESTAMP NOT NULL,
    allocated_by TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    metadata JSON,

    UNIQUE(port, server),
    FOREIGN KEY (server) REFERENCES servers(server_name)
);

CREATE INDEX idx_port ON port_allocations(port);
CREATE INDEX idx_project ON port_allocations(project);
CREATE INDEX idx_status ON port_allocations(status);
```

### Table: tunnel_registrations

```sql
CREATE TABLE tunnel_registrations (
    tunnel_id TEXT PRIMARY KEY,
    tunnel_name TEXT NOT NULL,
    cloudflare_tunnel_id TEXT NOT NULL,
    project TEXT NOT NULL,
    hostname TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    subdomain TEXT NOT NULL,
    target_port INTEGER NOT NULL,
    vps_server TEXT NOT NULL,
    registered_at TIMESTAMP NOT NULL,
    registered_by TEXT NOT NULL,
    status TEXT NOT NULL,
    dns_record JSON,
    deployment JSON,
    metadata JSON,

    FOREIGN KEY (target_port, vps_server)
        REFERENCES port_allocations(port, server),
    FOREIGN KEY (vps_server) REFERENCES servers(server_name)
);

CREATE INDEX idx_hostname ON tunnel_registrations(hostname);
CREATE INDEX idx_project_tunnel ON tunnel_registrations(project);
CREATE INDEX idx_server_tunnel ON tunnel_registrations(vps_server);
```

### Table: vps_deployments

```sql
CREATE TABLE vps_deployments (
    deployment_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    server TEXT NOT NULL,
    deployment_type TEXT NOT NULL,
    deployed_at TIMESTAMP NOT NULL,
    deployed_by TEXT NOT NULL,
    status TEXT NOT NULL,
    source_info JSON,
    target_info JSON,
    service JSON,
    environment JSON,
    health JSON,
    tunnel_id TEXT,
    metadata JSON,

    FOREIGN KEY (server) REFERENCES servers(server_name),
    FOREIGN KEY (tunnel_id) REFERENCES tunnel_registrations(tunnel_id)
);

CREATE INDEX idx_project_deploy ON vps_deployments(project);
CREATE INDEX idx_server_deploy ON vps_deployments(server);
CREATE INDEX idx_status_deploy ON vps_deployments(status);
```

### Table: servers

```sql
CREATE TABLE servers (
    server_name TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    ip TEXT NOT NULL,
    location TEXT,
    provider TEXT,
    config JSON NOT NULL,
    status TEXT NOT NULL,
    last_health_check TIMESTAMP
);
```

---

## 🔐 Data Validation Rules

### Port Number Validation

```python
def validate_port(port: int) -> bool:
    """驗證 port 號碼是否有效"""
    return 3000 <= port <= 9999

def is_port_available(port: int, server: str) -> bool:
    """檢查 port 在特定伺服器上是否可用"""
    allocations = load_port_allocations()
    return not any(
        a['port'] == port
        and a['server'] == server
        and a['status'] != 'released'
        for a in allocations
    )
```

### Hostname Validation

```python
def validate_hostname(hostname: str) -> bool:
    """驗證 hostname 格式和 domain"""
    import re
    pattern = r'^[a-z0-9-]+\.your-domain\.com$'
    return bool(re.match(pattern, hostname))

def is_hostname_available(hostname: str) -> bool:
    """檢查 hostname 是否已被使用"""
    tunnels = load_tunnel_registrations()
    return not any(
        t['hostname'] == hostname
        and t['status'] != 'decommissioned'
        for t in tunnels
    )
```

### Project Name Validation

```python
def validate_project_name(name: str) -> bool:
    """驗證專案名稱格式"""
    import re
    pattern = r'^[a-z0-9-]+$'
    return bool(re.match(pattern, name)) and len(name) >= 2
```

---

## 📝 Migration Plan (JSON → SQLite)

### Step 1: Schema Creation

```python
# main/db/migrate.py
def create_schema(conn):
    """建立 SQLite schema"""
    conn.executescript(open('schema.sql').read())
```

### Step 2: Data Migration

```python
def migrate_from_json(json_path: str, db_path: str):
    """從 JSON 遷移到 SQLite"""
    import json
    import sqlite3

    # 讀取 JSON
    with open(json_path) as f:
        data = json.load(f)

    # 連接 SQLite
    conn = sqlite3.connect(db_path)

    # 遷移 port allocations
    for alloc in data['port_allocations']:
        conn.execute('''
            INSERT INTO port_allocations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            alloc['allocation_id'],
            alloc['port'],
            alloc['project'],
            alloc['service'],
            alloc['server'],
            alloc['allocated_at'],
            alloc['allocated_by'],
            alloc['status'],
            alloc.get('notes'),
            json.dumps(alloc.get('metadata', {}))
        ))

    # 遷移其他資料...

    conn.commit()
```

### Step 3: Backward Compatibility

在 Phase 2 實作時，提供：
- 自動偵測 JSON/SQLite
- JSON → SQLite 單向同步工具
- 回退機制（如果 SQLite 有問題）

---

## 📚 Example Queries (SQLite)

### 查詢專案使用的所有資源

```sql
-- 查詢 my-app 專案的所有資源
SELECT
    'port' as resource_type,
    pa.port as resource_value,
    pa.service,
    pa.status
FROM port_allocations pa
WHERE pa.project = 'my-app'

UNION ALL

SELECT
    'tunnel' as resource_type,
    tr.hostname as resource_value,
    tr.tunnel_name as service,
    tr.status
FROM tunnel_registrations tr
WHERE tr.project = 'my-app'

UNION ALL

SELECT
    'deployment' as resource_type,
    vd.server as resource_value,
    json_extract(vd.service, '$.name') as service,
    vd.status
FROM vps_deployments vd
WHERE vd.project = 'my-app';
```

### 統計各伺服器資源使用

```sql
SELECT
    s.server_name,
    s.hostname,
    COUNT(DISTINCT pa.port) as ports_allocated,
    COUNT(DISTINCT tr.tunnel_id) as tunnels_active,
    COUNT(DISTINCT vd.deployment_id) as deployments_running
FROM servers s
LEFT JOIN port_allocations pa ON pa.server = s.server_name AND pa.status = 'in-use'
LEFT JOIN tunnel_registrations tr ON tr.vps_server = s.server_name AND tr.status = 'active'
LEFT JOIN vps_deployments vd ON vd.server = s.server_name AND vd.status = 'running'
GROUP BY s.server_name;
```

### 找出可回收的資源

```sql
-- 找出已分配但超過 30 天未使用的 ports
SELECT
    pa.port,
    pa.project,
    pa.service,
    pa.allocated_at,
    julianday('now') - julianday(pa.allocated_at) as days_since_allocation
FROM port_allocations pa
LEFT JOIN vps_deployments vd ON vd.project = pa.project
    AND json_extract(vd.service, '$.port') = pa.port
WHERE pa.status = 'allocated'
    AND vd.deployment_id IS NULL
    AND julianday('now') - julianday(pa.allocated_at) > 30;
```

---

**文檔維護**: 隨資料結構演進更新
**下次審查**: Phase 1 實作完成時
**維護責任**: Infrastructure Team
