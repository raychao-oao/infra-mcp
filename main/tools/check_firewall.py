"""
check_firewall MCP Tool Implementation

Check whether a host actually has a working, persistent packet filter.

Written after 2026-07-27, when a production host was found serving six backend
services and the Caddy admin API straight to the public internet. Its firewall had
silently disappeared: the ufw package was in `rc` state (removed but not
purged), the binary was gone, yet `/etc/ufw/ufw.conf` still said `ENABLED=yes`
and `systemctl is-enabled ufw` still answered `enabled` — because that reads a
leftover init script. Every indicator anyone would casually check said the host
was protected. None of them were evidence.

So this tool refuses to ask "is the firewall service enabled". It asks:

  1. Is there a terminal REJECT/DROP, or a default-deny policy? That is the
     only thing that actually blocks a packet.
  2. Are the persistence packages really installed (`ii`, not `rc`)? Without
     them the rules are gone at the next reboot. One host was in exactly this
     state: protected right up until it restarted.
  3. Does anything claim to be a firewall while not being one? A `rc`-state
     package or an ENABLED=yes config with no binary is worse than nothing,
     because it answers "yes" when asked.
  4. Is IPv6 covered too? Purging ufw on one host left the v6 INPUT chain
     wide open with policy ACCEPT while v4 looked fine.
"""

import re
from typing import Optional, Dict, Any, List

from main.config import INFRA_SERVERS
from main.providers.server_snapshot import ServerSnapshot

_PERSISTENCE_PACKAGES = ("iptables-persistent", "netfilter-persistent")
_FIREWALL_FRONTENDS = ("ufw", "firewalld")


async def check_firewall(
    server: Optional[str] = None,
    snapshot: Optional[ServerSnapshot] = None
) -> Dict[str, Any]:
    """
    Check the packet filter on one server or all configured servers.

    Args:
        server: VPS server name; all configured servers when omitted
        snapshot: Pre-fetched state, when the caller already has one

    Returns:
        Dict with per-server firewall findings
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

    results = {}
    unreachable = {}
    total_issues = 0

    for srv in servers:
        try:
            snap = snapshot if (snapshot and snapshot.server == srv) else ServerSnapshot.fetch(srv)
        except Exception as e:
            unreachable[srv] = str(e)
            continue

        report = _assess(snap.firewall)
        total_issues += len(report["issues"])
        results[srv] = report

    if not results and unreachable:
        return {
            "success": False,
            "error": "ALL_SERVERS_UNREACHABLE",
            "message": f"Could not reach any server: {unreachable}"
        }

    protected = [s for s, r in results.items() if r["protected"]]
    if total_issues:
        message = f"⚠️ {total_issues} firewall issue(s) across {len(results)} server(s)"
    else:
        message = f"✅ {len(protected)}/{len(results)} server(s) have a persistent packet filter"
    if unreachable:
        message += f" — NOT checked (unreachable): {', '.join(sorted(unreachable))}"

    return {
        "success": True,
        "summary": {
            "servers_checked": len(results),
            "protected": len(protected),
            "total_issues": total_issues,
            "unreachable_servers": len(unreachable),
        },
        "by_server": results,
        "unreachable": unreachable,
        "message": message
    }


def _assess(firewall: Dict[str, str]) -> Dict[str, Any]:
    """Judge one host's filter from its collected state."""
    issues: List[str] = []
    notes: List[str] = []

    v4 = _assess_chain(firewall.get("iptables_v4", ""), "IPv4")
    v6 = _assess_chain(firewall.get("iptables_v6", ""), "IPv6")

    if not v4["protected"]:
        issues.append(f"IPv4 INPUT is not filtered: {v4['reason']}")
    if not v6["protected"]:
        # Its own finding, not a footnote: purging ufw left a host's v6 chain at
        # policy ACCEPT with no rules while v4 looked healthy.
        issues.append(f"IPv6 INPUT is not filtered: {v6['reason']}")

    packages = _parse_packages(firewall.get("packages", ""))

    persistent = [p for p in _PERSISTENCE_PACKAGES if packages.get(p) == "ii"]
    if (v4["protected"] or v6["protected"]) and not persistent:
        half_installed = [p for p in _PERSISTENCE_PACKAGES if packages.get(p) == "rc"]
        detail = (
            f"{', '.join(half_installed)} is in 'rc' state (removed, config left behind)"
            if half_installed else "no persistence package installed"
        )
        issues.append(
            f"Rules are active but will not survive a reboot: {detail}. "
            f"`systemctl is-enabled` can still answer 'enabled' here — it reads a "
            f"leftover init script, not a working installation"
        )

    # A frontend that is half-removed is worse than absent: it keeps answering
    # "enabled" to the checks people actually run.
    ufw_text = firewall.get("ufw", "")
    ufw_claims_enabled = bool(re.search(r"^ENABLED=yes", ufw_text, re.MULTILINE | re.IGNORECASE))
    ufw_binary_missing = "BINARY=missing" in ufw_text

    for frontend in _FIREWALL_FRONTENDS:
        if packages.get(frontend) == "rc":
            issues.append(
                f"{frontend} is in 'rc' state — the binary is gone but its config "
                f"remains, so status checks still report it as present"
            )

    if ufw_claims_enabled and ufw_binary_missing:
        issues.append(
            "/etc/ufw/ufw.conf still says ENABLED=yes but the ufw binary is "
            "missing — this exact combination hid the absence of any firewall "
            "on prod for months"
        )

    if packages.get("ufw") == "ii" and persistent:
        notes.append(
            "Both ufw and iptables-persistent are installed; two managers over "
            "one rule set is how rules get silently overwritten"
        )

    if v4["protected"] and v6["protected"] and persistent and not issues:
        notes.append(f"Persistent via {', '.join(persistent)}")

    return {
        "protected": v4["protected"] and v6["protected"],
        "ipv4": v4,
        "ipv6": v6,
        "persistence": persistent,
        "packages": packages,
        "issues": issues,
        "notes": notes,
    }


