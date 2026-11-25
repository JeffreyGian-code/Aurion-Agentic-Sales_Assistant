# EC2 deployment quick reference

## Update after pulling from GitHub

Run on EC2 as `ubuntu`. These commands assume the existing systemd, PM2,
Nginx, and Docker setup described below. Stop if a command fails; fix it
before continuing to the restarts.

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant

# Skip this command if you already pulled the latest changes.
git pull --ff-only

# Update backend dependencies and start PostgreSQL and Chroma.
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --wait

# Install frontend dependencies and create the production build.
cd frontend
npm ci
npm run build

# Restart the frontend only after the build succeeds.
pm2 restart vehicle-frontend
cd ..
sudo systemctl restart vehicle-assistant

# Check the API, frontend, and public site.
sudo systemctl status vehicle-assistant --no-pager
pm2 status
curl -fsS http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1:4173/
curl -fsS https://aurion.duckdns.org/api/health
```

The API health response should be `{"status":"ok"}`. Open
`https://aurion.duckdns.org`, refresh the page, check service status, and try chat.
The basic health endpoint only confirms that the API is running; service status
also checks PostgreSQL and OpenRouter.

## What needs rebuilding or restarting?

| Change | Action |
|---|---|
| Frontend source or dependencies | In `frontend`, run `npm ci`, then `npm run build`, then `pm2 restart vehicle-frontend`. |
| Frontend `VITE_*` environment values | Rebuild and restart the frontend; these values are embedded at build time. |
| Backend source or dependencies | Install `requirements.txt` if dependencies changed, then `sudo systemctl restart vehicle-assistant`. |
| Root `.env` | Restart `vehicle-assistant`. If Compose settings changed, also run `docker compose up -d --wait`. |
| systemd service file | Run `sudo systemctl daemon-reload`, then restart `vehicle-assistant`. |
| Nginx config | Run `sudo nginx -t && sudo systemctl reload nginx`. |
| Database schema or seed files | Existing volumes are not initialized again. Back up the database and apply the specific SQL change deliberately. |
| Documentation only | No build or restart needed. |

## Existing server setup

- Checkout: `/home/ubuntu/Aurion-Agentic-Sales_Assistant`.
- Public domain: `aurion.duckdns.org`; its DNS record must point to the EC2 public IP.
- Nginx handles ports 80/443 and proxies `/` to `127.0.0.1:4173` and `/api/` to `127.0.0.1:8000/api/`.
- Backend: systemd service `vehicle-assistant`, running Uvicorn with one worker.
- Frontend: PM2 process `vehicle-frontend`, running Vite Preview for `frontend/dist`.
- Database: Docker Compose service `postgres`, container `vehicle-pg`, PostgreSQL 18; user `vehicle_app`, database `vehicle_agent`.
- Security group: SSH 22 from your IP; public HTTP 80 and HTTPS 443. Keep 4173, 5173, 8000, and 5432 closed publicly.

For initial installation, complete systemd/Nginx configuration, and HTTPS setup,
see [the full Ubuntu EC2 deployment guide](ec2-ubuntu-deploy.md).

## Frontend configuration and PM2

Keep these values in `frontend/.env.production`:

```dotenv
VITE_API_URL=/api
VITE_USE_MOCK=false
```

`/api` routes browser requests through the site's Nginx proxy. After changing
these values, run `npm run build` and restart PM2. The compiled files are in
`frontend/dist`.

The current repository config does not include the deployed hostname. Ensure
`frontend/vite.config.ts` contains this property inside the existing
`defineConfig({ ... })` object, and retain it when updating the server:

```ts
preview: {
  allowedHosts: ['aurion.duckdns.org'],
},
```

Restart PM2 after editing the config. Commit this setting if you want it retained
in GitHub; an uncommitted server edit can conflict with a later pull.

If `vehicle-frontend` has not been created yet, run this once:

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant/frontend
pm2 start npm --name vehicle-frontend -- run preview -- --host 127.0.0.1 --port 4173 --strictPort
pm2 save
pm2 startup systemd -u ubuntu --hp /home/ubuntu
```

Run the `sudo` command printed by `pm2 startup` to enable startup after reboot.
Run PM2 commands as `ubuntu`, the same user that owns the process. For normal
updates, use `pm2 restart vehicle-frontend` from the first section.

## Backend and database essentials

Keep real values in the project root `.env`; preserve this file during updates.

```dotenv
OPENROUTER_API_KEY=your_real_key
LANGSMITH_TRACING=false
POSTGRES_USER=vehicle_app
POSTGRES_DB=vehicle_agent
POSTGRES_PASSWORD=your_existing_database_password
POSTGRES_PORT=127.0.0.1:5432
DATABASE_URL=postgresql+psycopg://vehicle_app:URL_ENCODED_PASSWORD@localhost:5432/vehicle_agent
CHAT_USAGE_DATABASE=/home/ubuntu/Aurion-Agentic-Sales_Assistant/.chat-usage.sqlite3
CORS_ORIGINS=https://aurion.duckdns.org
```

The URL password must match the database role password; URL-encode reserved
characters. Changing `POSTGRES_PASSWORD` in `.env` does not change the password
inside an existing database. To rotate it, connect with:

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
docker compose exec postgres psql -U vehicle_app -d vehicle_agent
```

At the SQL prompt, run `\password vehicle_app`, enter the new password twice,
and exit with `\q`. Update both password values in `.env` and restart the API.

Use Ubuntu's virtual environment commands if `.venv` does not exist:

```bash
sudo apt install -y python3-full python3-venv
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod 600 .env
```

Do not use Windows commands such as `py` or `Scripts/Activate.ps1` on EC2.
The service uses `.venv/bin/uvicorn app.api.main:app` on `127.0.0.1:8000`
with `--workers 1`. API restarts clear in-memory conversation history; the
SQLite usage file retains session budgets.

PostgreSQL data persists in the `aurion_pg18data` named volume. Initialization
SQL runs only on a fresh volume (original catalogue: 200 vehicles). Never use
`docker compose down -v` for routine updates; it deletes the database volume.
Keep database backups outside the instance.

## Logs and common fixes

Run database commands from the project root:

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
sudo journalctl -u vehicle-assistant -n 100 --no-pager
pm2 logs vehicle-frontend --lines 100
# Ctrl+C exits the live PM2 log view.
docker compose ps
docker compose logs --tail=100 postgres
sudo nginx -t
sudo systemctl status nginx --no-pager
```

| Symptom | Check or fix |
|---|---|
| Compose says no configuration file found | Run it from the checkout containing `docker-compose.yml`. |
| Python says externally managed environment | Install packages with `.venv/bin/python -m pip`, not system pip. |
| Vite says the domain is blocked | Add `aurion.duckdns.org` to `preview.allowedHosts` as shown above, then restart PM2. |
| UI still shows old changes | Confirm the build succeeded, restart PM2, then hard-refresh the browser. |
| Nginx returns 502 | Check API/systemd and frontend/PM2 status, then test their localhost URLs. |
| Chat fails while `/api/health` works | Check service status, API logs, OpenRouter key, and database credentials. |
| Database password authentication fails | Match `.env` to the existing database role password; do not delete the volume. |
| Browser CORS error | Set the exact page origin in `CORS_ORIGINS` (no trailing slash), then restart the API. |
| Chat stream stalls | Keep `proxy_buffering off`, `proxy_cache off`, and `proxy_read_timeout 90s` in Nginx's `/api/` location. |
| Domain is unreachable | Check DuckDNS, EC2 inbound 80/443, Nginx, and HTTPS certificate configuration. |
