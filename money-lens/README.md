# Where'd My Money Go?

Your bank statement, finally understandable. Upload a PDF/CSV statement; get a report of money received,
money sent, and totals per identifiable recipient, using only what the statement itself says.

Status: backend (Phases 1-4) and frontend (Phase 5: landing, upload modal, processing, report dashboard).

## Run locally
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env        # then edit DJANGO_SECRET_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
Checks: `python manage.py check` and `python manage.py test` (244 tests).
Browser tests need Chromium: `pip install playwright && playwright install chromium` (skipped if missing).
JavaScript unit tests need Node 18+ (skipped if missing).
Optional: set `REPORT_FALLBACK_CURRENCY=NGN` in `.env` to show ₦ when a statement doesn't state its currency.

Run `python manage.py cleanup_expired_statements` on a schedule (cron) to purge abandoned uploads.

See `docs/` for the spec, architecture, API, privacy design and `FRONTEND.md`.
