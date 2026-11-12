"""
STAGE 1–3: Intake → Read the PDF → Extract fields with AI.

  intake()          fingerprint the file (SHA-256) so we can spot the exact same file again
  read_pdf()        text PDF  → pull the text out directly (free, exact)
                    scanned   → turn each page into an image for the AI to look at
  extract_fields()  ask the AI to return the invoice fields as JSON
"""
import base64
import hashlib
import json
import re
from pathlib import Path

import pymupdf

from pipeline.config import ROOT
from pipeline.llm import call_llm, parse_json

CACHE_DIR = ROOT / ".cache"
MIN_TEXT_CHARS = 50  # less text than this → treat as a scanned image


# ---------------------------------------------------------------- Stage 1
def intake(pdf_bytes):
    return {
        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "size_kb": round(len(pdf_bytes) / 1024, 1),
    }


# ---------------------------------------------------------------- Stage 2
def read_pdf(pdf_bytes, max_pages=3):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc).strip()
    result = {"pages": len(doc), "text_chars": len(text)}

    if len(text) >= MIN_TEXT_CHARS:
        result.update(method="text", text=text, images=[])
    else:
        images = [page.get_pixmap(dpi=150).tobytes("png") for page in list(doc)[:max_pages]]
        result.update(method="vision", text="", images=images)
    return result


# ---------------------------------------------------------------- Stage 3
PROMPT = """You are an accounts-payable data extraction assistant.
Extract the fields below from this vendor invoice and return ONLY a JSON object.

STRICT RULES
- If a field is not clearly present on the invoice, use null. NEVER guess or invent values.
- Copy invoice_number and po_number exactly as printed (keep prefixes like "INV-").
- Convert dates to YYYY-MM-DD.
- Numbers: plain numbers only, no currency symbols or commas (e.g. 4250.00).
- bank_account: digits only, exactly as printed.
- notes: copy any message from the vendor (e.g. about changed bank details, resent/copy, partial billing).

JSON FORMAT
{
  "vendor_name": string|null,
  "vendor_tax_id": string|null,
  "invoice_number": string|null,
  "invoice_date": "YYYY-MM-DD"|null,
  "due_date": "YYYY-MM-DD"|null,
  "po_number": string|null,
  "currency": string|null,
  "line_items": [{"description": string, "quantity": number|null, "unit_price": number|null, "amount": number|null}],
  "subtotal": number|null,
  "tax_amount": number|null,
  "total": number|null,
  "bank_name": string|null,
  "bank_account": string|null,
  "notes": string|null,
  "document_marks": string|null,
  "extraction_confidence": "high"|"medium"|"low"
}
document_marks = any stamp or title marking like "COPY", "RESENT", "DUPLICATE", "PAID" (else null).
extraction_confidence = "low" if the document is hard to read or many fields are unclear."""


def _build_messages(read_result):
    if read_result["method"] == "text":
        content = PROMPT + "\n\nINVOICE TEXT:\n" + read_result["text"]
        return [{"role": "user", "content": content}]
    parts = [{"type": "text", "text": PROMPT + "\n\nThe invoice is attached as image(s)."}]
    for img in read_result["images"]:
        b64 = base64.b64encode(img).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return [{"role": "user", "content": parts}]


def _to_number(v):
    """Turn '$4,250.00' / '4250' / 4250 into 4250.0 (or None)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    cleaned = re.sub(r"[^\d.\-]", "", str(v))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean(fields):
    """Make the AI output tidy and predictable for the rule checks."""
    for k in ("subtotal", "tax_amount", "total"):
        fields[k] = _to_number(fields.get(k))
    items = fields.get("line_items") or []
    fields["line_items"] = [
        {"description": it.get("description"),
         "quantity": _to_number(it.get("quantity")),
         "unit_price": _to_number(it.get("unit_price")),
         "amount": _to_number(it.get("amount"))}
        for it in items if isinstance(it, dict)
    ]
    if fields.get("bank_account"):
        fields["bank_account"] = re.sub(r"\D", "", str(fields["bank_account"])) or None
    for k, v in list(fields.items()):
        if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a"):
            fields[k] = None
    return fields


def extract_fields(read_result, sha256, use_cache=True, log=print):
    """Returns (fields_dict, info_dict). Uses a local cache so the same file
    never spends a second free AI request (unless use_cache=False)."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{sha256}.json"
    if use_cache and cache_file.exists():
        saved = json.loads(cache_file.read_text())
        log("Same file seen before – reusing saved extraction (no AI request used)")
        return saved["fields"], {**saved["info"], "cached": True}

    log(f"Sending invoice to AI ({read_result['method']} mode)…")
    reply, model = call_llm(_build_messages(read_result), log=log)
    fields = _clean(parse_json(reply))
    info = {"model": model, "method": read_result["method"], "cached": False}
    cache_file.write_text(json.dumps({"fields": fields, "info": info}, indent=2))
    log(f"Extracted with {model}")
    return fields, info
