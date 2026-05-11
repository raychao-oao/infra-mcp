#!/bin/bash
set -e

# Deployment script for Infrastructure MCP Server to asablue
# Usage: ./deploy/deploy.sh

SERVER="asablue"
REMOTE_DIR="/home/jcchao/PRJ/oao-infra"
PROJECT_NAME="oao-infra"

echo "🚀 Deploying Infrastructure MCP Server to $SERVER"
echo "================================================"

# Step 1: Create remote directory
echo ""
echo "📁 Step 1: Creating remote directory..."
ssh $SERVER "mkdir -p $REMOTE_DIR/configs $REMOTE_DIR/deploy"

# Step 2: Sync project files
echo ""
echo "📤 Step 2: Syncing project files..."
rsync -avz --exclude 'venv' \
           --exclude '.git' \
           --exclude '__pycache__' \
           --exclude '*.pyc' \
           --exclude '.env' \
           --exclude 'configs/resources.db' \
           --exclude 'server.log' \
           --exclude '.DS_Store' \
           ./ $SERVER:$REMOTE_DIR/

# Step 3: Set up Python environment
echo ""
echo "🐍 Step 3: Setting up Python environment on remote server..."
ssh $SERVER "cd $REMOTE_DIR && python3 -m venv venv"

# Step 4: Install dependencies
echo ""
echo "📦 Step 4: Installing dependencies..."
ssh $SERVER "cd $REMOTE_DIR && venv/bin/pip install --upgrade pip && venv/bin/pip install -r requirements.txt"

# Step 5: Create .env file (if not exists)
echo ""
echo "⚙️  Step 5: Setting up environment variables..."
ssh $SERVER "cd $REMOTE_DIR && if [ ! -f .env ]; then cp .env.example .env; echo '⚠️  Please edit .env file with production credentials'; fi"

# Step 6: Set up systemd service
echo ""
echo "🔧 Step 6: Setting up systemd service..."
ssh $SERVER "sudo cp $REMOTE_DIR/deploy/infra-mcp.service /etc/systemd/system/ && sudo systemctl daemon-reload"

# Step 7: Database initialization (if needed)
echo ""
echo "🗄️  Step 7: Initializing database..."
ssh $SERVER "cd $REMOTE_DIR && mkdir -p configs"

# Step 8: Restart service
echo ""
echo "🔄 Step 8: Restarting infra-mcp service..."
ssh $SERVER "sudo systemctl restart infra-mcp"

# Step 9: Verify
echo ""
echo "✅ Step 9: Verifying service status..."
ssh $SERVER "systemctl is-active infra-mcp"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 First-time setup (if needed):"
echo "1. SSH to server: ssh $SERVER"
echo "2. Edit .env file: cd $REMOTE_DIR && nano .env"
echo "3. Enable service: sudo systemctl enable infra-mcp"
echo "4. View logs: sudo journalctl -u infra-mcp -f"
echo ""
echo "🌐 Cloudflare Tunnel setup:"
echo "1. Create tunnel: cloudflared tunnel create infra-mcp"
echo "2. Update deploy/cloudflared-config-infra-mcp.yml with tunnel ID"
echo "3. Copy config: cp deploy/cloudflared-config-infra-mcp.yml ~/.cloudflared/config-infra-mcp.yml"
echo "4. Configure DNS: cloudflared tunnel route dns infra-mcp infra.nowhere.tw"
echo "5. Start tunnel: Use vps-tunnel-management skill"
echo ""
echo "🔒 Caddy setup:"
echo "1. Copy Caddyfile: sudo cp $REMOTE_DIR/deploy/Caddyfile /etc/caddy/Caddyfile"
echo "2. Test config: sudo caddy validate --config /etc/caddy/Caddyfile"
echo "3. Reload Caddy: sudo systemctl reload caddy"
