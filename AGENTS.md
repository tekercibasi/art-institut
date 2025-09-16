# Agent Guide for Art Institut

This file captures the context and house rules for anyone (human or AI) updating this repository. Scope: everything under `/home/art-institut`.

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

## Safety Checklist

Before declaring work done:
1. `cd /home/art-institut` and run `docker compose config`.
2. `docker compose up -d` (or restart specific services) and ensure containers stay healthy.
3. `docker ps` confirms status/health checks.
4. For UI updates, load `https://nextcloud.art-institut.de` and `https://kimai.art-institut.de`.
5. Keep an eye on `docker logs art-institut-nextcloud` and `art-institut-kimai` for new warnings.

## Do / Don’t

Do:
- Limit changes to this repo unless asked.
- Update docs when workflows change.
- Use Conventional Commit style messages (see CONTRIBUTING).

Don’t:
- Touch `/home/nginx-proxy` or other project folders without explicit instructions.
- Commit `.env`, backups, or generated logs.
- Run destructive Docker commands (`system prune`, `down -v`) unless owners confirm.

## Handy Commands

- Start/stop: `docker compose up -d`, `docker compose down`
- Restart single service: `docker compose restart kimai`
- Logs: `docker compose logs -f nextcloud`
- Nextcloud CLI: `docker exec -it art-institut-nextcloud bash -lc 'su -s /bin/sh www-data -c "php occ <cmd>"'`
- Kimai CLI: `docker exec -it art-institut-kimai /opt/kimai/bin/console <cmd>`

## Operational Memory (2025-09)

- Certificates for public hosts are managed by NPM (Let’s Encrypt). Renewals run there.
- Nextcloud is on version 31.0.9, using Redis for locking, SMTP configured, and maintenance window at 02:00.
- Kimai is on 2.38.0 with SMTP/Redis configured; health check: ensure `kimai` service stays healthy.
- Named volumes: `kimai_db_data`, `kimai_public`, `kimai_var`, `nextcloud_db_data`, `nextcloud_data`, `redis_data`.

Keep this guide updated when the infrastructure or workflows change.
