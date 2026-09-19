# Homework Manager — Design Spec

Date: 2026-09-19
Status: Approved for implementation planning

## Purpose

A self-hosted web app for tracking kids' homework assignments. Each kid gets
their own login and logs their own assignments; Justin and his wife each get
admin logins that can see and manage everything across all kids. Runs in a
single Docker container on the home network today, built to be reverse-proxy
friendly for external access later.

## Non-goals

- No shared SSO / integration with a future "HomeNet" portal — this is
  standalone for now.
- No grades, no notifications/reminders, no recurring-assignment templates.
- No self-service account signup — accounts are created by an admin.

## Stack

- **Backend:** Python, FastAPI
- **Templates:** Jinja2 (server-rendered HTML), light vanilla JS where needed
- **Database:** SQLite, file stored on a mounted Docker volume so data
  survives container rebuilds
- **Auth:** Session-cookie based; passwords hashed with bcrypt
- **Deployment:** Single container, `docker-compose.yml`

Rationale: the app is a small CRUD list behind auth — a server-rendered app
keeps this to one codebase with no build step. FastAPI gives clean
session/auth handling without much boilerplate. SQLite is plenty for a
family's worth of data and needs no separate DB container.

## Data model

**`users`**
| column | type | notes |
|---|---|---|
| id | integer PK | |
| username | text, unique | |
| password_hash | text | bcrypt |
| display_name | text | shown in UI |
| is_admin | boolean | any account can be an admin — not a separate role table |
| active | boolean | deactivated accounts can't log in, history is kept |
| created_at | datetime | |

**`assignments`**
| column | type | notes |
|---|---|---|
| id | integer PK | |
| user_id | integer FK → users.id | the owning kid |
| subject | text | e.g. "Math" |
| title | text | e.g. "Ch. 4 worksheet" |
| due_date | date | |
| status | text enum | `not_started` / `in_progress` / `done` |
| created_at | datetime | |

## Roles & permissions

- **Kid (non-admin) account:** can create, view, edit, and delete only their
  own assignments. Sees only their own overview page.
- **Admin account:** can view and manage assignments for *every* user, and
  can manage user accounts (create, reset password, deactivate). Being an
  admin is a flag on a normal user row, not a separate account type — so
  Justin and his wife each have their own login, both flagged `is_admin`.
- Permission checks happen server-side on every route (not just hidden in
  the UI) — a non-admin hitting another user's assignment by ID directly
  gets a 403, not just a hidden link.

## Pages / routes

| Route | Access | Purpose |
|---|---|---|
| `/login`, `/logout` | everyone | shared login form |
| `/overview` | logged-in user | that user's own assignments, sorted by due date, with add/edit/mark-done/delete |
| `/admin` | admin only | table of all assignments across all kids, filterable by kid and status, edit/delete any |
| `/admin/users` | admin only | list users, create new user (kid or admin), reset a password, deactivate an account |

## Error handling

- Invalid login → generic "invalid username or password" (no user
  enumeration).
- Non-admin attempting to access another user's assignment or any `/admin*`
  route → 403.
- Form validation (missing title/subject/due date) → re-render form with
  inline error, don't lose entered data.

## Testing

- Unit tests for permission logic (a non-admin cannot read/write another
  user's assignment; an admin can).
- Integration tests for auth (login success/failure, session persists,
  logout clears session).
- Basic route tests for each page rendering for the right role and
  403/redirect for the wrong role.

## Deployment notes

- `docker-compose.yml` mounts a volume for the SQLite file.
- First admin account is seeded via an environment variable / one-time setup
  script on first run (chicken-and-egg: an admin UI to create admins needs a
  first admin to exist).
- App reads `X-Forwarded-*` headers and doesn't hardcode its own origin, so
  it can sit behind a reverse proxy later without rework.
