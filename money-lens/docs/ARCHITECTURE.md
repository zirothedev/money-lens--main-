# Architecture

```
statements/   TEMPORARY data: StatementProcessing model, validators, private storage, cleanup, upload/process views
processing/   Pure extraction layer (no DB): parsing, columns, readers, recipients, normalizer, validation, pipeline
reports/      PERSISTENT data: Report, ReportRecipient, ReportTransaction, deterministic engine, services, views
accounts/     Custom User, login/logout/register
config/       Settings, URLs, health check
```

## Data flow
`upload` -> `validators` -> `storage.save_temp_file` (private, random name) -> `StatementProcessing(uploaded)`
-> `generate_report_for_job` claims the job (atomic `uploaded -> processing`)
-> `processing.pipeline.extract_statement` -> `reports.engine.build_report_data` -> `save_report` (one transaction)
-> `delete_statement_job` (file + record).

## Temporary vs persistent
- Temporary: `StatementProcessing` + the file. No raw transactions are ever stored; they exist only in memory.
- Persistent: `Report*` tables. They keep date, amount, direction, counterparty name, narration, reference.
  They do NOT keep the original file, raw descriptions or balances.

## Extraction (processing/)
CSV: header detection (preamble allowed), delimiter sniffing, encodings, column aliasing.
PDF: pdfplumber tables first; text-line fallback. Direction is only set when the statement states it
(debit/credit columns, DR/CR markers, a type column, signed amounts if the file contains negatives, or a running
balance that reconciles exactly). Otherwise the row is rejected, never guessed.
PDF tables are read by ruling lines first. If that rejects more than 5% of rows (or finds none), the table is rebuilt from character positions (`pdf_positioned.py`; sections, split rows and stranded row heads are handled) and the cleaner of the two readings is kept, then the text-line fallback.
Recipients: only explicit `... TO <name>` (debits) / `... FROM <name>` (credits), or a Beneficiary/Sender column.
Rejected rows are reported by row number and reason code only (no financial data).

## Parser version
`processing/version.py: PARSER_VERSION` is part of a report's fingerprint. When parsing improves, bump it: the same statement
uploaded again produces a fresh report with the better names, while uploading it twice on the same version still returns the
existing report. Old reports are left untouched (delete them in the admin if you don't want them).

## Duplicate protection
- Upload: same file hash for the same user while a job is active -> 409.
- Row level: a row is a duplicate only if it is identical AND carries a reference or running balance
  (so two genuine identical payments with neither are both kept).
- Report: per-user unique fingerprint of the transactions; saving the same statement again returns the existing report.
- Processing: atomic status claim prevents double processing.

## Report engine rules
Decimal only; recipients grouped case/whitespace-insensitively; ranked by total desc, count desc, name; output is
independent of input order; more than one currency -> refused (`multiple_currencies`).

## Known MVP limits
No OCR (scanned PDFs rejected); merchant names on POS/airtime lines stay unidentified; no-year dates are rejected;
single currency per statement; processing is synchronous (move to a task queue later).
