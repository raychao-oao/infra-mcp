#!/usr/bin/env bash
#
# Redeploy Infrastructure MCP Server to asablue
#
# Usage:
#   ./scripts/redeploy.sh          # Redeploy code and restart service
#   ./scripts/redeploy.sh --logs   # Also tail logs after restart
#   ./scripts/redeploy.sh --full   # Full deployment (including dependencies)
#

set -e

# Configuration
SERVER="asablue"
USER="jcchao"
REMOTE_DIR="/home/jcchao/PRJ/oao-infra"
PROJECT_NAME="oao-infra"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse arguments
SHOW_LOGS=false
FULL_DEPLOY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --logs|-l)
            SHOW_LOGS=true
            shift
            ;;
        --full|-f)
            FULL_DEPLOY=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --logs, -l     Tail logs after deployment"
            echo "  --full, -f     Full deployment (install dependencies)"
            echo "  --help, -h     Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Infrastructure MCP Server - Redeployment${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Step 1: Sync code files
echo -e "${YELLOW}📤 Step 1: Syncing code to ${SERVER}...${NC}"
echo ""

rsync -avz --progress \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='configs/resources.db' \
    --exclude='.env' \
    main/ \
    ${USER}@${SERVER}:${REMOTE_DIR}/main/

echo ""
echo -e "${GREEN}✅ Code synced successfully${NC}"
echo ""

# Step 2: Full deployment (dependencies)
if [ "$FULL_DEPLOY" = true ]; then
    echo -e "${YELLOW}📦 Step 2: Installing dependencies...${NC}"
    echo ""

    ssh ${USER}@${SERVER} << 'EOF'
cd /home/jcchao/PRJ/oao-infra
source venv/bin/activate
pip install -r requirements.txt
EOF

    echo ""
    echo -e "${GREEN}✅ Dependencies installed${NC}"
    echo ""
fi

# Step 3: Restart service
echo -e "${YELLOW}🔄 Step 3: Restarting infra-mcp service...${NC}"
echo ""

ssh ${USER}@${SERVER} "sudo systemctl restart infra-mcp"

sleep 2

# Step 4: Check service status
echo -e "${YELLOW}📊 Step 4: Checking service status...${NC}"
echo ""

SERVICE_STATUS=$(ssh ${USER}@${SERVER} "sudo systemctl is-active infra-mcp")

if [ "$SERVICE_STATUS" = "active" ]; then
    echo -e "${GREEN}✅ Service is running${NC}"
    echo ""

    # Show service details
    ssh ${USER}@${SERVER} "sudo systemctl status infra-mcp --no-pager | head -15"

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}Service URL:${NC} https://infra.nowhere.tw"
    echo -e "${BLUE}Health check:${NC} curl -s https://infra.nowhere.tw/health"
    echo ""

    # Test health endpoint
    echo -e "${YELLOW}Testing health endpoint...${NC}"
    HEALTH_RESPONSE=$(curl -s https://infra.nowhere.tw/health \
        -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
        -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")

    if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
        echo -e "${GREEN}✅ Health check passed${NC}"
    else
        echo -e "${RED}⚠️  Health check failed${NC}"
        echo "$HEALTH_RESPONSE"
    fi

    echo ""

    # Show logs if requested
    if [ "$SHOW_LOGS" = true ]; then
        echo -e "${YELLOW}📜 Tailing logs (Ctrl+C to exit)...${NC}"
        echo ""
        ssh ${USER}@${SERVER} "sudo journalctl -u infra-mcp -f"
    else
        echo -e "${BLUE}💡 Tip: Use --logs to tail logs after deployment${NC}"
    fi
else
    echo -e "${RED}❌ Service failed to start${NC}"
    echo ""
    echo -e "${YELLOW}Showing recent logs:${NC}"
    ssh ${USER}@${SERVER} "sudo journalctl -u infra-mcp -n 50 --no-pager"
    exit 1
fi
