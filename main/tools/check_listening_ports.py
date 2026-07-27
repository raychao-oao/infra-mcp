"""
check_listening_ports MCP Tool Implementation

Check listening ports on a VPS server to identify security risks.
Returns all ports not bound to 127.0.0.1 (localhost only).
"""

import ipaddress
import subprocess
import re
from typing import Optional, Dict, Any, Tuple

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.providers.ssh_provider import run_command

# Tailscale's ranges. 100.64.0.0/10 is CGNAT shared address space and
# fd7a:115c:a1e0::/48 is Tailscale's ULA prefix; both are reachable only from
# within the tailnet.
TAILSCALE_V4 = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")

# Wildcard forms `ss` emits for "every interface, including the public IP".
WILDCARD_ADDRESSES = {"0.0.0.0", "::", "*"}


def _normalize_address(raw: str) -> str:
    """
    Strip the decorations `ss` puts around a local address so it can be parsed.

    `ss` emits IPv6 in brackets (`[::1]`, `[fd7a:...]`) and appends a scope/zone
    suffix on link-local and some loopback binds (`127.0.0.53%lo`, `fe80::1%eth0`).
    Comparing the raw string against a literal list misses all of these — which is
    how `127.0.0.53%lo:53` came to be reported as "Publicly accessible".
    """
    addr = raw.strip()
    if addr.startswith("[") and addr.endswith("]"):
        addr = addr[1:-1]
    # Bracketed IPv6 keeps its zone inside the brackets, so strip it after unwrapping.
    addr = addr.split("%", 1)[0]
    return addr


def _classify_address(raw: str) -> Tuple[str, str]:
    """
    Grade a listening address by how much of the network can actually reach it.

    Returns (risk_level, note). Levels: "none", "low", "high", "unknown".

    Severity ordering matters and used to be inverted here: `0.0.0.0` includes the
    public IP and is the worst case, while a bind to a specific address is usually
    a *deliberate* restriction (Tailscale, docker bridge) and is the safe case.
    """
    addr = _normalize_address(raw)

    if addr in WILDCARD_ADDRESSES:
        return "high", "Bound to all interfaces — reachable on the public IP"

    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Unparseable rather than assumed safe: an address this code cannot read
        # is an address it cannot vouch for.
        return "unknown", f"Could not parse address '{raw}' — verify manually"

    if ip.is_unspecified:
        return "high", "Bound to all interfaces — reachable on the public IP"

    if ip.is_loopback:
        return "none", "Loopback only"

    if ip in TAILSCALE_V4 or ip in TAILSCALE_V6:
        return "low", "Tailscale address — reachable from the tailnet only"

    if ip.is_link_local:
        return "low", "Link-local address — reachable from the local segment only"

    if ip.is_private:
        return "low", "Private address — not routable from the internet"

    return "high", "Bound directly to a public IP address"


async def check_listening_ports(
    store: SQLiteStore,
    server: str,
    port: Optional[int] = None
) -> Dict[str, Any]:
    """
    Check listening ports on a VPS server.

    Args:
        store: SQLiteStore instance
        server: VPS server name (configured via INFRA_SERVERS)
        port: Optional specific port to check

    Returns:
        Dict with listening ports information including security risks
    """

    # Validate server name
    valid_servers = INFRA_SERVERS
    if server not in valid_servers:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Invalid server name. Must be one of: {', '.join(valid_servers)}"
        }

    # Check listening ports
    try:
        result = run_command(server, "sudo ss -tlnp", timeout=30)

        if result.returncode != 0:
            return {
                "success": False,
                "error": "SSH_COMMAND_FAILED",
                "message": f"Failed to check ports on {server}: {result.stderr}"
            }

        # Parse ss output
        lines = result.stdout.strip().split('\n')

        # Skip header line
        if lines and lines[0].startswith('State'):
            lines = lines[1:]

        all_ports = []
        security_risks = []

        for line in lines:
            if not line.strip():
                continue

            # Parse ss output line
            # Format: State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
            parts = line.split()
            if len(parts) < 5:
                continue

            local_address = parts[3]
            process_info = ' '.join(parts[5:]) if len(parts) > 5 else "unknown"

            # Extract IP and port
            match = re.match(r'(.*):(\d+)$', local_address)
            if not match:
                continue

            ip = match.group(1)
            port_num = int(match.group(2))

            # Skip if filtering by specific port
            if port is not None and port_num != port:
                continue

            risk_level, note = _classify_address(ip)

            port_info = {
                "port": port_num,
                "ip": ip,
                "process": process_info,
                "risk_level": risk_level,
                "note": note
            }

            all_ports.append(port_info)

            if risk_level != "none":
                security_risks.append(port_info)

        # Build summary
        def _count(level: str) -> int:
            return len([p for p in all_ports if p["risk_level"] == level])

        high_risks = _count("high")
        summary = {
            "total_listening_ports": len(all_ports),
            "localhost_only": _count("none"),
            "low_risks": _count("low"),
            "high_risks": high_risks,
            "unknown": _count("unknown"),
        }

        if high_risks:
            exposed = ", ".join(
                f"{p['ip']}:{p['port']}" for p in all_ports if p["risk_level"] == "high"
            )
            message = f"{high_risks} port(s) exposed on {server}: {exposed}"
        elif security_risks:
            message = (
                f"No public exposure on {server}; "
                f"{len(security_risks)} port(s) bound to Tailscale/private addresses"
            )
        else:
            message = f"All ports safely bound to localhost on {server}"

        return {
            "success": True,
            "server": server,
            "summary": summary,
            "all_ports": all_ports,
            "security_risks": security_risks,
            "message": message
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "SSH_TIMEOUT",
            "message": f"SSH command timed out when connecting to {server}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "UNEXPECTED_ERROR",
            "message": f"Unexpected error checking ports on {server}: {str(e)}"
        }


async def validate_check_listening_ports_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for check_listening_ports tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    if "server" not in data:
        return False, "Missing required field: server"

    if not isinstance(data["server"], str):
        return False, "Field 'server' must be a string"

    valid_servers = INFRA_SERVERS
    if data["server"] not in valid_servers:
        return False, f"Invalid server. Must be one of: {', '.join(valid_servers)}"

    if "port" in data:
        if not isinstance(data["port"], int):
            return False, "Field 'port' must be an integer"
        if data["port"] < 1 or data["port"] > 65535:
            return False, "Field 'port' must be between 1 and 65535"

    return True, None
