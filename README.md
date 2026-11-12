# Invoice Processor — PDF to reasoned decision

Zamp AI Solutions Analyst case study · **PS-1 Finance / AP**

Upload a vendor invoice PDF (clean or scanned). The process reads it with AI, checks it against
the vendor master, purchase orders and invoice history, and returns **APPROVE / HOLD FOR REVIEW / REJECT**
with the reasons and who needs to act next. Every stage is visible as it runs, and a dashboard
tracks every run, the money at stake, and the reviewer queue.

## Design principle
**AI reads the invoice. Rules make the decision.**
The model only extracts fields (it's good at messy documents). Every check and the final decision is
deterministic code: the same invoice always gets the same answer, and every answer can be explained.

## The 10 stages
| # | Stage | Engine | What it does |
|---|---|---|---|
| 1 | Intake | System | SHA-256 fingerprint of the file |
| 2 | Read | Code | Text PDF → extract text directly; no text layer → render page as image |
| 3 | Extract | **AI** | Structured fields, with the rule "never guess – null if absent" |
| 4 | Sanity | Rules | Required fields, line items = subtotal, subtotal + tax = total, date sanity |
| 5 | Vendor | Rules | Approved vendor (tax ID first, then fuzzy name), bank account vs vendor master |
| 6 | PO match | Rules | Explicit PO: exists, right vendor, open. Missing PO: score the vendor's open POs (60% amount fit + 40% description fit) |
| 7 | Amount | Rules | Cumulative billing (prior + this invoice, pre-tax) ≤ PO total + 2% tolerance |
| 8 | Duplicate | Rules | Same file · same normalised invoice number ("INV-0042" = "42") · same vendor + amount within 7 days · "COPY/RESENT" marks |
| 9 | Decide | Rules | Any REJECT → REJECT; else any HOLD → HOLD; else APPROVE. Each issue mapped to an owner and action |
| 10 | Record | System | Saved to SQLite → dashboard, duplicate memory, PO consumption |

## Scenarios (in `sample_invoices/`, run in this order)
| # | Scenario | What makes it hard | Result |
|---|---|---|---|
| 1 | Happy path | – | APPROVE |
| 2 | Split PO, over-billed | Each invoice looks fine alone; cumulative billing exceeds the PO | HOLD – Procurement: amend PO or get credit note |
| 3 | Disguised duplicate | Re-sent copy, number "42" vs "INV-0042", different date format, different file hash | REJECT |
| 4 | Scanned, no PO number | Image-only PDF (AI vision); vendor has two open POs | HOLD – suggests PO-1004 (93%) vs PO-1005 (26%) |
| 5 | Bank account changed | Perfect invoice, new bank details ("we changed banks") – classic fraud | HOLD, HIGH RISK – Treasury: call back on number on file |

Also handled: re-uploading any file (REJECT, exact duplicate), a corrupt / non-PDF file and AI outages
(HOLD → manual processing — nothing is ever lost), and a "COPY"-marked invoice with no original on record (HOLD).

## Judgment calls
- **Inferred POs are never auto-approved**, however high the score – where money goes is a human decision.
- **A HOLD doesn't consume PO budget** until a reviewer approves it, so one bad invoice can't block a good one.
- **Root cause over noise:** a duplicate also makes the PO look over-billed; only the duplicate is reported as the problem.
- **Bank-change verification uses contact details from our records, never from the invoice.**
- **Compare pre-tax amounts** against POs – POs don't carry tax.
- **Free-model resilience:** model fallback chain + key rotation + retries; extractions are cached by file
  fingerprint so a re-run never spends AI quota (toggle off to force a fresh read).

## Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "OPENROUTER_API_KEY1=sk-or-..." > .env
.venv/bin/streamlit run app.py
```
Regenerate test data: `.venv/bin/python scripts/make_test_data.py` ·
Full pipeline test (no AI calls): `.venv/bin/python scripts/test_pipeline.py`

## Stack
Python · Streamlit (UI) · PyMuPDF (PDF text + rendering) · OpenRouter free vision models (extraction) ·
RapidFuzz (fuzzy matching) · SQLite (history) · ReportLab + Pillow (synthetic invoices)

## Assumptions & what I'd build next
Single currency (USD) · one PO per invoice · CSVs stand in for the ERP · the process recommends, a human
releases payment. Next: email-inbox intake, 3-way match against goods receipts, multi-currency,
per-vendor tolerance, vendor reply drafts, and a paid zero-retention model for real data.
