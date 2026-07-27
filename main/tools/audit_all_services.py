"""
audit_all_services MCP Tool Implementation

Audit all deployed services' security configuration.
Generates a comprehensive security audit report.
"""

from typing import Optional, Dict, Any, List

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import DeploymentStatus
from main.providers.server_snapshot import ServerSnapshot
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

        # Audit every service still on record. This used to keep only those with
        # status == DEPLOYED, which on one host meant 2 of 12 records: the other
        # ten were running but marked REGISTERED, so the audit could not see the
        # six that turned out to be exposed on the public IP. `status` is
        # hand-maintained bookkeeping and drifts from reality — a security audit
        # must not decide what to look at based on it.
        #
        # PURGED is the one exception: those services are gone by definition.
        audited_services = [
            s for s in all_services
            if s.status != DeploymentStatus.PURGED
        ]

        if not audited_services:
            return {
                "success": True,
                "total_services": 0,
                "secure_services": 0,
                "vulnerable_services": 0,
                "services": [],
                "message": f"No services on record{' for ' + server if server else ''}"
            }

        # One snapshot per server, not per service. Each validation would
        # otherwise spend several SSH round trips of its own, which made a full
        # audit take minutes — and a slow audit gets skipped as reliably as a
        # noisy one.
        snapshots = {}
        snapshot_errors = {}
        for srv in sorted({s.server for s in audited_services}):
            try:
                snapshots[srv] = ServerSnapshot.fetch(srv)
            except Exception as e:
                snapshot_errors[srv] = str(e)

        # Audit each service
        audit_results = []
        secure_count = 0
        vulnerable_count = 0
        unverified_count = 0
        total_issues = 0
        total_unverified = 0
        total_fixed = 0
        unreachable = []

        for service_deployment in audited_services:
            project = service_deployment.project
            service = service_deployment.service
            srv = service_deployment.server

            if srv not in snapshots:
                # Report rather than silently drop: an unreachable host is the
                # one case where "no issues found" would be actively misleading.
                unreachable.append({
                    "project": project,
                    "service": service,
                    "server": srv,
                    "error": snapshot_errors.get(srv, "unknown")
                })
                continue

            # Run validation
            validation_result = await validate_service_security(
                store=store,
                project=project,
                service=service,
                server=srv,
                auto_fix=auto_fix,
                snapshot=snapshots[srv]
            )

            # Count results. UNVERIFIED is tracked apart from VULNERABLE: a check
            # that could not run is not a finding, and counting it as one makes
            # the report cry wolf.
            status = validation_result.get("security_status")
            if status == "SECURE":
                secure_count += 1
            elif status == "UNVERIFIED":
                unverified_count += 1
            else:
                vulnerable_count += 1
                total_issues += validation_result.get("issues_count", 0)
                if auto_fix:
                    total_fixed += validation_result.get("fixed_count", 0)
            total_unverified += validation_result.get("unverified_count", 0)

            # Add to results
            audit_results.append({
                "project": project,
                "service": service,
                "server": srv,
                "service_type": validation_result.get("service_type"),
                "security_status": status,
                "issues_count": validation_result.get("issues_count", 0),
                "issues": validation_result.get("issues", []),
                "unverified": validation_result.get("unverified", []),
                "fixed_count": validation_result.get("fixed_count", 0) if auto_fix else None
            })

        # Build summary. The score is over services actually audited — counting
        # ones on an unreachable host would quietly deflate it and read as though
        # they had failed a check.
        audited_count = len(audit_results)
        # Score over services that could actually be judged. Letting UNVERIFIED
        # drag it down would report a records gap as a security regression.
        judged = secure_count + vulnerable_count
        summary = {
            "total_services": len(audited_services),
            "audited_services": audited_count,
            "unreachable_services": len(unreachable),
            "secure_services": secure_count,
            "vulnerable_services": vulnerable_count,
            "unverified_services": unverified_count,
            "total_issues": total_issues,
            "total_unverified_checks": total_unverified,
            "security_score": round((secure_count / judged) * 100, 1) if judged else 0
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
                    "vulnerable": 0,
                    "unverified": 0
                }
            by_server[srv]["total"] += 1
            if result["security_status"] == "SECURE":
                by_server[srv]["secure"] += 1
            elif result["security_status"] == "UNVERIFIED":
                by_server[srv]["unverified"] += 1
            else:
                by_server[srv]["vulnerable"] += 1

        # Build message
        if vulnerable_count == 0:
            message = f"✅ No security issues found in {audited_count} service(s)"
        else:
            message = f"⚠️ Found {vulnerable_count} vulnerable service(s) with {total_issues} issue(s)"
            if auto_fix and total_fixed > 0:
                message += f" ({total_fixed} fixed, {total_issues - total_fixed} remaining)"
        if unverified_count:
            message += f" — {unverified_count} service(s) could not be fully verified"
        if unreachable:
            message += (
                f" — {len(unreachable)} service(s) NOT audited, "
                f"host unreachable: {', '.join(sorted(snapshot_errors))}"
            )

        return {
            "success": True,
            "summary": summary,
            "by_server": by_server,
            "services": audit_results,
            "unreachable": unreachable,
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
