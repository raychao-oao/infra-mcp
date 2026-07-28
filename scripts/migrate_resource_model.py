#!/usr/bin/env python3
"""Two-phase migration from the old five-path-column schema to the new
layer/roots/overrides schema on service_deployments.

Pure stdlib, single file, no repo imports — safe to scp to the server and
run standalone.

Phase "add" (safe to run while the OLD code is still live, and safe to
re-run — every step checks what's already done before doing it again):
    - backs up the DB file
    - ALTER TABLE ADD COLUMN, one at a time, only for columns that are
      still missing (layer, project_root, deploy_root, workspace_url,
      path_overrides) — safe to resume after a crash mid-migration
    - backfills each row: classifies layer from deployed_at, derives roots
      for STANDARD rows, carries non-conventional path values into
      path_overrides (JSON) — including a non-conventional app_path —
      drops values that match convention (trailing slash ignored), and
      drops everything for NONSTANDARD rows (old values only appear in
      the report)
    - runs a final sweep UPDATE to backfill layer for any row that is
      still NULL after the per-row loop (e.g. rows inserted by
      still-live old code between snapshot and migration)
    - creates the ix_service_deployments_layer index

Phase "drop" (only run after the NEW code is live):
    - refuses to run unless phase add has fully completed: all five new
      columns must exist AND no row may have layer IS NULL
    - backs up the DB file
    - ALTER TABLE DROP COLUMN x5 (app_path, static_path, data_path,
      log_path, config_path) — requires SQLite >= 3.35

Both phases default to dry-run (report only, no DB changes) unless
--execute is passed.
"""
import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime

TABLE = "service_deployments"

ADD_COLUMNS = [
    ("layer", "TEXT"),
    ("project_root", "TEXT"),
    ("deploy_root", "TEXT"),
    ("workspace_url", "TEXT"),
    ("path_overrides", "TEXT"),
]

DROP_COLUMNS = ["app_path", "static_path", "data_path", "log_path", "config_path"]

# Matches /home/<anyuser>/PRJ/... so it can be normalized to ~/PRJ/...
# regardless of which account the path was recorded under.
HOME_PREFIX_RE = re.compile(r"^/home/[^/]+/(PRJ/.*)$")
STATIC_PATH_RE = re.compile(r"^/var/www/")


def backup_db(db_path):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{db_path}.bak-{ts}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def paths_equal(a, b):
    """Compare two path-like strings ignoring a trailing slash difference."""
    if a is None or b is None:
        return a == b
    return a.rstrip("/") == b.rstrip("/")


def normalize_app_path(app_path):
    """Rewrite /home/<user>/PRJ/... to ~/PRJ/... so real-world absolute
    paths (recorded under whichever account deployed them) compare equal
    to the ~/PRJ/ convention regardless of username."""
    if app_path is None:
        return None
    m = HOME_PREFIX_RE.match(app_path)
    if m:
        return "~/" + m.group(1)
    return app_path


def convention_paths(project, project_root):
    """Convention-derived app/data/config/log paths for a given project_root."""
    root = project_root or f"~/PRJ/{project}/"
    return {
        "app": f"{root}app/",
        "data": f"{root}data/",
        "config": f"{root}config/",
        "log": f"/var/log/{project}/",
    }


def derive_project_root(project, app_path):
    """Derive project_root from app_path.

    Returns (project_root, guessed) where guessed is True when app_path
    gave no ~/PRJ/ evidence and we fell back to ~/PRJ/{project}/.
    """
    normalized = normalize_app_path(app_path)
    if normalized and normalized.startswith("~/PRJ/"):
        segments = normalized.split("/")
        # ['~', 'PRJ', '<project-segment>', ...]
        if len(segments) > 2 and segments[2]:
            return f"~/PRJ/{segments[2]}/", False
    return f"~/PRJ/{project}/", True


def derive_deploy_root(static_path):
    if static_path and STATIC_PATH_RE.match(static_path):
        return static_path
    return None


def classify_row(row):
    """row is a sqlite3.Row (or dict) with the old columns.

    Returns (layer, project_root, deploy_root, path_overrides_dict,
             ghosts_dropped, project_root_guessed)
    """
    project = row["project"]
    deployed_at = row["deployed_at"]
    app_path = row["app_path"]
    static_path = row["static_path"]
    data_path = row["data_path"]
    config_path = row["config_path"]
    log_path = row["log_path"]

    ghosts_dropped = 0
    project_root_guessed = False

    if deployed_at:
        layer = "STANDARD"
        project_root, project_root_guessed = derive_project_root(project, app_path)
        deploy_root = derive_deploy_root(static_path)
        conv = convention_paths(project, project_root)

        overrides = {}
        old_vals = {
            "app": normalize_app_path(app_path),
            "data": data_path,
            "config": config_path,
            "log": log_path,
        }
        for key, old_val in old_vals.items():
            if old_val is None:
                continue
            if paths_equal(old_val, conv[key]):
                ghosts_dropped += 1
            else:
                overrides[key] = old_val
        path_overrides = overrides or None
    else:
        layer = "NONSTANDARD"
        project_root = None
        deploy_root = None
        path_overrides = None
        # every old path value present is a "ghost" for a never-deployed row
        for old_val in (app_path, static_path, data_path, config_path, log_path):
            if old_val is not None:
                ghosts_dropped += 1

    return layer, project_root, deploy_root, path_overrides, ghosts_dropped, project_root_guessed


