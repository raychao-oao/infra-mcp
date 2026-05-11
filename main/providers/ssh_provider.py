"""
SSH Provider - Shared command execution utility.

Automatically detects whether the target server is local (running on this machine)
or remote, and executes commands accordingly:
- Local: subprocess.run(command, shell=True) directly
- Remote: ssh server "command" via subprocess

Detection uses the INFRA_LOCAL_SERVER environment variable.
"""

import asyncio
import os
import subprocess

from main.utils import validate_identifier


def is_local_server(server: str) -> bool:
    """Check if the target server is the local machine."""
    local_server = os.environ.get("INFRA_LOCAL_SERVER", "")
    return local_server != "" and server == local_server


def run_command(
    server: str,
    command: str,
    timeout: int = 30
) -> subprocess.CompletedProcess:
    """
    Execute a command on the target server.

    If the server is local, runs the command directly.
    If remote, wraps it in an SSH call.

    Args:
        server: VPS server name
        command: Shell command to execute
        timeout: Timeout in seconds

    Returns:
        subprocess.CompletedProcess with stdout, stderr, returncode
    """
    validate_identifier(server, "server")
    if is_local_server(server):
        return subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return subprocess.run(
        ["ssh", server, command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


async def async_run_command(
    server: str,
    command: str,
    timeout: int = 30
) -> dict:
    """
    Execute a command on the target server asynchronously.

    If the server is local, runs the command directly.
    If remote, wraps it in an SSH call.

    Args:
        server: VPS server name
        command: Shell command to execute
        timeout: Timeout in seconds

    Returns:
        Dict with success status, stdout, stderr
    """
    validate_identifier(server, "server")

    try:
        if is_local_server(server):
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                "ssh", server, command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "error": "TIMEOUT",
                "message": f"Command timed out after {timeout}s"
            }

        if proc.returncode != 0:
            return {
                "success": False,
                "error": "COMMAND_FAILED",
                "returncode": proc.returncode,
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
            }

        return {
            "success": True,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
        }

    except Exception as e:
        return {
            "success": False,
            "error": "COMMAND_ERROR",
            "message": str(e)
        }
