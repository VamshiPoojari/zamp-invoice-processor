"""
Test the rule checks (Stages 4–8) on all sample invoices, in demo order.
Uses the saved AI extractions from Step 5 (no AI requests).

  .venv/bin/python scripts/test_checks.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import db  # noqa: E402
from pipeline.checks import run_all_checks  # noqa: E402
from pipeline.extract import extract_fields, intake, read_pdf  # noqa: E402

ICON = {"pass": "✅", "warn": "🟡", "fail": "❌"}

db.reset()  # start with empty history
for path in sorted(Path("sample_invoices").glob("*.pdf")):
    pdf = path.read_bytes()
    meta = intake(pdf)
    fields, _ = extract_fields(read_pdf(pdf), meta["sha256"], log=lambda m: None)
    checks, ctx = run_all_checks(fields, meta["sha256"], db.all_runs(), log=lambda m: None)

    print("\n" + "=" * 90 + f"\n{path.name}")
    for c in checks:
        flag = " 🚩HIGH RISK" if c["high_risk"] else ""
        effect = f" → {c['effect'].upper()}" if c["effect"] else ""
        print(f"  {ICON[c['status']]} [{c['stage']}] {c['check']}{effect}{flag}\n      {c['message']}")

    # Save to history so later invoices can be compared against it.
    # (Step 7 will add the real decision; for now we save it as PENDING.)
    po = ctx["po"]
    db.save_run({"filename": path.name, "sha256": meta["sha256"], "decision": "PENDING",
                 "vendor_id": ctx["vendor"]["vendor_id"] if ctx["vendor"] else None,
                 "vendor_name": fields.get("vendor_name"), "invoice_number": fields.get("invoice_number"),
                 "invoice_number_norm": ctx["invoice_number_norm"], "invoice_date": fields.get("invoice_date"),
                 "po_number": po["po_number"] if po else None, "po_inferred": int(ctx["po_inferred"]),
                 "subtotal": fields.get("subtotal"), "total": fields.get("total")})
db.reset()  # leave history clean for the real app
