# Contributing to the Art Institut Stack

Thanks for helping maintain the overview, Kimai, and Nextcloud setup. This guide explains local setup, workflow, and expectations.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ and npm (required for commit hooks)

### Setup
1. Clone/copy the repo on the target host.
2. Create `.env` from `.env.example` and fill in **strong** passwords, SMTP creds, Redis password, etc. `.env` is gitignored.
3. Bring services online:
   ```bash
   cd /home/art-institut
   docker compose up -d
   ```
4. Install dev tooling and Git hooks:
   ```bash
   npm install
   npm run prepare
   ```
5. Ensure Nginx Proxy Manager maps the public domains. Typical proxy rules:
   - `nextcloud.art-institut.de` → `http://art-institut-nextcloud`
   - `kimai.art-institut.de` → `http://art-institut-kimai:8001`
   - `cloud.art-institut.de` → `http://art-institut-overview`

### Services
- `art-institut-overview`: static landing page (nginx)
- `art-institut-kimai` + `art-institut-kimai-db` + `art-institut-redis`: time tracking
- `art-institut-nextcloud` + `art-institut-nextcloud-db`: files

## Development Workflow

- Edit landing page: `web/index.html`
- Compose changes: `docker-compose.yaml` and `.env`
- Docs: update `README.md` / `AGENTS.md` when behavior changes
- Apply Nextcloud changes via `occ`; apply Kimai changes via `/opt/kimai/bin/console`

### Useful Commands
```bash
docker compose config              # lint compose file
docker compose up -d service       # recreate single service
docker compose logs -f nextcloud   # follow logs
# Nextcloud CLI example
docker exec -it art-institut-nextcloud \
  bash -lc "su -s /bin/sh www-data -c 'php occ status'"
# Kimai CLI example
docker exec -it art-institut-kimai /opt/kimai/bin/console kimai:mail:test you@example.com
```

## Commit Messages

We follow Conventional Commits:
- Format: `<type>(<scope>): <subject>`
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- Scopes (suggested): `compose`, `nextcloud`, `kimai`, `docs`, `infra`, `overview`, `repo`
- Subject: imperative, present tense, <= ~100 chars
- Body (optional): why/how, bullets if helpful

Examples:
- `feat(nextcloud): enable redis locking`
- `fix(kimai): configure smtp credentials`
- `docs(repo): add contributing guide`

## Branching / PRs

- Work off `main` or the branch requested by maintainers.
- Keep changes small and documented.
- Include screenshots when UI changes (overview page) are made.

## Coding & Ops Guidelines

- Never commit `.env` or secrets.
- Minimal changes only; respect running services.
- After Docker changes, confirm containers are healthy (`docker ps`) and web apps respond.
- Prefer additive updates; avoid deleting volumes or data.

## Testing & Verification

Before pushing:
1. `docker compose config`
2. Restart affected services: `docker compose up -d <service>`
3. Check logs for warnings (`docker compose logs -f <service>`)
4. Load endpoints in browser or via curl:
   - `curl -kI https://nextcloud.art-institut.de`
   - `curl -kI https://kimai.art-institut.de`
5. For large changes, notify maintainers before deploying to production.

## Support / Questions

- Operational owner: Art Institut infrastructure team (Michael Tschoepke & Akin Tekercibasi).
- For DNS/SSL issues, coordinate with the Nginx Proxy Manager maintainers.

Thanks for keeping the Art Institut services running smoothly!
