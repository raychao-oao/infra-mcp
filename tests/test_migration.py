import json
import sqlite3
import subprocess
import sys

OLD_SCHEMA = """
CREATE TABLE service_deployments (
    deployment_id TEXT PRIMARY KEY, project TEXT, service TEXT, server TEXT,
    service_type TEXT, port INTEGER, hostname TEXT, tunnel_name TEXT,
    app_path TEXT, static_path TEXT, data_path TEXT, log_path TEXT, config_path TEXT,
    caddy_rules TEXT, environment TEXT, systemd_config TEXT,
    status TEXT, registered_at TEXT, registered_by TEXT,
    deployed_at TEXT, stopped_at TEXT, archived_at TEXT, purged_at TEXT,
    notes TEXT, backup_config TEXT
);
"""


def make_old_db(path):
    db = sqlite3.connect(path)
    db.executescript(OLD_SCHEMA)
    db.execute("INSERT INTO service_deployments (deployment_id, project, service, server, service_type,"
               " app_path, static_path, data_path, config_path, status, deployed_at) VALUES"
               " ('d1','alpha','api','prod','FLASK','~/PRJ/alpha/app/','/var/www/alpha/',"
               "  '~/PRJ/alpha/data/','~/PRJ/alpha/config/','DEPLOYED','2026-01-01T00:00:00')")
    db.execute("INSERT INTO service_deployments (deployment_id, project, service, server, service_type,"
               " app_path, data_path, config_path, status) VALUES"
               " ('d2','beta-stack','caddy','prod','DOCKER','~/PRJ/beta-stack/app/',"
               "  '~/PRJ/beta-stack/data/','~/PRJ/beta-stack/config/','REGISTERED')")
    db.execute("INSERT INTO service_deployments (deployment_id, project, service, server, service_type,"
               " app_path, data_path, status, deployed_at) VALUES"
               " ('d3','gamma','web','prod','FLASK','~/PRJ/gamma/app/','~/PRJ/gamma/instance/',"
               "  'DEPLOYED','2026-01-01T00:00:00')")
    db.commit(); db.close()


def run_migration(db_path, phase):
    return subprocess.run([sys.executable, "scripts/migrate_resource_model.py",
                           "--db", str(db_path), "--phase", phase, "--execute"],
                          capture_output=True, text=True)


def test_phase_add_classifies_and_carries(tmp_path):
    db_path = tmp_path / "r.db"; make_old_db(db_path)
    r = run_migration(db_path, "add"); assert r.returncode == 0, r.stderr
    db = sqlite3.connect(db_path)
    rows = {row[0]: row for row in db.execute(
        "SELECT deployment_id, layer, project_root, deploy_root, path_overrides FROM service_deployments")}
    # deployed → STANDARD，根從舊 app_path 導出，慣例值不進 overrides
    assert rows["d1"][1] == "STANDARD" and rows["d1"][2] == "~/PRJ/alpha/"
    assert rows["d1"][3] == "/var/www/alpha/" and rows["d1"][4] is None
    # never deployed → NONSTANDARD，幽靈全丟
    assert rows["d2"][1] == "NONSTANDARD" and rows["d2"][2] is None and rows["d2"][4] is None
    # 非慣例 data → override
    assert json.loads(rows["d3"][4])["data"] == "~/PRJ/gamma/instance/"


def test_phase_drop_removes_old_columns(tmp_path):
    db_path = tmp_path / "r.db"; make_old_db(db_path)
    run_migration(db_path, "add")
    r = run_migration(db_path, "drop"); assert r.returncode == 0, r.stderr
    db = sqlite3.connect(db_path)
    cols = {c[1] for c in db.execute("PRAGMA table_info(service_deployments)")}
    assert "app_path" not in cols and "layer" in cols


def test_dry_run_changes_nothing(tmp_path):
    db_path = tmp_path / "r.db"; make_old_db(db_path)
    subprocess.run([sys.executable, "scripts/migrate_resource_model.py",
                    "--db", str(db_path), "--phase", "add"], capture_output=True)
    db = sqlite3.connect(db_path)
    cols = {c[1] for c in db.execute("PRAGMA table_info(service_deployments)")}
    assert "layer" not in cols
