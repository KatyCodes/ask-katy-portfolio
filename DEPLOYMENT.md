# DreamHost Deployment Decision

## Static frontend

Keep the existing KatyCodes homepage in place. Build Ask Katy with a dedicated
asset directory:

```bash
cd frontend
VITE_API_URL=https://api.katycodes.com \
VITE_SITE_URL=https://katycodes.com \
npm run build -- --base=/ask-katy/
```

Upload the contents of `frontend/dist/` to an `ask-katy/` directory inside the
`katycodes.com` document root. Do not upload the repository, database, `.env`,
or backend into the public document root. Python shebangs, CGI headers, and
executable permissions do not apply to these static files.

Merge these narrowly scoped rules into the existing root `.htaccess`; do not
replace unrelated homepage or WordPress rules:

```apache
RewriteEngine On
RewriteRule ^for/[a-z0-9-]+/[a-z0-9-]+/?$ /ask-katy/index.html [L]
RewriteRule ^admin/?$ /ask-katy/index.html [L]
```

Configure the web server to serve `index.html` for `/for/*` and `/admin` so refreshing a React route works. Do not add application URLs to navigation or a sitemap. The HTML includes a `noindex` directive; if DreamHost supports custom response headers, also send `X-Robots-Tag: noindex, nofollow, noimageindex, nosnippet` and `Referrer-Policy: no-referrer` for `/for/*`.

## FastAPI backend decision

The site uses a DreamHost Managed VPS. Run FastAPI as a persistent ASGI application in a dedicated virtual environment on a non-privileged port, then expose it at `api.katycodes.com` through DreamHost's Proxy Server. CGI and FastCGI entry files are not part of this design.

Deployment will use:

- A custom supported Python installation and virtual environment
- Uvicorn for the ASGI process during the MVP
- A non-privileged port in DreamHost's documented proxy range
- DreamHost Proxy Server for the public HTTPS subdomain
- A user-level persistent process configuration so the API restarts after failure or reboot
- Environment variables or a protected environment file outside the public web directory
- `ASK_KATY_ERROR_LOG_PATH` pointing to a private log directory outside the public web root
- Exact CORS access for `https://katycodes.com`
- `ASK_KATY_TRUST_PROXY=true` so the local API can rate-limit the original visitor address supplied by DreamHost's proxy
- One Uvicorn worker for the in-memory MVP rate limiter; use a shared rate-limit store before adding multiple workers

## Production checks

- Confirm the panel exposes Proxy Server for the VPS.
- Record `which python3` after the custom environment is active.
- Confirm the chosen port and health endpoint through the proxy.
- Verify cookies, CORS, outbound HTTPS to OpenAI, timeouts, and restart behavior.
- Verify a rate-limited request returns `429` and a friendly retry message through the proxy.
- Trigger a controlled test failure, confirm the browser shows only its reference ID, and confirm the matching private log entry is readable only by the server account.
- Keep private application content and logs outside the static site's document root.
- Set `ASK_KATY_DATABASE_PATH` to a private absolute path outside the document root.
- Keep the tested nightly SQLite backup job installed and periodically restore a
  snapshot into a temporary database to confirm it remains usable.
- Confirm `/for/company/job-title` refreshes directly and is absent from the sitemap.

## One-command code updates

The initial server setup is complete. Routine code and design changes deploy from the project root with:

```bash
./deploy.sh
```

The local `.deploy.env` is intentionally ignored by Git. It contains only the DreamHost hostname, shell username, SSH port, and path to the dedicated deployment key. Start from `.deploy.env.example`; never add passwords, API keys, or private application content.

Before uploading, the deployer requires committed code, runs Pytest and Vitest, builds Vite with the production API URL and `/ask-katy/` base path, and creates explicit archives. The backend archive is limited to `backend/app/` and `backend/pyproject.toml`. The frontend archive is limited to `frontend/dist/`.

The server installer:

- verifies the expected application, virtual environment, supervisor configuration, and release contents;
- installs Python dependency changes inside the existing virtual environment;
- moves the current backend and frontend into a private versioned backup;
- swaps in the new code without replacing the backend `.env`, virtual environment, database, logs, or root `.htaccess`;
- restarts the `ask-katy` Supervisor process;
- checks `https://api.katycodes.com/v1/health` and `https://katycodes.com/admin`;
- restores the previous backend and frontend automatically if a swap, restart, or health check fails.

Backups remain outside the web root under `private/ask-katy/deploy-backups/`. The deployer does not automatically delete them.

To exercise tests, the production build, and archive validation without connecting to the VPS, run:

```bash
./deploy.sh --prepare-only
```

Career facts, skills, company notes, application pages, corrected answers, and publishing controls live in the production SQLite database. Update those through `/admin`; they take effect without a code deployment.

## Nightly database backups

Run `scripts/install-production-backup.sh` once as the application shell user after
the backup module has been deployed. The installer first creates a verified snapshot
through SQLite's online backup API, then adds one marked cron entry. Rerunning it is
safe and replaces only that marked entry.

The job runs at 2:17 a.m. server time, keeps the newest 30 snapshots, and stores both
backups and its small log under `private/ask-katy/`, outside the public web root. The
backup directory is mode `700`; each snapshot and the log are mode `600`. Inspect the
schedule and snapshots with:

```bash
crontab -l
ls -lh ~/private/ask-katy/database-backups/
tail -n 20 ~/private/ask-katy/logs/ask-katy.backup.log
```
