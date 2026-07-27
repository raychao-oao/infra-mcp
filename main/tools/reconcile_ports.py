"""
reconcile_ports MCP Tool Implementation

Compare what the port registry believes against what the servers are actually
listening on.

Drift is inevitable — nobody updates the database when they shut a test service
down — and until 2026-07-27 nothing detected it. Finding 13 in-use but
unregistered ports took a manual diff of `ss` output against the table on five
hosts.

The two directions of drift are NOT equally serious:

  listening, not registered   -> warning. is_port_available consults only the
                                 database, so allocate_port will hand this port
                                 to someone else and the collision surfaces at
                                 deploy time.
  listening, but RELEASED     -> warning, and the worst case: the port is
                                 actively serving while being advertised as
                                 free for reuse.
  registered, not listening   -> information, never a finding. A reservation
                                 whose service is stopped is normal: temporary
                                 demos, deliberate shutdowns. Holding a port
                                 costs almost nothing, and warning about it
                                 would train people to ignore this tool.
"""

from typing import Optional, Dict, Any, List

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.port_allocation import AllocationStatus
from main.providers.server_snapshot import ServerSnapshot
from main.tools.allocate_port import PORT_MIN, PORT_MAX
from main.tools.check_listening_ports import _classify_address

# Statuses that mean "this port is spoken for".
_HELD = {AllocationStatus.ALLOCATED, AllocationStatus.IN_USE, AllocationStatus.RESERVED}


async def reconcile_ports(
    store: SQLiteStore,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reconcile the port registry against the ports actually listening.

    Args:
        store: SQLiteStore instance
        server: Optional VPS server to limit the check to

    Returns:
        Dict with per-server findings and a summary
    """

    servers = INFRA_SERVERS
    if server:
        if server not in servers:
            return {
                "success": False,
                "error": "INVALID_SERVER",
                "message": f"Invalid server name. Must be one of: {', '.join(servers)}"
            }
        servers = [server]

    if not servers:
        return {
            "success": False,
            "error": "NO_SERVERS_CONFIGURED",
            "message": "No servers configured — set INFRA_SERVERS"
        }

    try:
        results = {}
        unreachable = {}
        total_warnings = 0

        for srv in servers:
            try:
                snapshot = ServerSnapshot.fetch(srv)
            except Exception as e:
                unreachable[srv] = str(e)
                continue

            listening = _listening_ports(snapshot)

            # Every record for this server, including released ones — a RELEASED
            # row for a port that is serving traffic is exactly what we want to
            # surface, so it must not be filtered out here.
            allocations = await store.list_port_allocations(
                server=srv, include_released=True
            )
            held = {a.port: a for a in allocations if a.status in _HELD}
            released = {
                a.port: a for a in allocations
                if a.status == AllocationStatus.RELEASED and a.port not in held
            }

            unregistered = []
            released_but_listening = []

            for port, info in sorted(listening.items()):
                if port in held:
                    continue
                if port in released:
                    a = released[port]
                    released_but_listening.append({
                        "port": port,
                        "registered_to": f"{a.project}/{a.service}",
                        "addresses": info["addresses"],
                        "exposure": info["exposure"],
                        "process": info["process"],
                        "note": "Recorded as RELEASED but actively listening — "
                                "allocate_port may hand this port to another service"
                    })
                elif PORT_MIN <= port <= PORT_MAX:
                    # Only ports inside the allocatable range can collide.
                    # Warning about 22, 80 or 53 would be pure noise.
                    unregistered.append({
                        "port": port,
                        "addresses": info["addresses"],
                        "exposure": info["exposure"],
                        "process": info["process"],
                        "note": "In use but not registered — allocate_port "
                                "considers it available"
                    })

            registered_not_listening = [
                {
                    "port": p,
                    "registered_to": f"{a.project}/{a.service}",
                    "status": a.status.value,
                    "note": "Reserved but not listening — expected for a stopped "
                            "or on-demand service, not a problem"
                }
                for p, a in sorted(held.items())
                if p not in listening
            ]

            warnings = len(unregistered) + len(released_but_listening)
            total_warnings += warnings

            results[srv] = {
                "listening_in_range": len([p for p in listening if PORT_MIN <= p <= PORT_MAX]),
                "registered": len(held),
                "warnings": warnings,
                "unregistered": unregistered,
                "released_but_listening": released_but_listening,
                "registered_not_listening": registered_not_listening,
            }

        if not results and unreachable:
            return {
                "success": False,
                "error": "ALL_SERVERS_UNREACHABLE",
                "message": f"Could not reach any server: {unreachable}"
            }

        if total_warnings:
            message = f"⚠️ {total_warnings} port registry mismatch(es) that could cause a collision"
        else:
            message = "✅ Port registry matches what is actually listening"
        if unreachable:
            message += f" — NOT checked (unreachable): {', '.join(sorted(unreachable))}"

        return {
            "success": True,
            "summary": {
                "servers_checked": len(results),
                "total_warnings": total_warnings,
                "unreachable_servers": len(unreachable),
            },
            "by_server": results,
            "unreachable": unreachable,
            "message": message
        }

    except Exception as e:
        return {
            "success": False,
            "error": "RECONCILE_FAILED",
            "message": f"Failed to reconcile ports: {str(e)}"
        }


def _listening_ports(snapshot: ServerSnapshot) -> Dict[int, Dict[str, Any]]:
    """Map port -> its bound addresses and owning process, from the snapshot."""
    ports: Dict[int, Dict[str, Any]] = {}

    for line in snapshot.ss_output.split("\n"):
        parts = line.split()
        if len(parts) < 4 or parts[0] == "State":
            continue
        local = parts[3]
        if ":" not in local:
            continue
        addr, _, port_text = local.rpartition(":")
        if not port_text.isdigit():
            continue
        port = int(port_text)
        process = " ".join(parts[5:]) if len(parts) > 5 else "unknown"

        entry = ports.setdefault(port, {"addresses": [], "process": process})
        if addr not in entry["addresses"]:
            entry["addresses"].append(addr)

    # Annotate with the reachability of each address, so a reviewer can tell an
    # unregistered loopback service from an unregistered public one.
    for entry in ports.values():
        levels = {_classify_address(a)[0] for a in entry["addresses"]}
        entry["exposure"] = "high" if "high" in levels else (
            "low" if "low" in levels else "loopback"
        )

    return ports


async def validate_reconcile_ports_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for reconcile_ports tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    if "server" in data:
        if not isinstance(data["server"], str):
            return False, "Field 'server' must be a string"

        if data["server"] not in INFRA_SERVERS:
            return False, f"Invalid server. Must be one of: {', '.join(INFRA_SERVERS)}"

    return True, None
