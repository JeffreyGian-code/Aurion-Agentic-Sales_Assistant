# Deploy to Ubuntu on Amazon EC2

This deploys the React/Vite web UI, FastAPI backend, and PostgreSQL database on
one Ubuntu EC2 instance. PM2 runs Vite's preview server for the built frontend;
Nginx proxies web requests to it and `/api` to Uvicorn. The configured domain
is `aurion.duckdns.org`.
PostgreSQL listens only on localhost. The API uses one worker because its chat
memory and rate limiter are in process memory.

## 1. Create the EC2 instance

In the AWS EC2 console, launch an Ubuntu Server 24.04 LTS instance. For a small
personal demo, use at least 2 vCPU and 4 GiB RAM; increase this for concurrent
users. Select an instance size and EBS size appropriate for your workload and
check current AWS pricing for your region before launching.

Create or select a key pair and save its private key somewhere private. Attach
a security group with these inbound rules:

| Type | Port | Source |
|---|---:|---|
| SSH | 22 | My IP (your current public IP only) |
| HTTP | 80 | `0.0.0.0/0` |
| HTTPS | 443 | `0.0.0.0/0` |

Do not add inbound rules for ports 5432, 8000, 4173, or 5173. Assign an Elastic IP
if you want a stable address; if using a domain, point its DNS A record at that
address. AWS notes that SSH should be limited to known source IP addresses.

Connect from your computer (replace the key and public DNS/IP):

```bash
ssh -i /path/to/key.pem ubuntu@EC2_PUBLIC_DNS_OR_IP
```

The default SSH username for Ubuntu images is `ubuntu`.

## 2. Install system packages and Docker

Run on the instance:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git nginx python3 python3-venv python3-pip
```

Install Docker Engine and the Compose plugin from Docker's Ubuntu repository:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Log out and SSH in again so the `docker` group membership applies. Verify:

```bash
docker --version
docker compose version
```

## 3. Configure the deployed project

The project is already deployed at
`/home/ubuntu/Aurion-Agentic-Sales_Assistant`. Confirm the repository files
are present, then configure its environment:

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
ls -la
test -f .env || cp .env.example .env
nano .env
```

Set these values in `.env`:

```dotenv
OPENROUTER_API_KEY=your_real_openrouter_key
LANGSMITH_TRACING=false
POSTGRES_USER=vehicle_app
POSTGRES_DB=vehicle_agent
POSTGRES_PASSWORD=use_a_long_random_password
POSTGRES_PORT=127.0.0.1:5432
DATABASE_URL=postgresql+psycopg://vehicle_app:URL_ENCODED_PASSWORD@localhost:5432/vehicle_agent
CHAT_USAGE_DATABASE=/home/ubuntu/Aurion-Agentic-Sales_Assistant/.chat-usage.sqlite3
CORS_ORIGINS=http://aurion.duckdns.org,https://aurion.duckdns.org
```

If you do not have a domain yet, use `http://EC2_PUBLIC_IP` for
`CORS_ORIGINS` until HTTPS is configured. The `POSTGRES_PORT` value binds the
Compose database port to loopback, rather than every network interface. Keep
the PostgreSQL password in the URL identical to `POSTGRES_PASSWORD`, and
percent-encode reserved URL characters in it. Keep `.env` private; never commit
it or paste real API keys into a terminal recording.

The repo `.env.example` contains a `DATABASE_URL` placeholder. Replace it with
the URL for the password you chose. The compose file uses the default database
user/database above unless you explicitly set `POSTGRES_USER` and
`POSTGRES_DB`. Generate a URL-safe password with `openssl rand -hex 24` so it
does not need percent-encoding. Never share `.env` or paste credentials into
chat. If a database password was exposed, rotate it in PostgreSQL with the
interactive `\password vehicle_app` command described below, then update
both password values in `.env`.

## 4. Start PostgreSQL and install the Python app

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
docker compose up -d --wait postgres
docker compose ps
docker compose exec postgres psql -U vehicle_app -d vehicle_agent -c 'SELECT COUNT(*) FROM vehicles;'
```

On a fresh data volume, the repository SQL files initialize and seed the
catalogue (expected count: 200). Docker keeps the database in a named volume,
so it survives container restarts and code updates. Do not run `docker compose
down -v` unless you intend to delete the database.

Compose initializes the database admin role using `POSTGRES_USER`, so the role
is `vehicle_app`; a separate `postgres` database role may not exist. To change
the database role password safely, connect as the configured user:

```bash
docker compose exec postgres psql -U vehicle_app -d vehicle_agent
```

At the `psql` prompt, enter `\password vehicle_app`, provide the new password
twice, then exit with `\q`. Set the same new password in both
`POSTGRES_PASSWORD` and `DATABASE_URL` in `.env`. Changing `POSTGRES_PASSWORD`
alone does not change a role in an already initialized volume.

If you change `POSTGRES_PORT` after creating the container, recreate it to
apply the loopback-only port binding. Its named volume is retained:

```bash
docker compose up -d --force-recreate postgres
docker ps
```

The port mapping should begin with `127.0.0.1:5432->5432/tcp`. Keep inbound
port 5432 closed in the EC2 security group.

Create a virtual environment and install the pinned backend dependencies:

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
sudo apt install -y python3-full python3-venv
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt "psycopg[binary]==3.3.5"
```

## 5. Run the API with systemd

Restrict access to the environment file:

