# Infrastructure MCP Future Enhancements

本文檔記錄了已規劃但尚未實作的功能增強。

## 1. Enhance deploy_service with Security Validation

### 目標

在 `deploy_service` 工具中整合自動安全驗證，確保每次部署都符合 Zero Trust 架構。

### 實作步驟

#### 步驟 1：在部署前驗證配置

在 `main/tools/deploy_service.py` 中添加預檢查：

```python
async def deploy_service(...):
    # ... 現有代碼

    # 新增：部署前驗證
    if deployment_config.get("validate_security", True):
        # 檢查 docker-compose.yml
        if os.path.exists(docker_compose_path):
            issues = validate_docker_compose_security(docker_compose_path)
            if issues:
                return {
                    "success": False,
                    "error": "SECURITY_VALIDATION_FAILED",
                    "issues": issues,
                    "message": "配置不符合安全要求"
                }

        # 檢查 Caddy 配置
        if caddy_config:
            if "bind 127.0.0.1" not in caddy_config:
                return {
                    "success": False,
                    "error": "CADDY_MISSING_BIND",
                    "message": "Caddy 配置缺少 'bind 127.0.0.1'"
                }

    # ... 繼續部署
```

#### 步驟 2：部署後自動驗證

```python
async def deploy_service(...):
    # ... 執行部署

    # 新增：部署後驗證
    validation_result = await validate_service_security(
        store=store,
        project=project,
        service=service,
        server=server
    )

    if validation_result["security_status"] != "SECURE":
        logger.warning(f"部署的服務有安全問題：{validation_result}")

        # 可選：自動回滾
        if deployment_config.get("rollback_on_security_failure", False):
            await rollback_deployment(...)
            return {
                "success": False,
                "error": "SECURITY_VALIDATION_FAILED",
                "validation": validation_result,
                "message": "部署後安全驗證失敗，已回滾"
            }

    return {
        "success": True,
        "deployment": deployment_info,
        "security_validation": validation_result
    }
```

#### 步驟 3：添加配置選項

在 `register_service` 時允許配置安全驗證選項：

```python
{
    "security_validation": {
        "enabled": True,
        "auto_fix": False,
        "rollback_on_failure": False
    }
}
```

### 測試計畫

```bash
# 測試 1：部署安全的服務（應成功）
deploy_service(project="test", service="secure", ...)

# 測試 2：部署不安全的服務（應失敗）
deploy_service(project="test", service="insecure", ...)

# 測試 3：部署不安全的服務 + auto_fix（應修復並成功）
deploy_service(project="test", service="insecure", auto_fix=True, ...)
```

## 2. Extend Database Schema for Security Tracking

### 目標

在資料庫中追蹤服務的安全驗證歷史和狀態。

### Schema 擴展

#### 方案 A：擴展現有 ServiceDeployment

在 `main/models/service_deployment.py` 添加欄位：

```python
class ServiceDeployment(Base):
    # ... 現有欄位

    # 安全追蹤欄位
    security_validated = Column(Boolean, default=False, nullable=False)
    last_security_check = Column(DateTime, nullable=True)
    security_check_count = Column(Integer, default=0)
    security_issues_history = Column(JSON, nullable=True)  # 歷史問題記錄
    last_security_status = Column(String, nullable=True)  # SECURE/VULNERABLE
```

#### 方案 B：創建獨立的 SecurityAudit 表

創建 `main/models/security_audit.py`：

```python
class SecurityAudit(Base):
    __tablename__ = "security_audits"

    audit_id = Column(String, primary_key=True)
    deployment_id = Column(String, ForeignKey("service_deployments.deployment_id"))

    # 審計資訊
    audit_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    audited_by = Column(String, default="mcp-server")
    audit_type = Column(String)  # manual/automatic/scheduled

    # 結果
    security_status = Column(String)  # SECURE/VULNERABLE
    issues_found = Column(JSON)
    issues_count = Column(Integer)
    auto_fixed = Column(Boolean, default=False)
    fixed_issues = Column(JSON)

    # 檢查詳情
    checks_performed = Column(JSON)  # 執行的檢查列表
```

### 資料庫遷移

