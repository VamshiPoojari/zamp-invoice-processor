# Invoice Processing — Process Map

## The one-line idea
**AI reads the invoice. Rules make the decision.**
The AI is good at reading messy documents. It is not trustworthy at arithmetic or at
following money rules consistently. So the AI only *extracts* data; plain code does every
check and makes the final decision. That makes every decision explainable and repeatable.

---

## Inputs
| Input | What it is | Format |
|---|---|---|
| Invoice | The vendor's bill | PDF (text-based **or** scanned image) |
| Vendor master | Approved vendors: name, tax ID, bank account, payment terms | CSV |
| Purchase orders | PO number, vendor, line items, total, amount already invoiced, status | CSV |
| Invoice history | Every invoice processed before (for duplicate checks) | Database (built up by the app) |

## Output
One of three decisions, always with a list of reasons:
- **APPROVE** — safe to pay
- **HOLD FOR REVIEW** — a human must look; the app says exactly what to check
- **REJECT** — do not pay; the app says why

---

## The stages (what happens, in order)

### Stage 1 — Intake
- Receive the PDF, give it a run ID, save it.
- Take a "fingerprint" of the file (SHA-256 hash). If the exact same file was already processed → flag it.

### Stage 2 — Read the document
- Check whether the PDF has real text in it.
  - **Has text** → pull the text out directly (fast, free, accurate).
  - **No text (scanned)** → turn the page into an image and send it to an AI model that can read images.

### Stage 3 — Extract fields (AI)
The AI returns structured data:
vendor name, vendor tax ID, bank account, invoice number, invoice date, due date,
PO reference, currency, line items (description, qty, unit price, amount), subtotal, tax, total.
- **Rule for the AI: if a field is not on the page, return empty — never guess.**

### Stage 4 — Sanity checks (code)
- Are the critical fields present? (vendor, invoice number, date, total)
- Do line items add up to the subtotal?
- Does subtotal + tax = total?
- Is the date sensible (not in the future, not years old)?

### Stage 5 — Vendor check (code)
- Is this vendor on the approved list? (Matches name loosely: "Acme Corp" = "ACME Corporation Pvt Ltd", and confirms with tax ID.)
- Does the bank account on the invoice match the one on file?

### Stage 6 — PO match (code)
- **PO number on invoice** → look it up. Does it belong to this vendor? Is it still open?
- **No PO number** → search this vendor's open POs for one that fits the amount and items.
  If exactly one fits → suggest it, but send to a human (an *inferred* match is never auto-approved).

### Stage 7 — Amount check (code)
- Compare **pre-tax** amounts (POs don't include tax).
- Already billed = amount invoiced before this system + invoices this system approved.
- Already billed + this invoice ≤ PO total → pass.
- Over the PO total, but by no more than 2% (rounding/freight) → pass with a note.
- More than 2% over → hold (needs a PO amendment or credit note).

### Stage 8 — Duplicate check (code)
- Same vendor + same invoice number (after cleaning: "INV-0042" = "inv 42" = "42") → duplicate.
- Same vendor + same total + date within 7 days → *possible* duplicate.

### Stage 9 — Decide (code)
| If any of these… | Decision |
|---|---|
| Vendor not approved · confirmed duplicate · PO belongs to a different vendor | REJECT |
| Missing critical field · maths doesn't add up · over tolerance · inferred PO · possible duplicate · bank account changed · unreadable scan | HOLD |
| Everything passes | APPROVE |
Reject beats Hold beats Approve. Every triggered rule is listed as a reason.

### Stage 10 — Record
- Save everything (extracted data, every check, decision, reasons) to the database.
- If approved, add the amount to the PO's "already invoiced" total.
- Shows up in the dashboard.

---

## Happy path
Clean text PDF · approved vendor · PO number on invoice · amounts match → APPROVE.

## Edge cases (4)
| # | Scenario | Why it's realistic | Expected result |
|---|---|---|---|
| 1 | **Split PO, overbilled.** Vendor bills a ₹/$ PO in three parts. The 3rd invoice looks fine alone, but the three together exceed the PO. | Vendors split POs all the time; a person checking one invoice at a time misses it. | HOLD — "Cumulative billing exceeds PO by X" |
| 2 | **Disguised duplicate.** Same invoice sent again, re-scanned, invoice number written "INV-0042" instead of "42". File fingerprint is different. | The #1 way companies pay twice. | REJECT — "Duplicate of invoice processed on <date>" |
| 3 | **Scanned invoice, no PO number.** Image-only PDF; PO number missing. | Small vendors often send phone scans and forget the PO. | HOLD — "PO inferred as PO-1003 (matches vendor + amount). Please confirm." |
| 4 | **Bank account changed.** Invoice looks perfect, but the bank details differ from the vendor master. | Classic invoice fraud (fake "we changed banks" invoices). | HOLD (high risk) — "Bank account differs from vendor record. Verify by phone before paying." |

---

## Assumptions (say these in the interview)
- One currency (USD) for simplicity.
- Tolerance = cumulative billing may exceed the PO total by up to 2%.
- One invoice = one PDF; one PO per invoice.
- Vendor master and POs are CSV files standing in for the company's procurement system.
- The process recommends a decision; a human still releases the payment.
- Free AI models are used (OpenRouter `:free`). With real company data you'd use a paid,
  no-data-retention plan.
