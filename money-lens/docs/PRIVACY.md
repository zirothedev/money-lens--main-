# Privacy

- Originals are temporary. Lifecycle: upload -> private storage -> process -> save report -> delete file and record.
- Success: immediate deletion. Failure: file deleted immediately, small status record kept until expiry.
  Abandoned uploads: expire after `STATEMENT_EXPIRY_MINUTES` (default 60); `cleanup_expired_statements` removes them,
  plus orphan files older than the window.
- Files live in `PRIVATE_UPLOAD_ROOT` (outside static/media; never served), mode 0600, random names; user filenames are never used.
- Validation: extension, size (`STATEMENT_MAX_UPLOAD_MB`), content signature (PDF magic / no binary in CSV).
- Access control: jobs and reports are filtered by owner; other users get 404.
- Logs contain IDs, file type and exception class names only: no amounts, names, narrations or file names.
- Reports keep only what is needed to display them; raw descriptions and balances are not retained.
- Secrets come from environment variables (`.env`, gitignored).
