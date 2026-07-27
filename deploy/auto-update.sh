#!/usr/bin/env bash
#
# Pull-based auto-deploy for infra-mcp.
#
# Pull, not push: a webhook or a CI runner would need something to reach in from
# outside — an inbound endpoint, or a deploy key handed to a third party. This
# server exists partly to stop that sort of thing, so it polls instead. Nothing
# listens, nothing outside holds a credential.
#
# Refuses to leave the service broken: if the new revision does not come up
# healthy, it rolls back to the previous one and restarts. A bad push costs a
# few seconds of downtime, not an outage that waits for someone to notice.
#
# Installed as infra-mcp-update.timer. Run by hand to deploy immediately.

set -euo pipefail

REPO="${INFRA_MCP_REPO:-/home/jcchao/PRJ/infra-mcp}"
SERVICE="${INFRA_MCP_SERVICE:-infra-mcp}"
HEALTH_URL="${INFRA_MCP_HEALTH_URL:-http://127.0.0.1:8000/health}"
HEALTH_RETRIES=10
HEALTH_INTERVAL=2

cd "$REPO"

log() { echo "[auto-update] $*"; }

wait_for_health() {
    for _ in $(seq 1 "$HEALTH_RETRIES"); do
        sleep "$HEALTH_INTERVAL"
        if curl -fsS --max-time 3 "$HEALTH_URL" 2>/dev/null | grep -q '"status":"healthy"'; then
            return 0
        fi
    done
    return 1
}

git fetch --quiet origin main

local_rev=$(git rev-parse HEAD)
remote_rev=$(git rev-parse origin/main)

if [ "$local_rev" = "$remote_rev" ]; then
    exit 0
fi

log "updating ${local_rev:0:7} -> ${remote_rev:0:7}"
git log --oneline "$local_rev..$remote_rev" | sed 's/^/[auto-update]   /'

# .env and configs/ are gitignored, so reset cannot touch credentials or the
# database. Verified before this script was written; do not add them to git.
git reset --hard --quiet "$remote_rev"

deps_changed=false
if ! git diff --quiet "$local_rev" "$remote_rev" -- requirements.txt; then
    log "requirements.txt changed, installing"
    ./venv/bin/pip install -q -r requirements.txt
    deps_changed=true
fi

# A docs-only commit does not justify dropping every in-flight request.
if ! $deps_changed && git diff --quiet "$local_rev" "$remote_rev" -- ':!docs' ':!*.md'; then
    log "documentation only, not restarting"
    exit 0
fi

sudo systemctl restart "$SERVICE"

if wait_for_health; then
    log "healthy at ${remote_rev:0:7}"
    exit 0
fi

log "ERROR: ${remote_rev:0:7} did not become healthy, rolling back to ${local_rev:0:7}"
git reset --hard --quiet "$local_rev"
if $deps_changed; then
    ./venv/bin/pip install -q -r requirements.txt
fi
sudo systemctl restart "$SERVICE"

if wait_for_health; then
    log "rolled back to ${local_rev:0:7}, service healthy"
else
    log "CRITICAL: rollback did not become healthy either — needs a human"
fi
exit 1