```bash
sudo chmod 600 /home/ubuntu/Aurion-Agentic-Sales_Assistant/.env
```

Create `/etc/systemd/system/vehicle-assistant.service`:

```ini
[Unit]
Description=Vehicle Sales Assistant API
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Aurion-Agentic-Sales_Assistant
EnvironmentFile=/home/ubuntu/Aurion-Agentic-Sales_Assistant/.env
ExecStart=/home/ubuntu/Aurion-Agentic-Sales_Assistant/.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Then start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vehicle-assistant
sudo systemctl status vehicle-assistant --no-pager
curl http://127.0.0.1:8000/api/health
```

Expected health response: `{"status":"ok"}`. View logs with
`sudo journalctl -u vehicle-assistant -f`.

## 6. Build the frontend

Install Node.js 24 and build the UI with a relative API URL. Vite embeds
`VITE_API_URL` at build time; `/api` makes the browser use the same host as the
web page.

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant/frontend
npm ci
printf 'VITE_API_URL=/api\nVITE_USE_MOCK=false\n' > .env.production
npm run build
```

The output is `frontend/dist`. This setup runs Vite Preview under PM2, bound to
localhost so it is reached only through Nginx:

```bash
sudo npm install -g pm2
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant/frontend
pm2 start npm --name vehicle-frontend -- run preview -- --host 127.0.0.1 --port 4173
pm2 save
pm2 startup systemd -u ubuntu --hp /home/ubuntu
```

PM2 prints a `sudo` command after `pm2 startup`; copy and run that command to
enable startup after reboot. Check the app with `pm2 status` and
`curl -I http://127.0.0.1:4173/` (expect HTTP 200).

Vite Preview checks the incoming hostname. In `frontend/vite.config.ts`, add
the exact DuckDNS hostname to the existing `defineConfig` object:

```ts
preview: {
  allowedHosts: ['aurion.duckdns.org'],
},
```

Keep this list limited to hostnames you control; do not set `allowedHosts: true`.
Restart the preview process after changing the config:

```bash
pm2 restart vehicle-frontend
pm2 save
```

## 7. Configure Nginx

The DuckDNS A record must resolve to the EC2 instance's public IP. Check it
with `getent ahostsv4 aurion.duckdns.org` and use the domain in `server_name`.

Create `/etc/nginx/sites-available/vehicle-assistant`:

```nginx
server {
    listen 80;
    server_name aurion.duckdns.org;
    location / {
        proxy_pass http://127.0.0.1:4173;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 90s;
    }
}
```

Enable the site and reload Nginx:

```bash
sudo ln -sfn /etc/nginx/sites-available/vehicle-assistant /etc/nginx/sites-enabled/vehicle-assistant
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Open `http://aurion.duckdns.org`. Test chat and the service status
button; the latter checks API, database, and OpenRouter reachability.

## 8. Enable HTTPS for a domain

Confirm `aurion.duckdns.org` resolves to the instance's public IP and that
inbound ports 80 and 443 are allowed. Then run:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d aurion.duckdns.org
```

Choose the redirect to HTTPS when prompted. Set `CORS_ORIGINS` in `.env` to
`https://aurion.duckdns.org`, then restart the API:

```bash
sudo systemctl restart vehicle-assistant
```

Certbot configures renewal; check it with `sudo certbot renew --dry-run`.

## 9. Updates and operations

To deploy a later version:

```bash
cd /home/ubuntu/Aurion-Agentic-Sales_Assistant
git pull
.venv/bin/pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
pm2 restart vehicle-frontend
sudo systemctl restart vehicle-assistant
```

Useful commands:

```bash
sudo systemctl status vehicle-assistant nginx --no-pager
sudo journalctl -u vehicle-assistant -n 100 --no-pager
pm2 status
pm2 logs vehicle-frontend
docker compose ps
docker compose logs --tail=100 postgres
```

Back up the PostgreSQL volume regularly (for example, use `pg_dump` and store
the dump outside this instance). The named Docker volume is persistent storage,
not a backup. Chat conversation state is held in process memory and is lost on
API restart. The optional SQLite session budget file is persisted at the path
set by `CHAT_USAGE_DATABASE`.

For connection and web server troubleshooting, check these first:

- SSH times out: confirm the instance is running and the security group allows
  port 22 from your current IP.
- Site is unreachable: confirm inbound 80/443, Nginx status, and DNS.
- Frontend is unavailable: check `pm2 status` and `pm2 logs vehicle-frontend`.
- Vite says the host is not allowed: add `aurion.duckdns.org` to
  `preview.allowedHosts` in `frontend/vite.config.ts`, then restart PM2.
- `/api/health` fails: check `sudo journalctl -u vehicle-assistant` and that
  PostgreSQL is healthy.
- Chat fails but health succeeds: check `OPENROUTER_API_KEY`, database URL,
  and `sudo journalctl -u vehicle-assistant`.
- Browser CORS error: ensure `CORS_ORIGINS` exactly matches the page origin,
  including `https://` and no trailing slash, then restart the API.
- Chat stream stalls: confirm Nginx has `proxy_buffering off` and the
  `proxy_read_timeout` is longer than the model's quiet periods.

## AWS references

- [Connect to a Linux instance using SSH](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-linux-inst-ssh.html)
- [Create a security group](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html)
- [EC2 pricing](https://aws.amazon.com/ec2/pricing/)
