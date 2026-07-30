"""Regression tests for the 2026-07-30 asablue outage (issue #1).

A deploy_service run generated a Caddy log directive for a directory that
could not be created; the failure was swallowed, reload fell back to a blind
restart that killed the running Caddy, `systemctl restart` (Type=simple)
reported success anyway, and the deploy kept going. Every Caddy-fronted site
on the server was down for 17 minutes.
"""

import pytest

import main.tools.deploy_service as ds
from main.tools.register_service import register_service


def _ok(stdout=""):
    return {"success": True, "stdout": stdout, "stderr": ""}


def _fail(stderr="boom"):
    return {"success": False, "stdout": "", "stderr": stderr}


class FakeSSH:
    """run_ssh_command stand-in: match commands by substring, in order.

    rules: list of (substring, result_or_list). A list is consumed one result
    per matching call (for commands issued multiple times with different
    outcomes). Unmatched commands succeed.
    """

    def __init__(self, rules=None):
        self.rules = [(s, list(r) if isinstance(r, list) else [r]) for s, r in (rules or [])]
        self.commands = []

    async def __call__(self, server, command, timeout=30):
        self.commands.append(command)
        for sub, queue in self.rules:
            if sub in command:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        return _ok()

    def issued(self, substring):
        return [c for c in self.commands if substring in c]


# --- C1: log-dir creation failure must be fatal, not swallowed -------------

@pytest.mark.asyncio
async def test_create_directories_logdir_failure_is_fatal(monkeypatch):
    ssh = FakeSSH([("/var/log/", _fail("mkdir: read-only file system"))])
    monkeypatch.setattr(ds, "run_ssh_command", ssh)

    result = await ds.create_directories(
        server="prod", project="demo", service_type="flask",
        static_path=None, app_path="~/PRJ/demo/app/",
    )

    assert result["success"] is False
    assert any("/var/log/demo" in e for e in result["errors"])


# --- C2: reload_caddy must never blind-restart a running Caddy -------------

@pytest.mark.asyncio
async def test_reload_rejected_running_caddy_is_not_restarted(monkeypatch):
    ssh = FakeSSH([
        ("reload caddy", _fail("config validation failed")),
        ("is-active caddy", _ok("active")),
    ])
    monkeypatch.setattr(ds, "run_ssh_command", ssh)

    result = await ds.reload_caddy("prod")

    assert result["success"] is False
    assert result.get("caddy_still_running") is True
    assert ssh.issued("restart caddy") == []


@pytest.mark.asyncio
async def test_reload_failed_dead_caddy_restart_is_verified(monkeypatch):
    # Caddy was not running: restart is safe, and a verified-active restart
    # counts as success (first-deploy / caddy-was-down case).
    ssh = FakeSSH([
        ("reload caddy", _fail("caddy is not active, cannot reload")),
        ("restart caddy", _ok()),
        ("is-active caddy", [_fail("inactive"), _ok("active"), _ok("active")]),
    ])
    monkeypatch.setattr(ds, "run_ssh_command", ssh)

    result = await ds.reload_caddy("prod")

    assert result["success"] is True
    assert len(ssh.issued("restart caddy")) == 1


@pytest.mark.asyncio
async def test_restart_success_lie_is_detected(monkeypatch):
    # `systemctl restart` exits 0 for Type=simple units even when the process
    # dies immediately. The post-restart is-active probe must catch it.
    ssh = FakeSSH([
        ("reload caddy", _fail("caddy is not active, cannot reload")),
        ("restart caddy", _ok()),
        ("is-active caddy", _fail("failed")),
    ])
    monkeypatch.setattr(ds, "run_ssh_command", ssh)

    result = await ds.reload_caddy("prod")

    assert result["success"] is False


# --- main flow: rollback on reload failure, systemd failure is fatal -------

async def _registered_flask(store):
    r = await register_service(
        store, project="demo", service="api", server="prod",
        service_type="flask", port=3999,
        workspace_url="https://git.example.com/u/project-demo",
    )
    assert r["success"], r
    return r


@pytest.mark.asyncio
async def test_deploy_rolls_back_site_file_on_reload_failure(monkeypatch, store):
    await _registered_flask(store)

    ssh = FakeSSH()
    monkeypatch.setattr(ds, "run_ssh_command", ssh)

    async def dirs_ok(**kwargs):
        return {"success": True, "created": []}

    async def caddy_ok(**kwargs):
        return {"success": True, "config_file": "/etc/caddy/sites/demo-api.caddy",
                "config_content": ""}

    async def reload_fails(server):
        return {"success": False, "error": "CADDY_RELOAD_REJECTED", "stderr": "bad config"}

    monkeypatch.setattr(ds, "create_directories", dirs_ok)
    monkeypatch.setattr(ds, "generate_and_write_caddy_config", caddy_ok)
    monkeypatch.setattr(ds, "reload_caddy", reload_fails)

    result = await ds.deploy_service(store, "demo", "api", "prod")

    assert result["success"] is False
    assert result["error"] == "CADDY_RELOAD_FAILED"
    # The just-written site file must have been removed again
    assert any("/etc/caddy/sites/demo-api.caddy" in c for c in ssh.issued("rm -f"))


@pytest.mark.asyncio
async def test_deploy_fails_when_systemd_write_fails(monkeypatch, store):
    await _registered_flask(store)

    monkeypatch.setattr(ds, "run_ssh_command", FakeSSH())

    async def dirs_ok(**kwargs):
        return {"success": True, "created": []}

    async def caddy_ok(**kwargs):
        return {"success": True, "config_file": "/etc/caddy/sites/demo-api.caddy",
                "config_content": ""}

    async def reload_ok(server):
        return {"success": True, "action": "reload"}

    async def systemd_fails(**kwargs):
        return {"success": False, "error": "WRITE_FAILED",
                "message": "mv: read-only file system"}

    monkeypatch.setattr(ds, "create_directories", dirs_ok)
    monkeypatch.setattr(ds, "generate_and_write_caddy_config", caddy_ok)
    monkeypatch.setattr(ds, "reload_caddy", reload_ok)
    monkeypatch.setattr(ds, "generate_and_write_systemd_service", systemd_fails)

    result = await ds.deploy_service(store, "demo", "api", "prod")

    assert result["success"] is False
    assert result["error"] == "SYSTEMD_SERVICE_FAILED"
