"""
check_listening_ports MCP Tool Implementation

Check listening ports on a VPS server to identify security risks.
Returns all ports not bound to 127.0.0.1 (localhost only).
"""

import subprocess
import re
from typing import Optional, Dict, Any, List

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.providers.ssh_provider import run_command


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

            port_info = {
                "port": port_num,
                "ip": ip,
                "process": process_info
            }

            all_ports.append(port_info)

            # Check if it's a security risk (not bound to 127.0.0.1 or ::1)
            if ip not in ["127.0.0.1", "::1"]:
                # Check if it's actually exposed (not 0.0.0.0 or * or ::*)
                # These might be safe if UFW is blocking them
                if ip in ["0.0.0.0", "*", "[::]", "::*", "*:*"]:
                    port_info["risk_level"] = "potential"
                    port_info["note"] = "Bound to all interfaces - check UFW firewall"
                else:
                    port_info["risk_level"] = "high"
                    port_info["note"] = "Publicly accessible"

                security_risks.append(port_info)

        # Build summary
        summary = {
            "total_listening_ports": len(all_ports),
            "localhost_only": len([p for p in all_ports if p["ip"] in ["127.0.0.1", "::1"]]),
            "potential_risks": len([p for p in security_risks if p.get("risk_level") == "potential"]),
            "high_risks": len([p for p in security_risks if p.get("risk_level") == "high"]),
        }

        return {
            "success": True,
            "server": server,
            "summary": summary,
            "all_ports": all_ports,
            "security_risks": security_risks,
            "message": f"Found {len(security_risks)} potential security risks on {server}" if security_risks else f"All ports safely bound to localhost on {server}"
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
