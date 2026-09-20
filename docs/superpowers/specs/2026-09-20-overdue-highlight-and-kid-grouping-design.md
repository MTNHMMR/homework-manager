# Overdue Highlighting and Admin Kid-Grouping — Design Spec

Date: 2026-09-20
Status: Approved for implementation planning

## Purpose

Two small usability additions to the already-deployed Homework Manager app:

1. **Overdue highlighting** — visually flag an assignment that's past its due date and not yet done, on both the kid's own overview page and the admin dashboard.
2. **Kid grouping on the admin dashboard** — replace the current flat, sorted-by-due-date list on `/admin` with assignments grouped under a heading per kid, so a parent scanning the page sees one kid's work together instead of interleaved rows.

## Non-goals

- No change to how "done" is defined or computed — overdue is purely a display concern layered on existing `due_date`/`status` data, no schema change.
- No overdue highlighting change to the edit forms (`/overview/{id}/edit`, `/admin/{id}/edit`) — this is a list-view concern only.
- The admin "Kid" filter dropdown is removed (confirmed redundant now that everything is grouped by kid) — the "Status" filter stays and applies across all groups.

## Part 1: Overdue highlighting

### Definition

An assignment is **overdue** when `due_date < today` **and** `status != 'done'`. A done assignment past its due date is never highlighted — the work is finished, no warning needed.

### Where it shows

Both `GET /overview` (kid's own list) and `GET /admin` (all assignments, now grouped by kid — see Part 2).

### Implementation approach

`today` (an ISO date string, `date.today().isoformat()`) is computed once in each route and passed into the template context. The template marks a row `overdue` when `assignment.due_date < today and assignment.status != 'done'` (plain string comparison — safe because `due_date` is always stored as zero-padded `YYYY-MM-DD`, same assumption the existing `ORDER BY due_date` sort already relies on).

Styling applies a background tint to the whole `<tr>` (`color-mix(in srgb, var(--error) 12%, var(--card-bg))`, mirroring the pattern already used for the status-pill backgrounds) — never a `display`-altering rule on a `<td>`, which is exactly what caused the status-dropdown/border-cutting bug just fixed. Row-level background color doesn't affect table layout at all, so this can't repeat that failure mode.

## Part 2: Kid grouping on the admin dashboard

### Behavior

`GET /admin` groups assignments by owning kid. Kids appear in the same order `/admin/users` and `/admin/classes` already use (`ORDER BY display_name`, alphabetical). Within each kid's group, assignments stay sorted by due date — no re-sort needed, since the existing query already returns everything sorted by due date globally and bucketing that list by kid preserves each kid's relative due-date order automatically.

A kid with zero assignments (after the Status filter is applied, or in general) does not get an empty heading — only kids who have at least one assignment matching the current filter appear.

### What's removed

The "Kid" `<select>` filter and its query param (`kid_id`) are removed from `/admin` entirely — with everything already grouped by kid, filtering to one kid is redundant with just reading that kid's section. The "Status" filter (`status` query param) stays exactly as it is today and applies before grouping, so each kid's section only shows assignments matching the selected status.

## Testing

- Overdue: an assignment with a past due date and `not_started`/`in_progress` status renders with the overdue marker on both `/overview` and `/admin`; a past-due `done` assignment does not; a future-due assignment does not, regardless of status.
- Grouping: `/admin` renders one heading per kid with assignments, in display-name order; a kid with no matching assignments (after the Status filter) has no heading; the Status filter still narrows within groups; the Kid filter/query param is gone (a stray `?kid_id=` is simply ignored, not an error, since query params FastAPI doesn't declare are always ignored).

## Deployment notes

Ships to the same live deployment (Portainer stack `homework-manager`, `192.168.1.235:8010`) the same way as prior changes: push to `master`, Portainer git redeploy. No database change, so no migration concern this time — purely template/CSS/route-logic changes.
