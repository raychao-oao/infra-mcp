"""
Server Snapshot - one round trip, everything the security checks need.

The security tools used to issue an SSH call per question per service: does this
Caddy file exist, grep for the hostname, cat the file, check the port binding.
At four round trips each and a server on another continent, auditing 21 services
took minutes. A slow audit gets skipped just as reliably as a noisy one, so the
cost has to be per *server*, not per service.

A snapshot collects the listening sockets and every Caddy site file in a single
command, then answers all subsequent questions locally.
"""

import re
from typing import Dict, List, Optional, Tuple

from main.providers.ssh_provider import run_command

CADDY_SITES_DIR = "/etc/caddy/sites"

# Section delimiter for the combined command's output. Deliberately unlikely to
# appear in a Caddy file; it is also anchored to the start of a line when parsed.
_MARKER = "#===INFRA-MCP-SNAPSHOT:"

SYSTEMD_DIR = "/etc/systemd/system"

# Only bind-address settings are ever read out of a unit or its EnvironmentFile.
# Those files hold API keys and passwords; pulling whole ones back would put
# secrets into tool output and model context for no benefit. Both greps below
# are anchored so nothing else can come along for the ride.
_BIND_KEY_RE = r"^(ADMIN_)?(BIND_|SERVER_)?(HOST|PORT)="
_UNIT_LINE_RE = r"^(ExecStart|EnvironmentFile|WorkingDirectory)="

_SNAPSHOT_COMMAND = f"""
echo '{_MARKER}SS'
sudo ss -tlnp 2>/dev/null
for f in {CADDY_SITES_DIR}/*.caddy; do
  [ -f "$f" ] || continue
  echo '{_MARKER}CADDY '"$f"
  sudo cat "$f" 2>/dev/null
done
echo '{_MARKER}IPT4 -'
sudo iptables -S INPUT 2>/dev/null
echo '{_MARKER}IPT6 -'
sudo ip6tables -S INPUT 2>/dev/null
echo '{_MARKER}PKG -'
dpkg -l iptables-persistent netfilter-persistent ufw firewalld nftables 2>/dev/null | grep -E '^(ii|rc)' || true
echo '{_MARKER}UFW -'
grep -i '^ENABLED' /etc/ufw/ufw.conf 2>/dev/null || true
command -v ufw >/dev/null 2>&1 && echo 'BINARY=present' || echo 'BINARY=missing'
for u in {SYSTEMD_DIR}/*.service; do
  [ -f "$u" ] || continue
  echo '{_MARKER}UNIT '"$u"
  grep -E '{_UNIT_LINE_RE}' "$u" 2>/dev/null
  grep -E '^Environment="?{_BIND_KEY_RE[1:]}' "$u" 2>/dev/null
  for ef in $(grep -h '^EnvironmentFile=' "$u" 2>/dev/null | sed 's/^EnvironmentFile=-\\{{0,1\\}}//'); do
    [ -f "$ef" ] || continue
    echo '{_MARKER}ENV '"$ef"
    sudo grep -E '{_BIND_KEY_RE}' "$ef" 2>/dev/null
  done
done
"""


def _parse_env(text: str) -> Dict[str, str]:
    """Parse KEY=VALUE lines, tolerating quotes and blank lines."""
    env = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


