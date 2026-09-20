# Homework Manager

Self-hosted homework tracker. Each kid logs their own assignments under
their own login; any account flagged admin (e.g. both parents) can see and
manage every kid's assignments and manage user accounts.

## First run

1. Copy `.env.example` to `.env` and fill in real values:
   ```bash
   cp .env.example .env
   ```
   - `SESSION_SECRET_KEY`: any long random string (e.g. `openssl rand -hex 32`).
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_DISPLAY_NAME`: the first
     admin account, created automatically on first startup. Once the app is
     running, use "Manage users" to add everyone else (kids and any other
     admins) — the bootstrap step only ever creates this one account.

2. Build and start the container:
   ```bash
   docker compose up --build
   ```

3. Open `http://localhost:8010` (the host port is set in `docker-compose.yml`
   — change it if 8010 is already taken on your host), log in with the admin
   account from step 1, and add the kids (and any other admins) under
   "Manage users".

Data lives in the `homework-data` Docker volume (`/data/homework.db` inside
the container) and survives `docker compose down` — only `docker compose
down -v` removes it.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```
