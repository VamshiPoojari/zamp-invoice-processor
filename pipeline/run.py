"""
The whole process in one function:  process_invoice(pdf_bytes, filename)

It runs the 10 stages from PROCESS_MAP.md in order. After each stage it calls
`on_event(...)` so the UI can show progress live. If anything breaks (bad PDF,
AI down), the invoice is not lost: it is sent to HOLD for a human, with the reason.
"""
import time
import traceback

from pipeline import checks as C
from pipeline import db
from pipeline.decide import decide
from pipeline.extract import extract_fields, intake, read_pdf

STAGES = [
    ("intake", "Intake", "Fingerprint the file"),
    ("read", "Read document", "Text PDF or scanned image?"),
    ("extract", "AI extraction", "Pull out invoice fields"),
    ("sanity", "Sanity checks", "Do the numbers add up?"),
    ("vendor", "Vendor check", "Approved vendor? Same bank account?"),
    ("po", "PO match", "Find the purchase order"),
    ("amount", "Amount check", "Within the PO amount?"),
    ("duplicate", "Duplicate check", "Seen this invoice before?"),
    ("decide", "Decision", "Approve, hold or reject"),
    ("record", "Record", "Save to history"),
]


def _status_of(checks):
    if any(c["status"] == "fail" for c in checks):
        return "fail"
    if any(c["status"] == "warn" for c in checks):
        return "warn"
    return "pass"


def process_invoice(pdf_bytes, filename, use_cache=True, on_event=None, on_log=None):
    """Returns a result dict with fields, checks, decision, timeline and run_id.

    on_event(stage_key, status, summary, seconds)  status: running / pass / warn / fail
    on_log(message)                                  small progress messages (e.g. AI retries)
    """
    on_event = on_event or (lambda *a: None)
    on_log = on_log or (lambda m: None)
    timeline, checks = [], []
    fields, info, context, meta = {}, {}, {}, {}
    t_start = time.time()

    def stage(key, fn):
        """Run one stage, time it, and report it."""
        on_event(key, "running", "", 0)
        t = time.time()
        status, summary, value = fn()
        secs = round(time.time() - t, 2)
        timeline.append({"stage": key, "status": status, "summary": summary, "seconds": secs})
        on_event(key, status, summary, secs)
        return value

    try:
        # 1. Intake
        def _intake():
            m = intake(pdf_bytes)
            return "pass", f"{filename} · {m['size_kb']} KB · fingerprint {m['sha256'][:10]}…", m
        meta = stage("intake", _intake)

        # 2. Read
        def _read():
            r = read_pdf(pdf_bytes)
            if r["method"] == "text":
                return "pass", f"Text PDF – {r['text_chars']} characters, {r['pages']} page(s)", r
            return "warn", f"No text layer – scanned image, {r['pages']} page(s). Using AI vision.", r
        read = stage("read", _read)

        # 3. Extract (AI)
        def _extract():
            f, i = extract_fields(read, meta["sha256"], use_cache=use_cache, log=on_log)
            src = "saved result (no AI request)" if i.get("cached") else i["model"]
            found = sum(v not in (None, [], "") for k, v in f.items() if k != "extraction_confidence")
            return "pass", f"{found} fields extracted via {src} · confidence {f.get('extraction_confidence')}", (f, i)
        fields, info = stage("extract", _extract)

        vendors, pos = C.load_reference()
        history = db.all_runs()

        # 4–8. Rule checks
        def _checks(key, fn):
            def run():
                new = fn()
                checks.extend(new)
                bad = [c for c in new if c["status"] != "pass"]
                if bad:
                    summary = bad[0]["message"]
                elif key == "sanity":
                    summary = f"All {len(new)} checks passed – fields present, maths adds up, date OK."
                else:
                    summary = new[0]["message"] if new else "Skipped"
                return _status_of(new) if new else "pass", summary, None
            stage(key, run)

        _checks("sanity", lambda: C.sanity_checks(fields))

        def _vendor():
            out, context["vendor"] = C.vendor_checks(fields, vendors)
            return out
        _checks("vendor", _vendor)

        def _po():
            out, context["po"], context["po_inferred"] = C.po_checks(fields, context["vendor"], pos)
            return out
        _checks("po", _po)

        def _amount():
            out, context["amounts"] = C.amount_checks(fields, context["po"])
            return out
        _checks("amount", _amount)

        _checks("duplicate", lambda: C.duplicate_checks(fields, context["vendor"], meta["sha256"], history))

    except Exception as e:  # graceful failure → a human takes over
        on_log(f"Error: {e}")
        checks.append(C._check("Processing", "Automatic processing", "fail",
                               f"The invoice could not be processed automatically: {e}", effect="hold"))
        timeline.append({"stage": "error", "status": "fail", "summary": str(e), "seconds": 0,
                         "trace": traceback.format_exc(limit=3)})

    # 9. Decide
    result = {}

    def _decide():
        result.update(decide(checks, fields, context))
        status = {"APPROVE": "pass", "HOLD": "warn", "REJECT": "fail"}[result["decision"]]
        return status, result["headline"], None
    stage("decide", _decide)

    # 10. Record
    def _record():
        vendor, po = context.get("vendor"), context.get("po")
        record = {"fields": fields, "info": info, "checks": checks, "timeline": timeline,
                  "decision": result, "amounts": context.get("amounts"),
                  "po_candidates": (po or {}).get("candidates"),
                  "total_seconds": round(time.time() - t_start, 1)}
        run_id = db.save_run({
            "filename": filename, "sha256": meta.get("sha256"), "decision": result["decision"],
            "vendor_id": vendor["vendor_id"] if vendor else None,
            "vendor_name": (vendor or {}).get("vendor_name") or fields.get("vendor_name"),
            "invoice_number": fields.get("invoice_number"),
            "invoice_number_norm": C.norm_invoice_number(fields.get("invoice_number")),
            "invoice_date": fields.get("invoice_date"),
            "po_number": po["po_number"] if po else None,
            "po_inferred": int(bool(context.get("po_inferred"))),
            "subtotal": fields.get("subtotal"), "total": fields.get("total"),
            "reasons": result["reasons"], "record": record,
        })
        result["run_id"] = run_id
        return "pass", f"Saved as run #{run_id}", None
    stage("record", _record)

    return {"run_id": result["run_id"], "fields": fields, "info": info, "checks": checks,
            "decision": result, "timeline": timeline, "context": context}
