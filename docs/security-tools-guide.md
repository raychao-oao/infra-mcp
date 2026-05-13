# Infrastructure MCP Security Tools Guide

Infrastructure MCP Server provides a complete set of security audit and operations tools for managing and monitoring VPS service security configurations.

## Security Audit Tools

### 1. check_listening_ports

Checks all listening ports on a VPS and identifies security risks — ports not bound to 127.0.0.1.

**Use cases**:
- Discover publicly exposed service ports
- Verify Zero Trust architecture compliance
- Regular security audits

**Example**:
```json
{
  "server": "staging"
}
```

**Response fields**:
- `summary`: Port statistics (total, localhost-only, potential risks)
- `all_ports`: List of all listening ports
- `security_risks`: Details of risky ports

### 2. validate_service_security

Validates a single service's security configuration, including Docker, Caddy, and actual port bindings.

**Use cases**:
- Post-deployment security verification
- Troubleshooting
- Configuration review

**Example**:
```json
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "auto_fix": false
}
```

**What it checks**:
- Whether Caddy configuration has `bind 127.0.0.1`
- Whether Docker port bindings use `127.0.0.1:port:port`
- The HOST environment variable in systemd services
- Actual port binding state

**auto_fix**:
Set `"auto_fix": true` to automatically fix certain issues (e.g., adding Caddy bind directive)

### 3. audit_all_services

Bulk-audits the security configuration of all deployed services and generates a full report.

**Use cases**:
- Comprehensive security audit
- Generating compliance reports
- Bulk security remediation

**Example**:
```json
{
  "server": "prod",
  "auto_fix": false
}
```

**Response fields**:
- `summary`: Overall statistics (total services, secure/vulnerable counts, security score)
- `by_server`: Statistics grouped by VPS
- `services`: Detailed audit results per service

## Configuration Management Tools

### 4. get_caddy_config

Retrieves Caddy configuration file content (main config or service-specific config).

**Use cases**:
- View current configuration
- Troubleshoot routing issues
- Configuration backup

**Example**:
```json
// Get main config
{
  "server": "staging"
}

// Get service-specific config
{
  "server": "staging",
  "project": "tcm-go",
  "service": "poc"
}
```

### 5. get_tunnel_config

Retrieves Cloudflare Tunnel configuration.

**Use cases**:
- View ingress rules
- Confirm tunnel ID
- Diagnose routing issues

**Example**:
```json
{
  "server": "dev2"
}
```

**Response fields**:
- `tunnel_id`: Tunnel UUID
- `credentials_file`: Path to credentials file
- `ingress_rules`: List of routing rules

## Service Restart Tools

### 6. restart_service

Restarts service components (systemd service, Docker container, Caddy, Tunnel).

**Use cases**:
- Apply configuration changes
- Recover failed services
- Complete deployment workflow

**Example**:
```json
// Restart main service
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "component": "service"
}

// Restart Caddy
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "component": "caddy"
}

// Restart Tunnel
{
  "project": "PAC",
  "service": "dashboard",
  "server": "prod",
  "component": "tunnel"
}
```

**component options**:
- `service`: Main service (systemd or Docker)
- `caddy`: Caddy web server
- `tunnel`: Cloudflare Tunnel

## Log Management Tools

### 7. get_service_logs

Retrieves service logs (systemd, Docker, Caddy, Tunnel).

**Use cases**:
- Troubleshooting
- Performance analysis
- Security incident investigation

**Example**:
```json
// Get service logs
{
  "server": "prod",
  "project": "PAC",
  "service": "dashboard",
  "component": "service",
  "lines": 100
}

// Get Caddy logs
{
  "server": "staging",
  "component": "caddy",
  "lines": 50
}

// Get Tunnel logs
{
  "server": "dev2",
  "component": "tunnel",
  "lines": 50
}
```

**Parameters**:
- `lines`: Number of log lines to return (default 50, max 1000)
- `component`: Log source (service/caddy/tunnel)

## Health Check Tools

### 8. check_service_health

Checks service and system health status.

**Use cases**:
- Monitor service status
- System resource monitoring
- Preventive maintenance

**Example**:
```json
// Check a specific service
{
  "server": "prod",
  "project": "PAC",
  "service": "dashboard",
  "include_system_stats": true
}

// Check infrastructure
{
  "server": "staging",
  "include_system_stats": true
}
```

**Response fields**:
- `service_health`: Service status (if specified)
- `infrastructure`: Infrastructure status (Caddy, Tunnel)
- `system_stats`: System resource statistics (memory, disk, load)
- `overall_health`: Overall health status

## Best Practices

### Regular Security Audits

**Recommended frequency**: Once per week

```bash
# 1. Check listening ports on all VPS servers
check_listening_ports(server="prod")
check_listening_ports(server="staging")
check_listening_ports(server="dev1")
check_listening_ports(server="dev2")

# 2. Audit all services
audit_all_services()
```

### Post-Deployment Verification

After deploying a new service or modifying configuration:

```bash
# 1. Validate service security configuration
validate_service_security(
    project="your-project",
    service="your-service",
    server="prod"
)

# 2. Check service health
check_service_health(
    server="prod",
    project="your-project",
    service="your-service"
)

# 3. Check logs to confirm normal startup
get_service_logs(
    server="prod",
    project="your-project",
    service="your-service",
    lines=50
)
```

### Troubleshooting Workflow

When a service has issues:

```bash
# 1. Check health status
check_service_health(server="prod", project="...", service="...")

# 2. View recent logs
get_service_logs(server="prod", project="...", service="...", lines=100)

# 3. Check configuration
get_caddy_config(server="prod", project="...", service="...")

# 4. Validate security configuration
validate_service_security(project="...", service="...", server="prod")

# 5. Restart service if needed
restart_service(project="...", service="...", server="prod")
```

## Security Notes

1. **auto_fix**: Use with caution — run without auto_fix first to confirm the issues, then enable it
2. **Sensitive log data**: Logs may contain sensitive information; handle with care
3. **Restart impact**: Restarting causes brief downtime; choose an appropriate time window
4. **Concurrent operations**: Avoid running multiple operations on the same service simultaneously

## Tool Dependency Map

```
audit_all_services
  └── validate_service_security
        ├── get_caddy_config
        └── check_listening_ports

check_service_health
  └── get_service_logs (optional)

restart_service
  └── check_service_health (recommended after restart)
```

## Troubleshooting Guide

### Issue: check_listening_ports Reports Exposed Ports

**Cause**: Service not bound to 127.0.0.1

**Resolution**:
1. Use `validate_service_security` to identify the specific service
2. Try `auto_fix=true` for automatic remediation
3. Manually update configuration (Docker compose or environment variables)
4. Use `restart_service` to apply the fix

### Issue: audit_all_services Shows Vulnerable Services

**Cause**: Caddy configuration missing bind directive, or Docker ports misconfigured

**Resolution**:
1. Review the detailed `issues` list
2. Use `get_caddy_config` to inspect the configuration
3. Use `auto_fix=true` for bulk remediation
4. Use `restart_service` to apply fixes

### Issue: Service Restart Fails

**Cause**: Configuration error, port conflict, or dependency service not running

**Resolution**:
1. Use `get_service_logs` to view error logs
2. Use `check_service_health` to check dependency services
3. Use `check_listening_ports` to identify port conflicts
4. Fix the issue, then restart again

---

**Document version**: 1.0
**Last updated**: 2026-01-28
**Maintainer**: Infrastructure MCP Team