def phase_add(db_path, execute):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    existing_cols = {c[1] for c in db.execute(f"PRAGMA table_info({TABLE})")}
    missing_cols = [col for col, _ in ADD_COLUMNS if col not in existing_cols]

    rows = list(db.execute(
        "SELECT deployment_id, project, service, server, status, deployed_at, "
        "app_path, static_path, data_path, config_path, log_path "
        f"FROM {TABLE}"
    ))

    print(f"== phase add: {len(rows)} record(s) in {TABLE} ==")
    if missing_cols:
        print(f"columns to add: {', '.join(missing_cols)}")
    else:
        print("all new columns already present — will backfill in place.")

    summary = {"STANDARD": 0, "NONSTANDARD": 0, "ghosts_dropped": 0, "project_root_guessed": 0}
    plan = []
    for row in rows:
        layer, project_root, deploy_root, path_overrides, ghosts, guessed = classify_row(row)
        summary[layer] += 1
        summary["ghosts_dropped"] += ghosts
        if guessed:
            summary["project_root_guessed"] += 1
        plan.append((row, layer, project_root, deploy_root, path_overrides))

        old = {
            "app_path": row["app_path"], "static_path": row["static_path"],
            "data_path": row["data_path"], "config_path": row["config_path"],
            "log_path": row["log_path"],
        }
        new = {
            "layer": layer, "project_root": project_root,
            "deploy_root": deploy_root, "path_overrides": path_overrides,
        }
        print(f"  {row['project']}/{row['service']}@{row['server']}: "
              f"layer={layer}, old={old} -> new={new}")

    print(f"-- summary: STANDARD={summary['STANDARD']} "
          f"NONSTANDARD={summary['NONSTANDARD']} "
          f"ghost_values_dropped={summary['ghosts_dropped']} "
          f"project_root_guessed={summary['project_root_guessed']}")

    if not execute:
        print("(dry-run — no changes made; pass --execute to apply)")
        db.close()
        return

    backup_path = backup_db(db_path)
    print(f"backed up DB to {backup_path}")

    # Add only the columns that are still missing — safe to resume after a
    # crash left a partial set of ALTERs applied (each ALTER autocommits).
    for col, coltype in ADD_COLUMNS:
        if col not in existing_cols:
            db.execute(f"ALTER TABLE {TABLE} ADD COLUMN {col} {coltype}")

    for row, layer, project_root, deploy_root, path_overrides in plan:
        db.execute(
            f"UPDATE {TABLE} SET layer=?, project_root=?, deploy_root=?, "
            "path_overrides=? WHERE deployment_id=?",
            (layer, project_root, deploy_root,
             json.dumps(path_overrides) if path_overrides is not None else None,
             row["deployment_id"]),
        )

    # Safety-net sweep: any row still left with layer IS NULL (e.g. written
    # by still-live old code between the snapshot and this run, or missed
    # for any other reason) gets classified from deployed_at alone so the
    # drop-phase guard never finds a straggler.
    db.execute(
        f"UPDATE {TABLE} SET layer = CASE WHEN deployed_at IS NOT NULL "
        "THEN 'STANDARD' ELSE 'NONSTANDARD' END WHERE layer IS NULL"
    )

    db.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_layer ON {TABLE} (layer)"
    )

    db.commit()
    db.close()
    print("phase add: applied.")


def phase_drop(db_path, execute):
    assert sqlite3.sqlite_version_info >= (3, 35, 0), (
        f"SQLite {sqlite3.sqlite_version} does not support DROP COLUMN "
        "(need >= 3.35.0)"
    )

    db = sqlite3.connect(db_path)

    existing_cols = {c[1] for c in db.execute(f"PRAGMA table_info({TABLE})")}
    missing_new_cols = [col for col, _ in ADD_COLUMNS if col not in existing_cols]
    if missing_new_cols:
        print(f"ERROR: phase add has not fully run — missing columns: "
              f"{', '.join(missing_new_cols)}", file=sys.stderr)
        db.close()
        sys.exit(1)

    null_layer_count = db.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE layer IS NULL"
    ).fetchone()[0]
    if null_layer_count:
        print(f"ERROR: {null_layer_count} row(s) still have layer IS NULL — "
              "rerun phase add first", file=sys.stderr)
        db.close()
        sys.exit(1)

    to_drop = [c for c in DROP_COLUMNS if c in existing_cols]

    print(f"== phase drop: dropping {len(to_drop)} column(s) from {TABLE} ==")
    for col in to_drop:
        print(f"  DROP COLUMN {col}")
    if not to_drop:
        print("  (nothing to drop — already migrated)")

    if not execute:
        print("(dry-run — no changes made; pass --execute to apply)")
        db.close()
        return

    backup_path = backup_db(db_path)
    print(f"backed up DB to {backup_path}")

    for col in to_drop:
        db.execute(f"ALTER TABLE {TABLE} DROP COLUMN {col}")

    db.commit()
    db.close()
    print("phase drop: applied.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to the SQLite DB file")
    parser.add_argument("--phase", required=True, choices=["add", "drop"])
    parser.add_argument("--execute", action="store_true",
                         help="apply changes (default is dry-run)")
    args = parser.parse_args()

    if args.phase == "add":
        phase_add(args.db, args.execute)
    else:
        phase_drop(args.db, args.execute)


if __name__ == "__main__":
    main()
