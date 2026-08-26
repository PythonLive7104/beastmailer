# BeastMailer Auto-Reply

An admin webapp that connects to email accounts, watches incoming mail, and
sends automatic replies based on subject-matching rules — so one person can
manage many mailboxes from a single dashboard.

- **Backend:** Django 5 + Django REST Framework (SQLite in dev, Postgres-ready)
- **Frontend:** React 19 + Vite, with a light/dark theme toggle
- **Mail:** IMAP (read) + SMTP (send) via the Python standard library
- **Credentials:** mailbox passwords encrypted at rest with Fernet

## Authentication & multi-tenancy

The app opens on a **login / signup** screen; the dashboard and all API endpoints
require a logged-in user (DRF token auth). A token is issued on login/signup and
stored in the browser; the sidebar shows the current user and a working **Logout**.

**Data belongs to a workspace, and teams can share one.** On signup each user gets a
personal workspace; they can also create shared workspaces and invite others. All
mail data (mailboxes, rules, templates, placeholders, links, attachments, messages,
config, Telegram) is scoped to the **active workspace**, so every member of a
workspace sees and manages the same data. The engine runs each mailbox against only
its workspace's rules/placeholders/config/Telegram. Cross-workspace references are
rejected at the API.

**Team roles:** `owner` (created it; can delete, can't be removed), `admin` (manage
members + all data), `member` (use all data). Owners/admins invite by username/email
— existing users join instantly; new emails get a shareable **invite code** redeemed
under Team → Join. Switch workspaces from the topbar switcher.

Demo login after `seed_demo`: **admin / admin12345**.

## Database

Self-contained **SQLite** bundled with the app (`backend/db.sqlite3`) — no external
database service to run. Swap the `DATABASES` setting for Postgres if you later
need it, but nothing else depends on an external DB.

## What it does

1. Add email accounts (IMAP + SMTP) in the **Mailbox** page and test the connection.
2. The engine polls each active mailbox on an interval and records **received** mail.
3. Incoming subjects are matched against your **Rules**; a match drafts a reply from a
   **Template** and schedules it after a configurable delay.
4. Scheduled replies are **sent** over SMTP and threaded back to the original email by subject.
5. The **Dashboard** shows live stats and a running activity feed (sent / scheduled / received).

## Running it

### Backend
```bash
cd backend
python3 -m venv venv                 # already created during setup
venv/bin/pip install -r requirements.txt
venv/bin/python manage.py migrate
venv/bin/python manage.py seed_demo  # optional demo data + admin/admin12345
venv/bin/python manage.py runserver 8290  # http://127.0.0.1:8290
```

Run the automation engine in a second terminal:
```bash
venv/bin/python manage.py run_engine        # loops on the configured poll interval
# or: venv/bin/python manage.py run_engine --once   (good for cron)
```

### Frontend
```bash
cd frontend
npm install
npm run dev                          # http://localhost:5290
```

## Configuration

Backend reads `backend/.env` (all optional in dev):

```
DJANGO_SECRET_KEY=...
MAIL_ENCRYPTION_KEY=<Fernet key>     # REQUIRED in production; keep it stable
CORS_ALLOWED_ORIGINS=http://localhost:5290
```

Generate a Fernet key: `venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

Frontend reads `VITE_API_BASE` (defaults to `http://127.0.0.1:8290/api`).

## Layout

```
backend/
  config/            Django project (settings, urls)
  apps/
    accounts/        Token auth: register / login / logout / me
    workspaces/      Workspace, Membership (roles), invitations, active-workspace switching
    mailboxes/       Mailbox model + encrypted credentials + connection test
    rules/           Rule, ReplyTemplate, Placeholder
    mail/            EmailMessage (sent/received/scheduled) + subject threading
    automation/      Config singleton + IMAP/SMTP engine + run_engine command
    links/           Reusable links + click-tracking redirect (/r/<slug>/)
    attachments/     Uploaded files attached to replies (per rule)
    notifications/   Telegram bot config + notify() (sent/received/error)
    security/        Audit log (SystemEvent), posture, password change
    core/            Dashboard aggregate endpoint
frontend/
  src/pages/         Dashboard, Mailboxes, AutoReply, Rules, Configuration, Listeners,
                     Placeholders, Links, Attachments, Telegram, Security, Team, Auth
  src/components/WorkspaceSwitcher.jsx   topbar workspace picker
  src/components/     Layout (sidebar + theme toggle), shared UI
  src/api.js          API client (adds the auth token to every request)
  src/auth.jsx        auth context + route guard state
  src/theme.jsx       light/dark theme provider
```

## Notes for production
- Set `MAIL_ENCRYPTION_KEY` and `DJANGO_SECRET_KEY`, and `DJANGO_DEBUG=0`.
- Swap SQLite for Postgres in `settings.DATABASES`.
- Run `run_engine` under a process manager (systemd/supervisor) or as a cron with `--once`.
- Build the frontend (`npm run build`) and serve `dist/` behind your web server.
