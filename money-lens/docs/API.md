# Backend endpoints (JSON; all require login and CSRF token on POST)

| Method | URL | Purpose |
|---|---|---|
| GET | `/health/` | `{"status":"ok","database":"ok"}` |
| POST | `/statements/upload/` | multipart field `statement`; 201 job, 400 invalid, 409 duplicate, 413 too large |
| GET | `/statements/<uuid>/` | job status (404 if not yours) |
| POST | `/statements/<uuid>/process/` | build report; 200 `{"report_id"}`, 409 not allowed, 422 unreadable statement |
| GET | `/reports/` | your reports |
| GET | `/reports/<uuid>/data/` | full report (404 if not yours). Money values are strings. |

Error shape: `{"error": "<code>", "message": "<safe text>"}`.
Codes include: missing_file, empty_file, file_too_large, unsupported_type, content_mismatch, duplicate_upload,
pdf_unreadable, pdf_no_text, csv_no_header, no_transactions, multiple_currencies, expired.
