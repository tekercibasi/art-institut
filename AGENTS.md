# Agent Guide for Art Institut

This file captures the context and house rules for anyone (human or AI) updating this repository. Scope: everything under `<ART_ROOT>` (deployment path placeholder).

> Placeholder legend: `<ART_ROOT>` denotes the private deployment directory for this stack, `<NPM_ROOT>` references the shared Nginx Proxy Manager project path.

## Principles

- Keep the production services (Nextcloud, Kimai, overview page) online and stable.
- Make focused, reversible changes; avoid touching neighbouring stacks unless requested.
- Never commit or leak secrets. All credentials live in the untracked `.env`.

## Project Layout

- `docker-compose.yaml` – defines the overview, Kimai, Nextcloud, Redis, and MariaDB services.
- `web/index.html` – landing page with shortcuts to services.
- `.env` – runtime secrets (ignored by git). See `.env.example` for the shape.
- `README.md` – quick start and proxy notes.

## Operations & Infrastructure

- Reverse proxy: Nginx Proxy Manager (outside this repo) on network `proxy_net`.
- Public endpoints
  - `nextcloud.art-institut.de` → `art-institut-nextcloud`
  - `kimai.art-institut.de` → `art-institut-kimai`
  - `cloud.art-institut.de` (overview) handled in NPM.
- Docker networks: services join `proxy_net` for NPM and the project’s default network for DB/Redis.
- Persistence: all app and DB data use named volumes; do **not** replace with bind mounts unless agreed.

### Service Notes

- Kimai runs on Apache (port 8001 internally) and relies on MariaDB + Redis + SMTP.
- Nextcloud uses MariaDB and Redis (locking). Config tweaks belong in `config/config.php` via `occ`.
- Redis password is set via `.env` → `REDIS_PASSWORD` and consumed by both Redis and Nextcloud.
- SMTP should be configured in both apps before going live; test via CLI (Kimai `kimai:mail:test`, Nextcloud `occ mail:test`).
- TURN (`art-institut-turn`) provides STUN/TURN services for Talk; keep DNS for `${TURN_DOMAIN}` pointing at this host and rotate `TURN_SHARED_SECRET` via `.env` when needed.
- Nextcloud server-side encryption (master key) is enabled; keep backups of `/var/www/html/data/files_encryption/` and avoid disabling encryption once in use.
- TURN certificates live under /etc/letsencrypt/live/turn.art-institut.de/ and are mounted into the TURN container; renewals are handled by certbot (standalone).

### User provisioning

- Use `<ART_ROOT>/scripts/provision_user.py` to create coordinated accounts in Nextcloud and Kimai:

```bash
<ART_ROOT>/scripts/provision_user.py \
    --email user@example.com \
    --first-name Alice \
    --last-name Example
```

- The script derives a unique username, creates accounts in both systems, and prints the generated password. Optional `--kimai-roles` (comma-separated) overrides the default `ROLE_USER`.
- It refuses to proceed if the email already exists in either system.
- If `NETCUP_*` environment variables are set and the Python `zeep` package is installed, the script also creates the Netcup mailbox automatically. Otherwise, create the mailbox manually in the CCP.
- Nach der Anlage wird die Nextcloud-Oberfläche standardmäßig auf Deutsch (`language=de`, `locale=de_DE`) gesetzt.

### Backup & Restore

- Automated full-system backups run every 15 minutes via `<ART_ROOT>/scripts/backup.py` (see cron entry). Archives land in `<ART_ROOT>/backups` with tiered retention.
- Manual usage:
  - `python scripts/backup.py run` — create backup immediately (also prunes old ones)
  - `python scripts/backup.py list` — show available archives (newest first)
  - `python scripts/backup.py check [FILE]` — verify archive integrity (default: latest)
