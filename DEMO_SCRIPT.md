# 5-minute demo script (your own voice, no AI voice)

**Before recording:** open the live app → sidebar **Reset demo** → Process invoice page.
Leave "Reuse saved AI reading" ON, except in step 2 where you switch it OFF for one live AI read.

---

### 0:00–0:30 · The problem (on the Process invoice page)
> "AP teams open hundreds of PDF invoices a month, find the PO in a spreadsheet, check the numbers and decide.
> It's slow and error-prone. I built a process that takes an invoice PDF and returns a decision —
> approve, hold, or reject — with the reasons and who acts next. The principle: **AI reads the invoice,
> rules make the decision.** The AI only extracts data; every check and decision is plain code, so it's
> consistent and explainable."

### 0:30–1:45 · Happy path (sample 1)
- Select **Happy path – Northwind**. Switch **Reuse saved AI reading OFF**. Click **Run process**.
> "Left is the invoice. Right, each stage runs live. Intake fingerprints the file. Read sees it's a text PDF.
> Now the AI extracts the fields — a free vision model via OpenRouter, with automatic fallback to backup
> models if one is busy. Then the rule checks: maths adds up, Northwind is approved and matched by tax ID,
> bank account matches our records, PO-1001 exists and is open, the amount fits, not a duplicate."
- Point at the green card: "Approve, all 11 checks passed, and the next action: schedule payment by the due date."
- Click the **Extracted data** tab briefly. Switch **Reuse saved AI reading back ON**.

### 1:45–2:30 · Edge case: disguised duplicate (sample 3)
> "Same invoice, resent. Different file, the number written '42' instead of 'INV-0042', different date format.
> A file-hash check would miss it."
- Run → **Reject: duplicate invoice.**
> "I normalise invoice numbers, so both mean 42. Note it does NOT also tell Procurement the PO is over-billed —
> that's a side effect of the duplicate, so it's a side note, not a task."

### 2:30–3:15 · Edge case: bank account changed (sample 5)
- Run → **Hold, HIGH RISK.**
> "Everything matches the PO, but the bank account differs from our vendor master, with a 'we changed banks' note.
> That's the classic invoice-fraud pattern. Treasury is told to call back on the number in OUR records,
> never the one on the invoice."

### 3:15–3:50 · Edge case: scanned, no PO (sample 4) — quick
- Run → show **Read document** turning amber: "no text layer, so it uses AI vision."
- Hold → open **PO & amounts** tab: "No PO on the invoice. It scored this vendor's two open POs — PO-1004 at 93%
  versus PO-1005 at 26%. Inferred matches are never auto-approved — a human confirms."
- (If time) mention split PO: "Sample 2 catches a third invoice that pushes cumulative billing past the PO."

### 3:50–4:45 · Dashboard
- Open **Dashboard**.
> "Every run: straight-through rate, value approved, value stopped, high-risk flags. The decision mix,
> and why invoices were stopped. The reviewer queue — the process never pays a HOLD on its own."
- Open the Brightline item, type a note "Called vendor on number on file – confirmed", click **Approve for payment**.
> "It moves to Approved after review, with an audit note. Below is the full history — filter, search,
> click any run to see every check, and export to CSV."

### 4:45–5:00 · Close
> "It handles clean and scanned PDFs, fails safely — a broken file or AI outage goes to a human, never lost —
> and every decision is explainable. Next I'd add email intake, 3-way match with goods receipts, and multi-currency."

---

## Likely interview questions
- **Why not let the AI decide?** Money rules need consistency and an audit trail; LLMs can misread maths and vary run to run.
- **Why 2% tolerance?** Covers rounding/freight; it's one number in `pipeline/config.py`, per-company or per-vendor in production.
- **Why does a HOLD not consume the PO?** Otherwise a bad invoice blocks the next legitimate one.
- **What if the AI misreads?** Sanity checks catch arithmetic mismatches; low confidence → HOLD; missing fields are null, never guessed.
- **Free models are flaky?** Fallback chain + key rotation + retry; cached extractions by file fingerprint; outage → HOLD.
- **Scale?** Each invoice is independent → parallel workers; SQLite → Postgres; CSVs → ERP API.
