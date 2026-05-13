# Security Configuration Templates

These templates provide secure configuration examples following Zero Trust architecture.

## Core Principle

**All services must bind to 127.0.0.1 (localhost) and are only accessible externally through Cloudflare Tunnel.**

## Template List

### 1. docker-compose.secure.yml

Secure Docker Compose configuration template.

**Key configuration**:
```yaml
ports:
  - "127.0.0.1:${APP_PORT}:${APP_PORT}"
```

**Usage**:
```bash
# Copy the template
cp templates/docker-compose.secure.yml ~/PRJ/your-project/docker-compose.yml

# Set variables
export PROJECT="your-project"
export SERVICE="your-service"
export APP_PORT="8080"

# Substitute variables (optional)
envsubst < docker-compose.yml > docker-compose.tmp
mv docker-compose.tmp docker-compose.yml

# Start the service
docker compose up -d
```

### 2. Caddyfile.secure

Secure Caddy configuration template.

**Key configuration**:
```caddyfile
your-domain.com:80 {
    bind 127.0.0.1
    reverse_proxy localhost:8080
}
```

**Usage**:
```bash
# Copy the template
sudo cp templates/Caddyfile.secure /etc/caddy/sites/your-project-your-service.caddy

# Edit the configuration
sudo nano /etc/caddy/sites/your-project-your-service.caddy

# Validate configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# Restart Caddy
sudo systemctl restart caddy
```

### 3. systemd.secure.service

Secure systemd service configuration template.

**Key configuration**:
```ini
Environment="HOST=127.0.0.1"
Environment="PORT=8080"
ExecStart=... --bind 127.0.0.1:8080 ...
```

**Usage**:
```bash
# Copy the template
sudo cp templates/systemd.secure.service /etc/systemd/system/your-project-your-service.service

# Edit the configuration
sudo nano /etc/systemd/system/your-project-your-service.service

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable your-project-your-service
sudo systemctl start your-project-your-service

# Check status
sudo systemctl status your-project-your-service
```

## Variable Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `${PROJECT}` | Project name | `PAC`, `tcm-go` |
| `${SERVICE}` | Service name | `dashboard`, `api` |
| `${HOSTNAME}` | Public hostname | `myapp.your-domain.com` |
| `${APP_PORT}` | Application port | `8080`, `5000` |

## Security Checklist

Before deploying, verify:

- [ ] Docker ports use `127.0.0.1:port:port` format
- [ ] Caddy configuration includes `bind 127.0.0.1`
- [ ] systemd environment variable `HOST=127.0.0.1`
- [ ] Application binds to `127.0.0.1`, not `0.0.0.0`
- [ ] UFW firewall only allows SSH (port 22)
- [ ] Service is accessible externally through Cloudflare Tunnel

## Verifying Your Deployment

Use Infrastructure MCP tools to verify:

```bash
# 1. Validate service security configuration
validate_service_security(project="...", service="...", server="...")

# 2. Check listening ports
check_listening_ports(server="...")

# 3. Test service health
check_service_health(server="...", project="...", service="...")
```

## Common Mistakes

### Mistake 1: Port Exposed Publicly

**Problem**:
```yaml
ports:
  - "8080:8080"  # ❌ Wrong
```

**Fix**:
```yaml
ports:
  - "127.0.0.1:8080:8080"  # ✅ Correct
```

### Mistake 2: Caddy Missing bind Directive

**Problem**:
```caddyfile
example.com:80 {
    reverse_proxy localhost:8080  # ❌ Missing bind
}
```

**Fix**:
```caddyfile
example.com:80 {
    bind 127.0.0.1  # ✅ Required
    reverse_proxy localhost:8080
}
```

### Mistake 3: Wrong Environment Variable Binding

**Problem**:
```ini
Environment="HOST=0.0.0.0"  # ❌ Wrong
```

**Fix**:
```ini
Environment="HOST=127.0.0.1"  # ✅ Correct
```

## References

- [Infrastructure MCP Security Tools Guide](../docs/security-tools-guide.md)
- [Zero Trust Architecture](https://www.cloudflare.com/learning/security/glossary/what-is-zero-trust/)

---

**Version**: 1.0
**Last updated**: 2026-01-28
