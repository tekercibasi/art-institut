# Art Institut – Infrastructure

This repo holds the overview page and Docker setup for:

- Overview page (static) served by an `nginx` container
- Kimai (time tracking)
- Nextcloud (files)
- TURN/STUN relay for Nextcloud Talk

Reverse-proxy is handled by Nginx Proxy Manager running on this host at `/home/nginx-proxy`.

## Prerequisites

- Docker + Docker Compose installed
- The external Docker network `proxy_net` already exists (created by Nginx Proxy Manager compose)
- DNS `cloud.art-institut.de` already points to this server (202.61.248.115)

## Quick start

1) Create a .env file

Copy `.env.example` to `.env` and set STRONG passwords. Do not commit `.env`.

2) Bootstrap containers

```bash
cd /home/art-institut
docker compose up -d
```

3) Create/adjust Proxy Host in Nginx Proxy Manager (GUI)

Create a Proxy Host for `cloud.art-institut.de` with these locations:

- Location `/` → Forward to `http://art-institut-overview:80`
- Location `/kimai` → Forward to `http://art-institut-kimai:8001`
- Location `/nextcloud` → Forward to `http://art-institut-nextcloud:80`

Enable SSL for `cloud.art-institut.de` by requesting a new certificate.

4) Cron job

Ensure the host (root) crontab runs `docker exec -u www-data art-institut-nextcloud php occ system:cron` every 5 minutes. This repository already installs that entry, but verify with `crontab -l`.

5) TURN/STUN DNS & firewall

Point DNS for `turn.art-institut.de` (and optionally `stun.art-institut.de`) at this server. Open UDP/TCP 3478 and the relay port range (defaults 49160–49200/UDP). Configure Talk via `occ talk:turn:add`/`talk:stun:add` as described in `AGENTS.md`.

Notes:
- For Nextcloud sub-path operation, this compose sets `OVERWRITEWEBROOT=/nextcloud` and trusted host/protocol vars.
- Kimai works behind a reverse proxy. If assets don’t load under `/kimai`, add a custom location in NPM that forwards both `/kimai` and `/kimai/` with path prefix kept; Kimai 2 supports subdirectory when the proxy preserves the path. If you still see issues, consider adding `X-Forwarded-*` headers (NPM does by default) or running Kimai on a subdomain.

## Rotating credentials

- Fresh setup (no data to keep):
  - Update strong passwords in `.env`
  - `docker compose down -v` (drops DB volumes)
  - `docker compose up -d`
- Keep data:
  - Change MariaDB passwords inside the DBs (e.g., `ALTER USER ... IDENTIFIED BY ...;` for root and app users)
  - Update the same values in `.env`
  - Restart services: `docker compose restart kimai kimai-db nextcloud nextcloud-db`

## Data persistence

Named volumes:
- `kimai_db_data`, `kimai_public`, `kimai_var`
- `nextcloud_db_data`, `nextcloud_data`

You can override DB credentials with environment variables in your shell or a `.env` file next to the compose file.

## Development

- Edit the overview landing page in `web/index.html`.
- After changes, restart the overview container:

```bash
docker compose restart overview
```

## Git

This folder is initialized as a git repository. Set the remote to `tekercibasi/art-institut` when the remote repo exists, then push:

```bash
cd /home/art-institut
git remote add origin https://github.com/tekercibasi/art-institut.git
git push -u origin main
```

Security: never commit secrets. `.env` is ignored via `.gitignore`.
