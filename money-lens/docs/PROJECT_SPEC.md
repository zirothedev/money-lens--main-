# Project Spec: Where'd My Money Go?

**Tagline:** Your bank statement, finally understandable.

## Non-negotiable principles
1. The bank statement is the source of truth; report only what it provides.
2. Never invent information. No narration -> `narration = ""`. No identifiable recipient -> `recipient = None`.
   Never infer the purpose of a transfer. Never write "purpose unknown" at the data level.
3. No user input is needed to generate a report (no categorizing, no "who was this?").
4. Simplify presentation, never change facts.
5. All financial calculations are deterministic Python/`Decimal` (no LLM, no floats).
6. Preserve original information (display narration where present, empty where absent).

## MVP scope
Upload PDF/CSV -> extract and normalize transactions -> identify recipients where stated -> totals received/sent
-> group outgoing by recipient (ranked) -> show unidentified outgoing separately -> simple report.
Out of scope: investments, credit scores, budgets, loans, crypto, bank integrations, financial advice.

## Journey
Landing -> Upload (modal) -> Processing -> Report ready -> Money report.

## Report contents
Header and period; total received / sent with counts; "Where your money went" (recipients ranked by total sent);
unidentified recipients; all transactions (date, recipient, amount, in/out, narration); expandable recipient details.

## Privacy lifecycle
Upload -> private temporary storage -> process -> save report -> delete original -> delete temporary data.
Failure/abandonment: expires automatically after a configurable window.

## Stack
Python, Django, Django Templates, HTML, CSS, vanilla JS. SQLite locally, PostgreSQL-ready (`DATABASE_URL`).
Libraries: pdfplumber, Python `csv`, dj-database-url, python-dotenv.

## Phases
1. Foundation (done)  2. Temporary upload (done)  3. Extraction/normalization (done)  4. Report engine (done)
5+. Frontend (landing, upload modal, processing UI, report dashboard), then hardening/deployment.

## Brand
Purple brand colour (replaces the earlier neon green); visual language follows the separate design reference.