```python
# main/db/migrations/add_security_tracking.py

async def upgrade(conn):
    """添加安全追蹤欄位"""

    # 方案 A：修改現有表
    await conn.execute("""
        ALTER TABLE service_deployments
        ADD COLUMN security_validated BOOLEAN DEFAULT 0;
    """)

    await conn.execute("""
        ALTER TABLE service_deployments
        ADD COLUMN last_security_check DATETIME;
    """)

    await conn.execute("""
        ALTER TABLE service_deployments
        ADD COLUMN security_check_count INTEGER DEFAULT 0;
    """)

    await conn.execute("""
        ALTER TABLE service_deployments
        ADD COLUMN security_issues_history TEXT;
    """)

    await conn.execute("""
        ALTER TABLE service_deployments
        ADD COLUMN last_security_status VARCHAR(20);
    """)

    # 方案 B：創建新表
    await conn.execute("""
        CREATE TABLE security_audits (
            audit_id VARCHAR PRIMARY KEY,
            deployment_id VARCHAR,
            audit_time DATETIME NOT NULL,
            audited_by VARCHAR NOT NULL,
            audit_type VARCHAR,
            security_status VARCHAR,
            issues_found TEXT,
            issues_count INTEGER,
            auto_fixed BOOLEAN DEFAULT 0,
            fixed_issues TEXT,
            checks_performed TEXT,
            FOREIGN KEY (deployment_id) REFERENCES service_deployments(deployment_id)
        );
    """)
```

### 更新工具以使用新 Schema

#### 更新 validate_service_security

```python
async def validate_service_security(...):
    # ... 執行驗證

    # 更新資料庫
    deployment.security_validated = (security_status == "SECURE")
    deployment.last_security_check = datetime.utcnow()
    deployment.security_check_count += 1
    deployment.last_security_status = security_status

    # 記錄歷史
    if deployment.security_issues_history:
        history = json.loads(deployment.security_issues_history)
    else:
        history = []

    history.append({
        "timestamp": datetime.utcnow().isoformat(),
        "status": security_status,
        "issues": issues
    })

    # 只保留最近 10 次記錄
    deployment.security_issues_history = json.dumps(history[-10:])

    await store.update_service_deployment(deployment)

    # ... 返回結果
```

#### 創建新的查詢工具

```python
async def get_security_history(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str
) -> Dict[str, Any]:
    """獲取服務的安全驗證歷史"""

    deployment = await store.get_service_deployment(project, service, server)

    if not deployment:
        return {"error": "SERVICE_NOT_FOUND"}

    history = []
    if deployment.security_issues_history:
        history = json.loads(deployment.security_issues_history)

    return {
        "project": project,
        "service": service,
        "server": server,
        "security_validated": deployment.security_validated,
        "last_check": deployment.last_security_check,
        "check_count": deployment.security_check_count,
        "current_status": deployment.last_security_status,
        "history": history
    }
```

### 實作優先級

**方案 A（擴展現有表）**優先，因為：
- 實作簡單
- 不需要處理複雜的表關聯
- 滿足基本需求

如果未來需要更詳細的審計記錄，再考慮**方案 B（獨立審計表）**。

## 3. Additional Future Enhancements

### 3.1 自動定期安全審計

創建一個 cron job 或 systemd timer，定期執行安全審計：

```bash
# /etc/systemd/system/infra-mcp-security-audit.timer
[Unit]
Description=Infrastructure MCP Security Audit Timer

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
```

### 3.2 告警和通知

當發現安全問題時，發送通知：

```python
async def send_security_alert(issues):
    """發送安全告警"""

    # Email
    await send_email(
        to="your@email.com",
        subject="[Security Alert] Infrastructure Issues Detected",
        body=f"Found {len(issues)} security issues"
    )

    # Slack/Discord webhook
    await webhook.send({
        "text": f"⚠️ Security Alert: {len(issues)} issues found"
    })
```

### 3.3 配置模板驗證工具

創建一個工具來驗證模板的正確性：

```python
async def validate_config_template(template_path):
    """驗證配置模板"""

    # 檢查 Docker Compose
    if "docker-compose" in template_path:
        check_docker_compose_template(template_path)

    # 檢查 Caddyfile
    if "Caddyfile" in template_path:
        check_caddyfile_template(template_path)

    return validation_result
```

## 實作時程建議

| 任務 | 優先級 | 預估時間 | 依賴 |
|------|--------|----------|------|
| #9 Enhance deploy_service | 高 | 2-3 小時 | 無 |
| #10 Database schema | 中 | 1-2 小時 | 無 |
| 定期審計 | 低 | 1 小時 | #9, #10 |
| 告警通知 | 低 | 2 小時 | #10 |
| 模板驗證 | 低 | 1 小時 | 無 |

---

**文檔版本**：1.0
**最後更新**：2026-01-28
**狀態**：規劃中