- Each archive contains: Kimai + Nextcloud SQL dumps, all Docker volumes, git tree snapshot, and `/var/www/html/data/files_encryption/`.
- Restore outline (document details in private runbook):
  1. Unpack archive on target host (`tar --zstd -xf ...`)
  2. Recreate named Docker volumes and load tarballs (`docker run --rm -v volume:/restore busybox tar xzf -`)
  3. Import SQL dumps into fresh MariaDB containers
  4. Restore `/var/www/html/data/files_encryption/` into the Nextcloud data path before first start
  5. Copy repo files into `<ART_ROOT>` (respect permissions) and start stack (`docker compose up -d`)
- Keep off-site copies of `backups/*.tar.zst` regularly (e.g., download to Google Drive) and ensure `backup.log` is rotated.

### Monitoring & Ops Notes

- Server: 4 vCPU / 16 GB RAM / 320 GB disk (Netcup RS class). Watch `docker stats`, `htop`, and Nextcloud admin monitoring for saturation.
- Logs to watch: `docker compose logs nextcloud`, `docker compose logs kimai`, `docker logs art-institut-turn`, `<ART_ROOT>/backups/backup.log`.
- Cron jobs (root):
  - `*/5 * * * * docker exec -u www-data art-institut-nextcloud php occ system:cron >/dev/null 2>&1`
- `*/15 * * * * <ART_ROOT>/scripts/backup.py run >> <ART_ROOT>/backups/backup.log 2>&1`
- SSL: Web endpoints via NPM (Let’s Encrypt); TURN/STUN via standalone certbot (`/etc/letsencrypt/live/turn.art-institut.de/`). Renewals auto-run, but monitor expiry.
- Security: `.env` is untracked; update `.env.example` when variables change so new deployments match current config.

## Safety Checklist

Before declaring work done:
1. `cd <ART_ROOT>` and run `docker compose config`.
2. `docker compose up -d` (or restart specific services) and ensure containers stay healthy.
3. `docker ps` confirms status/health checks.
4. For UI updates, load `https://nextcloud.art-institut.de` and `https://kimai.art-institut.de`.
5. Keep an eye on `docker logs art-institut-nextcloud` and `art-institut-kimai` for new warnings.

## Do / Don’t

Do:
- Limit changes to this repo unless asked.
- Update docs when workflows change.
- Run `npm install && npm run prepare` after cloning so Husky hooks work.
- Use Conventional Commit style messages (see CONTRIBUTING).

Don’t:
- Touch `<NPM_ROOT>` or other project folders without explicit instructions.
- Commit `.env`, backups, or generated logs.
- Run destructive Docker commands (`system prune`, `down -v`) unless owners confirm.

## Handy Commands

- Start/stop: `docker compose up -d`, `docker compose down`
- Restart single service: `docker compose restart kimai`
- Logs: `docker compose logs -f nextcloud`
- Nextcloud CLI: `docker exec -it art-institut-nextcloud bash -lc 'su -s /bin/sh www-data -c "php occ <cmd>"'`
- Kimai CLI: `docker exec -it art-institut-kimai /opt/kimai/bin/console <cmd>`
- TURN CLI: `docker logs -f art-institut-turn`
- Cron: root crontab runs `docker exec -u www-data art-institut-nextcloud php occ system:cron` every 5 minutes and `<ART_ROOT>/scripts/backup.py run` every 15 minutes (logging to `backups/backup.log`). Adjust via `crontab -e`.

## Operational Memory (2025-09)

- Certificates for public hosts are managed by NPM (Let’s Encrypt). Renewals run there.
- Nextcloud is on version 31.0.9, using Redis for locking, SMTP configured, and maintenance window at 02:00.
- Kimai is on 2.38.0 with SMTP/Redis configured; health check: ensure `kimai` service stays healthy.
- Named volumes: `kimai_db_data`, `kimai_public`, `kimai_var`, `nextcloud_db_data`, `nextcloud_data`, `redis_data`.

Keep this guide updated when the infrastructure or workflows change.
