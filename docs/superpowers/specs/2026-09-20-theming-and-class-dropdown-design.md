# Per-Kid Theming and Class Dropdown — Design Spec

Date: 2026-09-20
Status: Approved for implementation planning

## Purpose

Two additions to the already-deployed Homework Manager app:

1. **Per-kid visual customization** — each kid picks their own theme preset and
   accent color for their own pages. Nobody else can change it for them.
2. **Per-kid class dropdown** — the assignment "subject" field becomes a
   dropdown populated from that specific kid's actual class list (admin-entered),
   instead of free text, with a graceful fallback to free text when a kid has
   no active classes on file.

## Non-goals

- No per-kid dashboard layout changes beyond color/theme — component
  structure (nav, tables, forms) stays the same across all four themes.
- No self-service class-list editing by kids — only an admin enters/edits
  classes (confirmed: admin-entered only, not kid-editable).
- No "Other" free-text escape hatch alongside the dropdown when classes
  exist — the dropdown is strict; free text only appears as a fallback when
  there are zero active classes for that kid.
- No theme/accent settable by an admin on a kid's behalf — a kid's own
  `/settings` page is the only place `theme`/`accent_color` can change.

## Part 1: Per-kid theming

### Data model

Add two columns to `users`:

| column | type | notes |
|---|---|---|
| theme | text | one of `light`, `dark`, `fun`, `minimal`; default `light` |
| accent_color | text | one of `red`, `orange`, `yellow`, `green`, `teal`, `blue`, `purple`, `pink`; default `blue` |

### UI

New route `GET/POST /settings` (any logged-in user, kid or admin — everyone
gets to pick their own look): a simple form with a theme radio group and an
accent-color swatch picker, `require_user` only (no ownership complexity —
a user can only ever edit their own row, there's no ID in the URL).

`base.html` renders `<body data-theme="{{ user.theme }}" data-accent="{{ user.accent_color }}">`
for a logged-in user (falls back to `data-theme="light" data-accent="blue"`
on the login page, where there's no user yet).

### Styling approach

One stylesheet, not four. `style.css` defines CSS custom properties per
`data-theme` value (background/text/card colors, corner radius, shadow
style) and per `data-accent` value (a single `--accent` color used by the
nav bar, primary buttons, and status badges). This keeps "Fun" a
CSS-only affair — livelier via rounder corners, soft gradients, and bigger
badge padding — rather than needing per-theme Jinja template branches or
icon logic. Approved via the visual mockup comparison during brainstorming
(all four presets shown side by side; user confirmed the direction).

### Error handling

`theme`/`accent_color` values are validated server-side against the fixed
lists above (`VALID_THEMES`, `VALID_ACCENTS`, same pattern as
`VALID_STATUSES`) — an invalid value is rejected with 400, not silently
stored.

## Part 2: Per-kid class dropdown

### Data model

New `classes` table:

| column | type | notes |
|---|---|---|
| id | integer PK | |
| user_id | integer FK → users.id | the kid this class belongs to |
| name | text | e.g. "Science" |
| teacher | text, nullable | reference info only — not shown in the dropdown |
| period | integer, nullable | for display/admin ordering |
| expires_on | date, nullable | null = never expires |
| created_at | datetime | |

A class is **active** for dropdown purposes if `expires_on` is null or
`expires_on >= today`.

### Admin UI

New admin section `/admin/classes` (mirrors the existing `/admin/users`
pattern): list every kid's classes grouped by kid, ordered by `period`;
add/edit/delete a class for a given kid. Each class form has `name`,
`teacher` (optional), `period` (optional), `expires_on` (optional date).

### Assignment form behavior

On the kid's own add/edit assignment form (`/overview/add`,
`/overview/{id}/edit`) and the admin edit form (`/admin/{id}/edit`):

- If the assignment's owning kid has one or more **active** classes: the
  `subject` field renders as a `<select>` of those class names (ordered by
  `period`, nulls last), values are the class **names** (not IDs — kept
  consistent with the existing `subject: str` column on `assignments`, no
  schema change needed there).
- If the owning kid has **zero** active classes (none entered yet, or all
  expired): `subject` renders as the existing free-text `<input>` — the
  current behavior, unchanged. This is the confirmed fallback for after
  Dec 31 when this semester's classes lapse and a new semester's list
  hasn't been entered yet.
- Server-side validation: when the dropdown path is used, the submitted
  `subject` must match one of that kid's currently-active class names, or
  the form re-renders with an error (400) — same "don't lose entered data"
  pattern already used for missing-field validation. When the fallback
  free-text path is used, any non-blank string is accepted, same as today.

### Initial data (seeded via admin UI or a one-time script, this semester,
### all expiring 2026-12-31)

**Elliott:**
1. Jazz Band — Lamar
2. Science — Rogers
3. American History — McNeil
4. PE — Campos
5. ELA — Hutson
6. Honors Algebra — Seyer
7. Challenge — Taylor

**Zander:**
1. Ecology — Morton
2. Personal Finances — Wamble
3. Industrial Tech — Hobeck
4. Advanced Foods — Newman
5. A+ Tutoring — *(no teacher given)*
6. College Readiness — Taylor
7. Marching Band — Lamar

**Elizabeth** *(partial — Justin will provide periods 3, 4, 5, 7 later)*:
1. Jazz Band — Lamar
2. Science — Dugas
6. Math — Campos

All entries above get `expires_on = 2026-12-31`. As of this spec, only
Zander (`zcain`) has a `users` row on the live deployment — Elliott and
Elizabeth's accounts (`ebcain`, `eacain`) get created as a deployment-time
step (via the "Manage users" admin UI against the live app, not a
committed script — their initial passwords are not written into this repo
or any spec/plan file) before their classes are attached. Elizabeth's
periods 3, 4, 5, and 7 are still pending from Justin and get added once
provided — this seed is intentionally partial for her.

## Testing

- Theme/accent: valid values persist and render in `data-theme`/`data-accent`;
  invalid values rejected (400); a user can only change their own settings
  (no ID-based route to spoof).
- Classes: active-vs-expired filtering (`expires_on` boundary at "today"),
  dropdown renders only active classes for the correct kid, free-text
  fallback when zero active classes, dropdown submission rejects a subject
  not in the active list, admin-only access to `/admin/classes` routes
  (403 for non-admin, consistent with every other admin route).

## Deployment notes

This ships to the same running deployment (Portainer stack `homework-manager`
on the HomeLab, `192.168.1.235:8010`) via the existing GitHub-repo-backed
stack — push to `master`, then a Portainer git redeploy, same as the
original rollout. The new `users` columns and `classes` table are additive
(no destructive migration) — `init_db()`'s `CREATE TABLE IF NOT EXISTS`
pattern won't add new columns to an *existing* `users` table on its own, so
the plan must include an explicit `ALTER TABLE users ADD COLUMN ...`
migration step guarded to run once against the live SQLite file, not just
a fresh-install schema change.
