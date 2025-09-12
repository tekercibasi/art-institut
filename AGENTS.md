# AGENTS.md

This document defines how humans and AI agents should work in this repo.

## Purpose

- Host a minimal overview/landing page for Art Institut.
- Run Kimai (time tracking) and Nextcloud (files) via Docker Compose.
- Expose services behind Nginx Proxy Manager (NPM) at `cloud.art-institut.de`.

## Scope & Guardrails

- Only touch files under `/home/art-institut` unless explicitly instructed.
- Do not change `/home/nginx-proxy` or other stacks unless asked.
- Never commit secrets. Use a local `.env` (untracked) for overrides. See `.env.example`.
- Keep changes minimal, focused, and reversible. Prefer additive diffs.
- Avoid destructive actions (e.g., `docker system prune`, `rm -rf`) unless approved.

## Key Files

- `docker-compose.yaml`: Defines `overview`, `kimai(+db)`, `nextcloud(+db)` services.
- `web/index.html`: Landing page with service links.
- `README.md`: Quick start and reverse proxy notes.
- `.gitignore`: Keep noise and secrets out of VCS.

## Environments & Networks

- Docker and Docker Compose must be available on the host.
- External network `proxy_net` is created by Nginx Proxy Manager and is required.
- DNS `cloud.art-institut.de` points to this host (202.61.248.115).

## Reverse Proxy (NPM) Expectations

Create a Proxy Host for `cloud.art-institut.de` with these locations:

1) `/` → `http://art-institut-overview:80`
2) `/kimai` → `http://art-institut-kimai:8001`
3) `/nextcloud` → `http://art-institut-nextcloud:80`

Enable SSL via Let’s Encrypt in NPM for `cloud.art-institut.de`.

Notes:
- Nextcloud is set to subpath with `OVERWRITEWEBROOT=/nextcloud` and trusted host/protocol env vars.
- Kimai generally works under a subpath if the proxy preserves the prefix and forwards `X-Forwarded-*` headers (NPM does by default). If asset paths break, ensure both `/kimai` and `/kimai/` forward as-is; consider a subdomain fallback if needed.

## Typical Tasks

1) Edit overview landing page
   - File: `web/index.html`
   - Keep it lightweight (no build steps). Inline CSS is acceptable.

2) Adjust containers/services
   - File: `docker-compose.yaml`
   - Stick to official images, minimal env vars, named volumes for persistence.
   - Keep all services on `proxy_net` for NPM visibility.

3) Bring services up/down
   - `cd /home/art-institut`
   - Up: `docker compose up -d`
   - Down: `docker compose down` (does not remove volumes by default)
   - Restart single service: `docker compose restart overview` (or `kimai`, `nextcloud`)
   - Logs: `docker compose logs -f <service>`

4) Validate changes
   - `docker compose config` to lint YAML.
   - Ensure containers are `running` via `docker ps`.
   - Confirm services are attached to `proxy_net`.

## Secrets & Configuration

- Use a local `.env` file next to `docker-compose.yaml` (copy from `.env.example`).

```
KIMAI_DB_ROOT_PASSWORD=...
KIMAI_DB_NAME=kimai
KIMAI_DB_USER=kimai
KIMAI_DB_PASSWORD=...

NEXTCLOUD_DB_ROOT_PASSWORD=...
NEXTCLOUD_DB_NAME=nextcloud
NEXTCLOUD_DB_USER=nextcloud
NEXTCLOUD_DB_PASSWORD=...
```

- Never commit `.env`. `.gitignore` should keep it untracked.

### Rotating leaked secrets

- If any password was committed, assume compromise. Replace in `.env` with strong values and rotate in the running services:
  - Fresh install: `docker compose down -v && docker compose up -d` (drops DB volumes)
  - Preserve data: update users in MariaDB via `ALTER USER ... IDENTIFIED BY ...;`, then restart services.

## Git Workflow

- Default branch: `main`.
- Small, focused commits with clear messages (present tense, imperative mood).
- Avoid creating branches unless requested by the maintainer.

Commit message examples:
- `feat(overview): add link styles and favicon`
- `chore(compose): bump nextcloud image to apache variant`
- `fix(kimai): set TRUSTED_HOSTS for cloud.art-institut.de`

## HTML Style Guide (overview)

- Keep markup simple and accessible. No frameworks.
- Prefer inline CSS for small adjustments; avoid external assets when possible.
- Open external links in new tabs with `rel="noopener noreferrer"`.

## Compose Conventions

- Use official images (`nginx:alpine`, `kimai/kimai2:apache`, `nextcloud:apache`, `mariadb:10.11`).
- Persist data via named volumes only; do not bind-mount application data.
- Join services that need proxying to `proxy_net`.
- Use explicit container names prefixed with `art-institut-...`.

## Safety Checklist (before pushing)

- `docker compose config` passes with no errors.
- `docker compose up -d` starts all services without crash loops.
- `docker ps` shows containers healthy (where applicable).
- Landing page loads locally via `curl http://art-institut-overview` on the Docker network host.
- NPM has routes for `/`, `/kimai`, `/nextcloud`; SSL green at `cloud.art-institut.de` once DNS/ACME ready.

## Future Enhancements (optional)

- Add healthchecks for services to improve orchestration.
- Provide `nginx.conf` overrides for Kimai/Nextcloud subpath hardening if needed.
- Automate NPM host creation via its API (requires credentials; do not commit).