class ServerSnapshot:
    """Listening sockets and Caddy site files for one server, fetched once."""

    def __init__(
        self,
        server: str,
        ss_output: str,
        caddy_files: Dict[str, str],
        unit_files: Optional[Dict[str, str]] = None,
        env_files: Optional[Dict[str, str]] = None,
        firewall: Optional[Dict[str, str]] = None,
    ):
        self.server = server
        self.ss_output = ss_output
        self.caddy_files = caddy_files
        # Units hold only ExecStart/EnvironmentFile/WorkingDirectory and
        # bind-related Environment lines; env files hold only bind-related keys.
        self.unit_files = unit_files or {}
        self.env_files = env_files or {}
        self.firewall = firewall or {}

    @classmethod
    def fetch(cls, server: str, timeout: int = 60) -> "ServerSnapshot":
        """
        Collect the snapshot in a single SSH round trip.

        Raises RuntimeError if the command fails outright. A partial result is
        fine: a host with no Caddy sites simply yields no CADDY sections.
        """
        result = run_command(server, _SNAPSHOT_COMMAND, timeout=timeout)
        if result.returncode != 0 and not result.stdout.strip():
            raise RuntimeError(
                f"Failed to snapshot {server}: {result.stderr.strip() or 'no output'}"
            )
        return cls._parse(server, result.stdout)

    @classmethod
    def _parse(cls, server: str, output: str) -> "ServerSnapshot":
        ss_lines: List[str] = []
        sections: Dict[str, Dict[str, str]] = {
            "CADDY": {}, "UNIT": {}, "ENV": {},
            "IPT4": {}, "IPT6": {}, "PKG": {}, "UFW": {},
        }
        kind: Optional[str] = None
        path: Optional[str] = None
        buffer: List[str] = []

        def flush():
            if kind and path:
                sections[kind][path] = "\n".join(buffer)

        for line in output.split("\n"):
            if line.startswith(_MARKER):
                flush()
                buffer = []
                section = line[len(_MARKER):]
                kind, _, rest = section.partition(" ")
                if kind in sections:
                    path = rest.strip()
                else:
                    kind, path = None, None
                continue
            if kind is None:
                ss_lines.append(line)
            else:
                buffer.append(line)
        flush()

        return cls(
            server,
            "\n".join(ss_lines),
            sections["CADDY"],
            sections["UNIT"],
            sections["ENV"],
            firewall={
                "iptables_v4": sections["IPT4"].get("-", ""),
                "iptables_v6": sections["IPT6"].get("-", ""),
                "packages": sections["PKG"].get("-", ""),
                "ufw": sections["UFW"].get("-", ""),
            },
        )

    # --- listening sockets -------------------------------------------------

    def listening_addresses(self, port: int) -> List[str]:
        """Every local address bound to `port`, as `ss` printed it."""
        addresses = []
        for line in self.ss_output.split("\n"):
            parts = line.split()
            if len(parts) < 4 or parts[0] == "State":
                continue
            match = re.match(r"(.*):(\d+)$", parts[3])
            if not match:
                continue
            if int(match.group(2)) == port:
                addresses.append(match.group(1))
        return addresses

    def process_for_port(self, port: int) -> str:
        """The raw `ss` lines for `port`, for reporting."""
        return "\n".join(
            line for line in self.ss_output.split("\n")
            if re.search(rf":{port}\s", line)
        )

    # --- Caddy site files --------------------------------------------------

    def locate_caddy_configs(
        self,
        svc_name: str,
        hostname: Optional[str],
        port: Optional[int],
        static_path: Optional[str]
    ) -> Tuple[List[str], str]:
        """
        Find the Caddy site file(s) serving a deployment.

        Returns (paths, how_they_were_found); empty paths means no site file
        references this service.

        Strategies, in order of confidence:
          1. the conventional filename, when it happens to exist
          2. the hostname — a Caddy site block is keyed by it, and in practice
             every deployment record carries one
          3. the backend port, for anything behind reverse_proxy
          4. the static root, for file_server sites that never mention a port

        More than one file can legitimately match: two hostnames may proxy the
        same backend port, so every match is returned and each gets checked.
        """
        guess = f"{CADDY_SITES_DIR}/{svc_name}.caddy"
        if guess in self.caddy_files:
            return [guess], "conventional filename"

        if hostname:
            paths = self._grep_word(hostname)
            if paths:
                return paths, f"hostname {hostname}"

        if port:
            paths = self._grep_word(f"localhost:{port}") or self._grep_word(f"127.0.0.1:{port}")
            if paths:
                return paths, f"reverse_proxy to port {port}"

        # Last resort, and exact-match only: records drift from what Caddy
        # actually serves (a record may say /var/www/x/static while Caddy roots
        # one level up at /var/www/x).
        if static_path:
            paths = self._grep_word(static_path)
            if paths:
                return paths, f"static root {static_path}"

        return [], "not found"

    # --- systemd units -----------------------------------------------------

    def locate_unit(self, svc_name: str, project: str) -> Optional[str]:
        """
        Find the systemd unit for a deployment.

        Deriving `{project}-{service}.service` and stopping there repeats the
        mistake that made the Caddy check useless: real units are often named
        after the project alone — `sa-integration.service` serves
        sa-integration/sandbox, `lyricvid.service` serves lyricvid/web. Guessing
        produced "no unit file" for four services that have one.

        Falls back to matching a unit whose WorkingDirectory or ExecStart points
        into the project's directory, which is what actually ties them together.
        """
        for candidate in (f"{svc_name}.service", f"{project}.service"):
            path = f"{SYSTEMD_DIR}/{candidate}"
            if path in self.unit_files:
                return path

        marker = f"/{project}/"
        matches = [
            path for path, content in self.unit_files.items()
            for line in content.split("\n")
            if line.startswith(("WorkingDirectory=", "ExecStart="))
            and (marker in line or line.rstrip().endswith(f"/{project}"))
        ]
        # Only trust this when it is unambiguous; two units sharing a project
        # directory means we cannot tell which one the record refers to.
        unique = sorted(set(matches))
        return unique[0] if len(unique) == 1 else None

    def env_for_unit(self, unit_path: str) -> Dict[str, str]:
        """
        Bind-related environment for a unit: its EnvironmentFile(s) first, then
        its own Environment= lines, which take precedence in systemd.

        Only HOST/PORT-style keys are ever collected (see _BIND_KEY_RE); this is
        never a full view of the service's environment, by design.
        """
        unit = self.unit_files.get(unit_path, "")
        env: Dict[str, str] = {}

        for line in unit.split("\n"):
            if line.startswith("EnvironmentFile="):
                path = line[len("EnvironmentFile="):].lstrip("-").strip()
                env.update(_parse_env(self.env_files.get(path, "")))

        for line in unit.split("\n"):
            if line.startswith("Environment="):
                env.update(_parse_env(line[len("Environment="):].strip().strip('"')))

        return env

    def _grep_word(self, needle: str) -> List[str]:
        """
        Paths whose content contains `needle` delimited by non-word characters.

        The word boundary is what stops `localhost:3003` from matching
        `localhost:30031`, and `a.example.com` from matching `xa.example.com`.
        """
        pattern = re.compile(rf"(?<![\w.]){re.escape(needle)}(?![\w.])")
        return sorted(
            path for path, content in self.caddy_files.items()
            if pattern.search(content)
        )
