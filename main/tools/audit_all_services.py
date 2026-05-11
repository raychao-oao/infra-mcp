"""
audit_all_services MCP Tool Implementation

Audit all deployed services' security configuration.
Generates a comprehensive security audit report.
"""

from typing import Optional, Dict, Any, List

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import DeploymentStatus
from main.tools.validate_service_security import validate_service_security


async def audit_all_services(
    store: SQLiteStore,
    server: Optional[str] = None,
    auto_fix: bool = False
) -> Dict[str, Any]:
    """
    Audit all deployed services' security configuration.

    Args:
        store: SQLiteStore instance
        server: Optional VPS server to filter (configured via INFRA_SERVERS)
        auto_fix: Whether to automatically fix issues

    Returns:
        Dict with comprehensive security audit report
    """

    # Validate server if provided
    if server:
        valid_servers = INFRA_SERVERS
        if server not in valid_servers:
            return {
                "success": False,
                "error": "INVALID_SERVER",
                "message": f"Invalid server name. Must be one of: {', '.join(valid_servers)}"
            }

    # Get all deployed services
    try:
        all_services = await store.list_service_deployments()

        # Filter by server if specified
        if server:
            all_services = [s for s in all_services if s.server == server]

        # Filter to only deployed services
        deployed_services = [
            s for s in all_services
            if s.status == DeploymentStatus.DEPLOYED
        ]

        if not deployed_services:
            return {
                "success": True,
                "total_services": 0,
                "deployed_services": 0,
                "secure_services": 0,
                "vulnerable_services": 0,
                "services": [],
                "message": f"No deployed services found{' on ' + server if server else ''}"
            }

        # Audit each service
        audit_results = []
        secure_count = 0
        vulnerable_count = 0
        total_issues = 0
        total_fixed = 0

        for service_deployment in deployed_services:
            project = service_deployment.project
            service = service_deployment.service
            srv = service_deployment.server

            # Run validation
            validation_result = await validate_service_security(
                store=store,
                project=project,
                service=service,
                server=srv,
                auto_fix=auto_fix
            )

            # Count results
            if validation_result.get("security_status") == "SECURE":
                secure_count += 1
            else:
                vulnerable_count += 1
                total_issues += validation_result.get("issues_count", 0)
                if auto_fix:
                    total_fixed += validation_result.get("fixed_count", 0)

            # Add to results
            audit_results.append({
                "project": project,
                "service": service,
                "server": srv,
                "service_type": validation_result.get("service_type"),
                "security_status": validation_result.get("security_status"),
                "issues_count": validation_result.get("issues_count", 0),
                "issues": validation_result.get("issues", []),
                "fixed_count": validation_result.get("fixed_count", 0) if auto_fix else None
            })

        # Build summary
        summary = {
            "total_services": len(deployed_services),
            "secure_services": secure_count,
            "vulnerable_services": vulnerable_count,
            "total_issues": total_issues,
            "security_score": round((secure_count / len(deployed_services)) * 100, 1) if deployed_services else 0
        }

        if auto_fix:
            summary["total_fixed"] = total_fixed
            summary["remaining_issues"] = total_issues - total_fixed

        # Group by server
        by_server = {}
        for result in audit_results:
            srv = result["server"]
            if srv not in by_server:
                by_server[srv] = {
                    "total": 0,
                    "secure": 0,
                    "vulnerable": 0
                }
            by_server[srv]["total"] += 1
            if result["security_status"] == "SECURE":
                by_server[srv]["secure"] += 1
            else:
                by_server[srv]["vulnerable"] += 1

        # Build message
        if vulnerable_count == 0:
            message = f"✅ All {len(deployed_services)} service(s) are secure"
        else:
            message = f"⚠️ Found {vulnerable_count} vulnerable service(s) with {total_issues} issue(s)"
            if auto_fix and total_fixed > 0:
                message += f" ({total_fixed} fixed, {total_issues - total_fixed} remaining)"

        return {
            "success": True,
            "summary": summary,
            "by_server": by_server,
            "services": audit_results,
            "auto_fix_enabled": auto_fix,
            "message": message
        }

    except Exception as e:
        return {
            "success": False,
            "error": "AUDIT_FAILED",
            "message": f"Failed to audit services: {str(e)}"
        }


async def validate_audit_all_services_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for audit_all_services tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    if "server" in data:
        if not isinstance(data["server"], str):
            return False, "Field 'server' must be a string"

        valid_servers = INFRA_SERVERS
        if data["server"] not in valid_servers:
            return False, f"Invalid server. Must be one of: {', '.join(valid_servers)}"

    if "auto_fix" in data:
        if not isinstance(data["auto_fix"], bool):
            return False, "Field 'auto_fix' must be a boolean"

    return True, None