def _assess_chain(rules: str, family: str) -> Dict[str, Any]:
    """
    Decide whether an INPUT chain actually blocks anything.

    Only two things stop a packet: a default-deny policy, or a terminal
    REJECT/DROP that unmatched traffic falls through to. Counting rules proves
    nothing — a chain full of ACCEPTs ending in nothing is wide open.
    """
    lines = [line.strip() for line in rules.strip().split("\n") if line.strip()]
    if not lines:
        return {
            "protected": False,
            "policy": None,
            "reason": f"no {family} INPUT rules could be read (is iptables installed?)",
            "accepted_ports": [],
        }

    policy = None
    for line in lines:
        match = re.match(r"-P INPUT (\w+)", line)
        if match:
            policy = match.group(1)
            break

    appends = [line for line in lines if line.startswith("-A INPUT")]
    terminal = bool(appends) and bool(
        re.search(r"-j (REJECT|DROP)\b", appends[-1])
    ) and "-p " not in appends[-1] and "--dport" not in appends[-1]

    # Carry the source restriction with the port. "2020 is open" reads very
    # differently from "2020 is open to 172.20.0.0/16", and a security report
    # that drops the qualifier is misleading in the direction that matters.
    accepted = {}
    for line in appends:
        if "-j ACCEPT" not in line:
            continue
        source = re.search(r"-s (\S+)", line)
        for match in re.finditer(r"--dport (\d+)", line):
            port = int(match.group(1))
            accepted[port] = f"{port} from {source.group(1)}" if source else str(port)
    accepted_ports = [accepted[p] for p in sorted(accepted)]

    if policy in ("DROP", "REJECT"):
        return {
            "protected": True,
            "policy": policy,
            "reason": f"default policy {policy}",
            "accepted_ports": accepted_ports,
        }

    if terminal:
        return {
            "protected": True,
            "policy": policy,
            "reason": f"terminal {appends[-1].split('-j ')[-1].split()[0]} rule",
            "accepted_ports": accepted_ports,
        }

    return {
        "protected": False,
        "policy": policy,
        "reason": (
            f"policy is {policy or 'unknown'} and the chain has no terminal "
            f"REJECT/DROP — unmatched traffic is accepted"
        ),
        "accepted_ports": accepted_ports,
    }


def _parse_packages(text: str) -> Dict[str, str]:
    """Map package name -> dpkg state ('ii' installed, 'rc' removed-not-purged)."""
    packages = {}
    for line in text.strip().split("\n"):
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("ii", "rc"):
            packages[parts[1]] = parts[0]
    return packages


async def validate_check_firewall_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for check_firewall tool.

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
