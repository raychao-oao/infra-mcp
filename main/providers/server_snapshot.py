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

_SNAPSHOT_COMMAND = f"""
echo '{_MARKER}SS'
sudo ss -tlnp 2>/dev/null
for f in {CADDY_SITES_DIR}/*.caddy; do
  [ -f "$f" ] || continue
  echo '{_MARKER}CADDY '"$f"
  sudo cat "$f" 2>/dev/null
done
"""


class ServerSnapshot:
    """Listening sockets and Caddy site files for one server, fetched once."""

    def __init__(self, server: str, ss_output: str, caddy_files: Dict[str, str]):
        self.server = server
        self.ss_output = ss_output
        self.caddy_files = caddy_files

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
        caddy_files: Dict[str, str] = {}
        current: Optional[str] = None
        buffer: List[str] = []

        def flush():
            if current is not None:
                caddy_files[current] = "\n".join(buffer)

        for line in output.split("\n"):
            if line.startswith(_MARKER):
                flush()
                buffer = []
                section = line[len(_MARKER):]
                if section.startswith("CADDY "):
                    current = section[len("CADDY "):].strip()
                else:
                    current = None
                continue
            if current is None:
                ss_lines.append(line)
            else:
                buffer.append(line)
        flush()

        return cls(server, "\n".join(ss_lines), caddy_files)

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
