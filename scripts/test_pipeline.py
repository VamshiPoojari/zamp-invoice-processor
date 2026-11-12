"""
Run the FULL process on every sample invoice, in demo order, and print the decisions.
Uses saved AI extractions (no AI requests). Starts from empty history.

  .venv/bin/python scripts/test_pipeline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import db  # noqa: E402
from pipeline.run import process_invoice  # noqa: E402

ICON = {"APPROVE": "✅", "HOLD": "🟡", "REJECT": "❌"}

db.reset()
files = sorted(Path("sample_invoices").glob("*.pdf"))
files.append(files[0])  # bonus: upload the happy-path file a second time

for path in files:
    r = process_invoice(path.read_bytes(), path.name)
    d = r["decision"]
    print("\n" + "=" * 90)
    print(f"{path.name}\n{ICON[d['decision']]} {d['decision']} – {d['headline']}")
    for reason in d["reasons"]:
        print(f"   • {reason}")
    for a in d["actions"]:
        print(f"   → [{a['owner']}] {a['action']}")

db.reset()  # leave history clean for the real app
