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
     admin account, created automatically on first startup. New passwords must
     be at least 8 characters. Once the app is running, use "Manage users" to
     add everyone else (kids and any other admins) — the bootstrap step only
     ever creates this one account.
   - `SESSION_HTTPS_ONLY`: leave at `0` for plain HTTP on your LAN. Set it
     to `1` when the site is served through HTTPS so the session cookie is
     never sent over an unencrypted connection.

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


## Security notes for network hosting

The app uses signed session cookies with `SameSite=Strict`, rejects
cross-site state-changing browser requests, rate-limits repeated failed login
attempts, validates stored dates, and enforces an 8-character minimum for new
or reset passwords.

If you expose Homework Manager beyond your trusted home network, put it behind
an HTTPS reverse proxy, set `SESSION_HTTPS_ONLY=1`, preserve the original
`Host` header, and do not expose the container's port directly to the public
internet. The login throttle is intentionally lightweight and stored in memory,
which is appropriate for the current single-process deployment but is not a
replacement for edge rate limiting at a public reverse proxy.
