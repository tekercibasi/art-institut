#!/usr/bin/env python3
"""Unified backup utility for the Art Institut stack.

Creates compressed archives that include:
  * Database dumps (Kimai & Nextcloud)
  * Docker volume snapshots
  * Nextcloud encryption master key directory
  * Repository configuration (git working tree)

Also enforces tiered retention:
  - every 15 minutes for last 2 hours
  - every 30 minutes for last 24 hours
  - every day for last 14 days
  - every 5 days for last 30 days
  - every 30 days beyond that

Usage:
  python backup.py run        # create backup & prune old ones
  python backup.py list       # list stored backups with age
  python backup.py check [FILE]  # verify archive (default latest)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_NAME = REPO_ROOT.name
BACKUP_ROOT = REPO_ROOT / "backups"
STAGING_PREFIX = "staging"
BACKUP_PREFIX = "art-institut-backup"
COMPOSE_DIR = REPO_ROOT
REPO_EXCLUDES = [f'{PROJECT_NAME}/backups', f'{PROJECT_NAME}/node_modules', '*.pyc', '__pycache__']

KIMAI_DB_CONTAINER = "art-institut-kimai-db"
NEXTCLOUD_DB_CONTAINER = "art-institut-nextcloud-db"
NEXTCLOUD_APP_CONTAINER = "art-institut-nextcloud"

VOLUMES = {
    "kimai_db_data": "art-insitut_kimai_db_data",
    "kimai_public": "art-insitut_kimai_public",
    "kimai_var": "art-insitut_kimai_var",
    "nextcloud_data": "art-insitut_nextcloud_data",
    "nextcloud_db_data": "art-insitut_nextcloud_db_data",
    "redis_data": "art-insitut_redis_data",
}

RETENTION_RULES: List[Tuple[Optional[dt.timedelta], dt.timedelta]] = [
    (dt.timedelta(hours=2), dt.timedelta(minutes=15)),
    (dt.timedelta(days=1), dt.timedelta(minutes=30)),
    (dt.timedelta(days=14), dt.timedelta(days=1)),
    (dt.timedelta(days=30), dt.timedelta(days=5)),
    (None, dt.timedelta(days=30)),
]

@dataclass
class BackupFile:
    path: Path
    timestamp: dt.datetime

    @property
    def age(self) -> dt.timedelta:
        return dt.datetime.utcnow() - self.timestamp


def _run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("check", True)
    return subprocess.run(cmd, **kwargs)


def timestamp_now() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def ensure_dirs() -> None:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


def _dump_database(container: str, output: Path) -> None:
    with output.open("wb") as fh:
        cmd = [
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            "mysqldump -u\"$MYSQL_USER\" -p\"$MYSQL_PASSWORD\" \"$MYSQL_DATABASE\"",
        ]
        _run(cmd, stdout=fh)


def _dump_volume(volume: str, destination: Path) -> None:
    with destination.open("wb") as fh:
        cmd = [
            "docker",
            "run",
            "--rm",
            f"-v{volume}:/volume:ro",
            "busybox",
            "tar",
            "czf",
            "-",
            "-C",
            "/volume",
            ".",
        ]
        _run(cmd, stdout=fh)


def _dump_master_key(dest: Path) -> None:
    with dest.open("wb") as fh:
        cmd = [
            "docker",
            "exec",
            NEXTCLOUD_APP_CONTAINER,
            "tar",
            "czf",
            "-",
            "-C",
            "/var/www/html/data",
            "files_encryption",
        ]
        _run(cmd, stdout=fh)


def _dump_repo(dest: Path) -> None:
    exclude_args = []
    for pattern in REPO_EXCLUDES:
        if pattern.startswith(f"{PROJECT_NAME}/"):
            exclude_args.append(f"--exclude={pattern}")
        else:
            exclude_args.append(f"--exclude={PROJECT_NAME}/{pattern}")
    cmd = ["tar", "--zstd", "-cf", str(dest), *exclude_args, "-C", str(COMPOSE_DIR.parent), COMPOSE_DIR.name]
    _run(cmd)


def create_backup() -> Path:
    ensure_dirs()
    timestamp = timestamp_now()
    staging_dir = Path(tempfile.mkdtemp(prefix=f"{STAGING_PREFIX}-{timestamp}-", dir=str(BACKUP_ROOT)))

    try:
        db_dir = staging_dir / "databases"
        db_dir.mkdir()
        _dump_database(KIMAI_DB_CONTAINER, db_dir / "kimai.sql")
        _dump_database(NEXTCLOUD_DB_CONTAINER, db_dir / "nextcloud.sql")

        vol_dir = staging_dir / "volumes"
        vol_dir.mkdir()
        for label, volume in VOLUMES.items():
            _dump_volume(volume, vol_dir / f"{label}.tar.gz")

        master_key = staging_dir / "files_encryption.tar.gz"
        _dump_master_key(master_key)

        repo_file = staging_dir / "repo.tar.zst"
        _dump_repo(repo_file)

        metadata = {
            "timestamp": timestamp,
            "created_utc": dt.datetime.utcnow().isoformat() + "Z",
            "volumes": list(VOLUMES.keys()),
            "files": sorted(str(p.relative_to(staging_dir)) for p in staging_dir.rglob("*")),
        }
        (staging_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

        backup_name = f"{BACKUP_PREFIX}-{timestamp}.tar.zst"
        backup_path = BACKUP_ROOT / backup_name
        _run(["tar", "--zstd", "-cf", str(backup_path), "-C", str(staging_dir), "."])
        return backup_path
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def parse_timestamp(path: Path) -> Optional[dt.datetime]:
    name = path.name
    if name.endswith('.tar.zst'):
        name = name[:-8]
    if not name.startswith(BACKUP_PREFIX + '-'):
        return None
    stamp = name[len(BACKUP_PREFIX) + 1 :]
    try:
        return dt.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def list_backups() -> List[BackupFile]:
    backups: List[BackupFile] = []
    for path in BACKUP_ROOT.glob(f"{BACKUP_PREFIX}-*.tar.zst"):
        ts = parse_timestamp(path)
        if ts:
            backups.append(BackupFile(path=path, timestamp=ts))
    backups.sort(key=lambda b: b.timestamp, reverse=True)
    return backups


def format_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def format_timedelta(delta: dt.timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return sign + " ".join(parts)


def prune_backups(backups: List[BackupFile]) -> List[Path]:
    now = dt.datetime.utcnow()
    keep_slots: Dict[Tuple[int, int], BackupFile] = {}
    keep_paths = set()

    def slot(timestamp: dt.datetime, interval: dt.timedelta) -> int:
        return int(timestamp.timestamp() // interval.total_seconds())

    for backup in backups:
        age = now - backup.timestamp
        for idx, (limit, interval) in enumerate(RETENTION_RULES):
            if limit is None or age <= limit:
                slot_key = (idx, slot(backup.timestamp, interval))
                if slot_key not in keep_slots:
                    keep_slots[slot_key] = backup
                    keep_paths.add(backup.path)
                break

    removed: List[Path] = []
    for backup in backups:
        if backup.path not in keep_paths:
            backup.path.unlink(missing_ok=True)
            removed.append(backup.path)
    return removed


def check_backup(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Backup {path} does not exist")
    _run(["tar", "-tf", str(path)], stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        _run(["tar", "--zstd", "-xf", str(path), "./metadata.json"], cwd=str(tmp))
        meta = json.loads((tmp / "metadata.json").read_text())
        required = {"databases/kimai.sql", "databases/nextcloud.sql", "files_encryption.tar.gz"}
        missing = [item for item in required if item not in meta.get("files", [])]
        if missing:
            raise SystemExit(f"Backup {path} missing items: {missing}")


def cmd_run(_: argparse.Namespace) -> None:
    backup_path = create_backup()
    backups = list_backups()
    removed = prune_backups(backups)
    print(f"Created: {backup_path}")
    if removed:
        for path in removed:
            print(f"Removed old backup: {path}")


def cmd_list(_: argparse.Namespace) -> None:
    ensure_dirs()
    backups = list_backups()
    total_size = sum(int(b.path.stat().st_size) for b in backups if b.path.exists())
    disk_total, _disk_used, disk_free = shutil.disk_usage(str(BACKUP_ROOT))

    print("=== Backup Storage ===")
    print(f"- path: {BACKUP_ROOT}")
    print(f"- total: {format_bytes(disk_total)}")
    print(f"- available: {format_bytes(disk_free)}")
    print(f"- used by backups: {format_bytes(total_size)}")

    if not backups:
        print("\nNo backups present.")
        return

    header_name = "Archive"
    header_time = "Captured (UTC)"
    header_age = "Age"
    line_length = 40 + 21 + len(header_age)

    print("\n=== Stored Archives ===")
    print(f"{header_name:<40} {header_time:<21} {header_age}")
    print("-" * line_length)

    now = dt.datetime.utcnow()
    for backup in backups:
        age = format_timedelta(now - backup.timestamp)
        timestamp_str = backup.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{backup.path.name:<40} {timestamp_str:<21} {age}")


def cmd_check(args: argparse.Namespace) -> None:
    if args.file:
        path = Path(args.file)
    else:
        backups = list_backups()
        if not backups:
            raise SystemExit("No backups available to check")
        path = backups[0].path
    check_backup(path)
    print(f"Backup {path.name} verified")


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Art Institut backup utility")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Create backup and prune old ones")
    run_p.set_defaults(func=cmd_run)

    list_p = sub.add_parser("list", help="List backups")
    list_p.set_defaults(func=cmd_list)

    check_p = sub.add_parser("check", help="Check backup integrity")
    check_p.add_argument("file", nargs="?", help="Backup file to verify")
    check_p.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
