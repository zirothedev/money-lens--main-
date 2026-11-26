# Frontend (Phase 5)

Django Templates + one stylesheet + small vanilla-JS modules. No React, no build step, no third-party requests
(the Plus Jakarta Sans font is self-hosted).

## Pages
| URL | Template | Notes |
|---|---|---|
| `/` | `home.html` | Landing + upload modal (modal only rendered for logged-in users) |
| `/reports/<uuid>/` | `report.html` | Report dashboard, server-rendered from the saved report |
| `/reports/history/` | `reports/history.html` | List of the user's own reports |
| `/accounts/login/`, `/accounts/register/` | `accounts/*.html` | Styled auth pages |
| any missing/forbidden report | `reports/not_found.html` (404) | Identical for "missing" and "someone else's" |

Templates: `base.html` (shell) with partials `_icons.html`, `_sidebar.html`, `_upload_modal.html`.

## Flow (uses the existing synchronous backend, nothing new)
1. `POST /statements/upload/` (multipart `statement`) -> `{id}`
2. `POST /statements/<id>/process/` -> `{report_id}` (blocks until the report exists; the temporary file/record are already deleted)
3. Redirect to `/reports/<report_id>/`

A `409 duplicate_upload` carries the existing job, so the UI continues processing that job instead of failing.
Status polling is not used: the job row is deleted on success, so `GET /statements/<id>/` would just 404.

**Processing checklist:** step 1 completes when the upload really finishes; steps 2-5 advance on a timer while the
server works; the last step stays "current" until the server actually answers. Completion and failure are real;
the in-between timing is paced because the backend does not report stages.

## JavaScript (`static/js/`)
`boot.js` (js flag) · `validation.js` (pure) · `messages.js` (pure, error wording) · `api.js` (fetch + response
classification) · `modal.js` (focus trap, Esc, scroll lock) · `upload.js` (flow) · `report.js` (expand, search, filter, show more).
Pure modules are unit-tested with Node (`frontend_tests/js`).

## Design tokens (`static/css/style.css`)
Purple sampled from the supplied reference and logo: `--primary #7837ec` (UI), `--primary-deep #5a1dac` (logo),
sidebar navy `#07081e`, page `#f7f8fc`. Purple text uses `--primary-strong #5f26c9` for contrast.
Red is used only for error messages.

## Decisions worth knowing
- Names and narrations are shown exactly as the statement writes them (e.g. `AHMED MUSA`). Empty narration is an empty cell.
- Currency symbol comes from the statement. If the statement states none, no symbol is shown. Set
  `REPORT_FALLBACK_CURRENCY=NGN` in `.env` to display ₦ in that case (display only).
- Bar length = recipient total as a percentage of the largest recipient total (the only derived display value).
- The landing-page report preview is a labelled "Example report", not real data.

## Tests
`python manage.py test` runs everything: Django page tests, Node JS unit tests, and Playwright browser tests
(skipped automatically if Chromium isn't installed: `pip install playwright && playwright install chromium`).
Screenshots of every screen are in `docs/screenshots/`.
