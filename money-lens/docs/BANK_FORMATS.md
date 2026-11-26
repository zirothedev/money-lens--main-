# Bank-specific statement formats

Banks write structured text into the description. `processing/formats.py` reads the formats listed here
**exactly as written** and never guesses. Anything that matches no format falls through to the generic rules in
`processing/recipients.py` (explicit `TO <name>` / `FROM <name>`), and if no name is stated the transaction stays
unidentified.

## GTBank (GTCO)
| Format | Example (shape) | Recipient | Other fields |
|---|---|---|---|
| Instant payment | `Instant Payment Outward <ref> NIP TRANSFER TO <BANK> - <NAME>` | `<NAME>` | `via` = `<BANK>`; a note before `TO` (e.g. `ICE CREAM`) or after the bank (`POS TRANSFER-`) becomes the narration |
| Airtime / data | `Airtime Purchase ... FROM <you> TO MTN AIRTIME COLLECTION SALES` | text after the last `TO` | |
| Direct debit | `NIPS DIRECT DEBIT ... TO <COMPANY> FROM<digits>: - <note>` | `<COMPANY>` (stops at digits / `FROM` / `:`) | note after ` - ` is the narration |
| App transfer | `TRANSFER BETWEEN CUSTOMERS VIA GTWORLD [note] FROM <a> TO <b>` | `<b>` (debit) / `<a>` (credit) | note is the narration |
| POS / card | `... POS PUR [T] <MERCHANT><CITY> <ST>NG <stan> ...` | merchant exactly as written | the fixed-width name field is 23 characters, so long names arrive truncated (`OPAY KURE BUSINESS ENTE`); the city is removed |
| Web purchase | `... WEB PUR <ID> <MERCHANT> ...` | merchant as written | rows sharing the statement's own merchant ID take its most common spelling (the bank blanks a random letter, so one merchant otherwise appears under many spellings) |

Not covered yet: credits (senders), other banks. To add a bank: add a handler to `processing/formats.py`, add its
shapes to `processing/tests/test_formats.py` (use fictional names), and bump `PARSER_VERSION` in
`processing/version.py` so re-uploads create fresh reports.

## Moniepoint
Layout: a wide (19-column) table drawn as shaded bands with no gridlines. The generic table detector can't read it, so
`processing/pdf_positioned.py` rebuilds it from character positions (rows = blocks separated by larger vertical gaps; columns =
header x-positions; a row cut by a page break is merged back). Amounts come from **Settlement Debit / Settlement Credit**, so totals
reconcile with the summary printed on the statement (this includes the bank's N10 transfer fee inside each transfer's debit).

| Narration shape | Recipient | Other fields |
|---|---|---|
| `TRANSFER TO <NAME> <INSTITUTION> *****1234` | `<NAME>` (split from the bank using the *Beneficiary Institution* column) | `via` = institution |
| `TRANSFER TO POS Transfer- <NAME> ...` | `<NAME>` | narration `POS Transfer` |
| `<PAYER> TO <PAYEE> MONIEPOINT *****1234` | payee (debit) / payer (credit) | `via` = Moniepoint MFB |
| `POS purchase at [T] <MERCHANT> <counter>` | merchant exactly as written (the bank truncates it) | |
| `AIRTIME TO <phone> <NETWORK>` | `<phone> <NETWORK>` | |
| `BILL PAYMENT FOR ... <account>` | the biller (*Beneficiary Institution* column) | |
| `Stamp duty`, `Value Added Tax`, `CARD REQUEST AND DELIVERY...` | the label the statement gives | |
| anything else with a Beneficiary column | the Beneficiary column | narration = the Narration column (what the sender wrote), `via` = institution |

## OPay
Layout: borderless shaded rows, tiny font, **several account sections in one PDF** (Wallet Account, Savings Account), each with its
own title, summary box and header. The PDF reader finds every header, reads each section with its own column positions, and joins a
row whose first line(s) were stranded at the bottom of the previous page. Every section's totals reconcile with its printed summary.

| Description shape | Recipient / sender | Other fields |
|---|---|---|
| `Transfer to <NAME> \| <BANK> \| <account>` | `<NAME>` (a dash inside a name is kept) | `via` = `<BANK>`; `POS Transfer-<NAME>` gives narration `POS Transfer` |
| `Transfer from <NAME> \| <BANK> \| <acct> \| <note>` | `<NAME>` (sender) | narration = the note, minus the bank's long reference numbers |
| `OPay Card Payment \| <acquirer> \| <terminal> \| <code> \| [T] <MERCHANT> [counter terminal] [city] <ST>NG` | merchant exactly as written | |
| `Mobile Data` / `Airtime \| <phone> \| <network> [\| plan]` | `<phone> <network>` | narration = plan |
| `Auto-save to OWealth Balance` | `OWealth Balance` | narration `Auto-save` |
| `USSD Charge`, `VAT on ...`, `... Fee`, `OWealth Interest Earned`, `OWealth Withdrawal (Transaction Payment)` | the label the statement gives | |

Note: transfers between a wallet and its savings appear in BOTH sections (a debit in one, a credit in the other).

## Also read from the statement header (PDF key/value block or CSV preamble)
- `Currency` (e.g. `NIGERIAN NAIRA` -> NGN)
- `Statement Period`, a `Period: 26 Sep 2026 - 25 Oct 2026` line, or a `Date 28/07/2026 - 26/10/2026` line (used for the report period when it covers every transaction)
