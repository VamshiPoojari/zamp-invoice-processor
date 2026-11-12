"""
Test Stage 1–3 on invoice PDFs from the terminal.

  .venv/bin/python scripts/test_extract.py sample_invoices/1_happy_path_northwind.pdf
  .venv/bin/python scripts/test_extract.py sample_invoices/*.pdf

Each NEW file uses 1 free AI request (files seen before come from the cache).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.extract import extract_fields, intake, read_pdf  # noqa: E402

for path in sys.argv[1:]:
    print("=" * 70, "\n", path)
    pdf = Path(path).read_bytes()
    meta = intake(pdf)
    read = read_pdf(pdf)
    print(f"Fingerprint {meta['sha256'][:12]}…  | mode: {read['method']} | text chars: {read['text_chars']}")
    fields, info = extract_fields(read, meta["sha256"])
    print(json.dumps(fields, indent=2))
