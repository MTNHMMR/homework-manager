# Completed History, Priority Flag, Weekly View, and Streaks — Design Spec

Date: 2026-09-20
Status: Approved for implementation planning

## Purpose

Four features Justin picked after brainstorming a longer list, following up on v4's "done assignments fall off the list" change:

1. **Completed-work history** — a place to see finished assignments, since v4 now removes them from the main view on their due date instead of leaving them visible.
2. **Priority flag** — mark an assignment as important (a big test or project) so it stands out from routine homework.
3. **Weekly view** — an alternate, calendar-style way to see a kid's assignments, alongside the existing flat list.
4. **Streak stats** — a motivational "N-day on-time streak" shown to each kid and to admins.

A fifth idea from the same brainstorm — due-soon reminders — is **out of scope for this spec**, split off as a future v7 because it needs a real delivery-mechanism decision (email/push/etc.) this app has no infrastructure for yet.

## Non-goals

- No change to what "done" means or to the v4 falls-off-on-due-date behavior — history is a new read surface over the same data, not a redefinition.
- No multi-level priority (Low/Normal/High) — a single boolean "important" flag only.
- No full month-grid calendar — the weekly view is a Sun–Sat column layout with prev/next navigation, not a traditional calendar grid.
- No persisted view preference — the List/Week toggle is a `?view=` query param, not a stored per-user setting.
- Streaks are computed on read, not stored — no new table, no background job.

## Data model changes

Two new columns on `assignments`, added via the same additive-migration pattern already used for `users.theme`/`users.accent_color` in `database.py` (`PRAGMA table_info`, `ALTER TABLE ... ADD COLUMN` guarded by a column-existence check, run from `init_db`):

- `priority INTEGER NOT NULL DEFAULT 0` — 0/1 flag.
- `completed_at TEXT` (nullable) — set to `datetime('now')` the moment `status` is updated to `'done'`; cleared back to `NULL` if `status` is changed away from `'done'`. This is the one behavior change to `update_assignment()`: it needs to know the assignment's *previous* status to decide whether to set or clear the timestamp, so it will look up the current row before applying the update (same cost as today's callers already pay, since every caller already fetched the assignment via `get_assignment_by_id`/`_own_assignment_or_403` before calling `update_assignment`).

## Feature 1: Completed-work history

### Routes

- `GET /overview/history` — kid's own completed assignments only (`user_id = current user`, `status = 'done'`).
- `GET /admin/history` — all completed assignments, grouped by kid (same grouping pattern as `/admin` today: alphabetical by `display_name`, a kid with none omitted).

### Behavior

Lists every assignment with `status = 'done'`, sorted by `completed_at` descending (most recently finished first). Each row shows subject, title, due date, and completed date, so it's visible at a glance whether something was finished on time or late (`completed_at` date vs. `due_date`). No inline status dropdown or delete button on this view — it's primarily a read-only look back — but each row does keep an **Edit** link to the existing edit form, using the same `_own_assignment_or_403`/admin-edit routes that already exist today. That's the only way to correct a mistaken "done" once the item has fallen off the active list (v4): editing it back to a non-done status makes it reappear on the active list and disappear from history, the same reciprocal relationship the active list and history already have.

Nav gets a new link ("History") alongside the existing "My assignments" / "All assignments" links in `base.html`.

## Feature 2: Priority flag

### Where it's set

A checkbox ("Important") added to both add and edit forms — `overview.html`'s add form, `overview_edit.html`, and `admin_edit.html`. Persisted through `create_assignment`/`update_assignment`, which both gain a `priority: bool = False` parameter.

### Where it shows

On every list that already exists (`/overview`, `/admin`, plus the new history and week views): a flagged assignment gets a small marker next to its title (a themed icon, styled via the existing CSS-custom-property system rather than a hardcoded color, matching how status pills and overdue rows already key off theme/accent variables) and sorts to the top of its group — priority first, then the existing due-date order within each priority tier. Sorting happens in Python after fetch (same place the admin kid-grouping bucketing already happens), not a SQL `ORDER BY` change, to keep the query layer's contract (`ORDER BY due_date`) unchanged for existing callers/tests.

## Feature 3: Weekly view

### Behavior

`/overview?view=week` (and `/admin?view=week`, applied per kid within each group) shows the current week as seven columns, Sunday through Saturday, each listing that day's assignments due (subject, title, status pill, priority marker, overdue styling — all the same per-row treatment as the list view, just laid out by day instead of one sorted table). Prev/next links move the window a week at a time via a `week=` query param (an ISO date for that week's Sunday); omitting it defaults to the current week.

`view=list` (or omitting `view`) keeps today's existing flat table exactly as-is. A small toggle control at the top of the page switches between them, preserving whichever other query params are relevant (e.g. `status` on `/admin`).

### Data

No new query — same `list_assignments_for_user`/`list_all_assignments` (still only the "visible" set from v4's filtering) is grouped by `due_date` weekday in Python for the week view, exactly the way admin grouping already buckets by kid.

## Feature 4: Streak stats

### Definition

An **on-time streak** counts consecutive calendar days, walking backward from today, where every assignment due that day has `completed_at` set (regardless of whether it was completed exactly on that day or earlier) by the end of that day. A day with zero assignments due doesn't break or extend the streak — it's simply skipped over. The streak stops counting the first time it hits a day with at least one assignment that was due but not completed by end of that day. Today itself only counts once it's fully past (so a streak doesn't inflate mid-day) — practically: the walk starts at yesterday, and today's own due items only join the streak count once compared against the *next* day's calculation, so there's no special-casing of "in-progress today."

### Where it's computed

A new function in `assignments.py`, e.g. `compute_streak(conn, user_id, today) -> int`, called fresh on each page render (cheap: bounded by how many due-dates actually have assignments, not an unbounded scan — it stops at the first miss).

### Where it shows

- Kid's own `/overview`: "🔥 N-day streak" near the top of the page.
- Admin dashboard: next to each kid's name heading on both `/admin` and `/admin/history`.
- A streak of 0 shows no flame/message clutter — just omitted, rather than "🔥 0-day streak."

## Testing

- Migration: `priority` and `completed_at` columns exist after `init_db` on both a fresh DB and one already containing the pre-v6 schema (mirrors the existing `test_database.py` migration test for `theme`/`accent_color`).
- `completed_at`: set when status becomes `done`, cleared when changed away from `done`, unaffected by no-op updates that keep the same status.
- Priority: flag persists through create/edit; flagged items sort before unflagged items within the same list; unauthorized users still can't flag another kid's assignment (existing 403 boundary unchanged).
- History routes: kid sees only their own completed items; admin sees all, grouped by kid, empty kids omitted; a non-done item never appears; permission boundaries match `/overview`/`/admin` (login required, admin required for the admin route).
- Weekly view: correct items appear under the correct day column; `week=` navigation moves the window; items outside the shown week don't appear; `view=list` (or no param) is unaffected — a regression check that the existing table still renders exactly as before.
- Streaks: a run of on-time completions counts correctly; a single missed day resets/stops the count; a day with no assignments due doesn't break an existing streak; a done-but-late item (completed after its due date) still breaks the streak for that day.

## Deployment notes

Ships to the same live deployment (Portainer stack `homework-manager`, `192.168.1.235:8010`), same flow as v3/v4: push to `master`, trigger the stack's git-redeploy via the Portainer API. This one **does** carry a schema migration (`priority`, `completed_at` columns) — the additive `ALTER TABLE` pattern already used for `theme`/`accent_color` was deployed once before against this same live, non-empty database with zero downtime-causing errors, so the approach is proven against this exact app.
