"""
STAGES 4–8: the rule checks. Plain code — no AI — so results are repeatable and explainable.

Every check returns the same shape:
    {
      "stage":   "Vendor check",
      "check":   "Bank account matches vendor record",
      "status":  "pass" | "warn" | "fail",
      "effect":  None | "hold" | "reject",   # what this means for the decision
      "message": "plain-English explanation",
      "high_risk": True/False                # fraud-type signals get flagged in red
    }
"""
import re
from datetime import date, datetime, timedelta

import pandas as pd
from rapidfuzz import fuzz

from pipeline import db
from pipeline.config import DATA_DIR, DUPLICATE_WINDOW_DAYS, TOLERANCE_PCT

REQUIRED_FIELDS = ["vendor_name", "invoice_number", "invoice_date", "total"]
NAME_MATCH_MIN = 85   # fuzzy vendor-name score (0–100) needed to count as a match


# ---------------------------------------------------------------- helpers
def _check(stage, check, status, message, effect=None, high_risk=False):
    return {"stage": stage, "check": check, "status": status, "effect": effect,
            "message": message, "high_risk": high_risk}


def money(x):
    return "—" if x is None else f"${x:,.2f}"


def load_reference():
    vendors = pd.read_csv(DATA_DIR / "vendors.csv", dtype=str)
    pos = pd.read_csv(DATA_DIR / "purchase_orders.csv",
                      dtype={"po_number": str, "vendor_id": str, "status": str})
    return vendors, pos


def norm_invoice_number(s):
    """'INV-0042', 'inv 42', 'Invoice #42', '42' → '42'  (so disguised duplicates match)."""
    if not s:
        return None
    s = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    s = re.sub(r"^(INVOICE|INV|NO|NUMBER)+", "", s)
    return s.lstrip("0") or "0"


def norm_po(s):
    """'po 1001', 'PO1001', '1001' → 'PO-1001'."""
    if not s:
        return None
    m = re.search(r"(\d+)", str(s))
    return f"PO-{m.group(1)}" if m else str(s).upper().strip()


def norm_company(s):
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    drop = {"inc", "llc", "co", "corp", "corporation", "ltd", "limited", "company", "pvt", "the"}
    return " ".join(w for w in s.split() if w not in drop)


def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def parse_date(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- Stage 4
def sanity_checks(f):
    S = "Sanity checks"
    out = []

    missing = [k for k in REQUIRED_FIELDS if f.get(k) in (None, "")]
    if missing:
        out.append(_check(S, "Critical fields present", "fail",
                          f"Missing on invoice: {', '.join(missing)}. Ask the vendor for a corrected invoice.",
                          effect="hold"))
    else:
        out.append(_check(S, "Critical fields present", "pass",
                          "Vendor, invoice number, date and total all found."))

    if f.get("extraction_confidence") == "low":
        out.append(_check(S, "Document readable", "warn",
                          "The AI reported the document is hard to read. A person should verify the figures.",
                          effect="hold"))

    items = f.get("line_items") or []
    amounts = [i["amount"] for i in items if i.get("amount") is not None]
    sub = f.get("subtotal")
    if amounts and sub is not None:
        diff = round(sum(amounts) - sub, 2)
        if abs(diff) > 0.01:
            out.append(_check(S, "Line items add up to subtotal", "fail",
                              f"Line items total {money(sum(amounts))} but subtotal says {money(sub)} "
                              f"(difference {money(abs(diff))}).", effect="hold"))
        else:
            out.append(_check(S, "Line items add up to subtotal", "pass",
                              f"{len(amounts)} line item(s) sum to {money(sub)}."))

    tot, tax = f.get("total"), f.get("tax_amount") or 0
    if sub is not None and tot is not None:
        diff = round(sub + tax - tot, 2)
        if abs(diff) > 0.01:
            out.append(_check(S, "Subtotal + tax = total", "fail",
                              f"{money(sub)} + {money(tax)} tax ≠ {money(tot)} (off by {money(abs(diff))}).",
                              effect="hold"))
        else:
            out.append(_check(S, "Subtotal + tax = total", "pass",
                              f"{money(sub)} + {money(tax)} tax = {money(tot)}."))

    d = parse_date(f.get("invoice_date"))
    if d:
        today = date.today()
        if d > today:
            out.append(_check(S, "Invoice date sensible", "fail",
                              f"Invoice is dated in the future ({d}).", effect="hold"))
        elif d < today - timedelta(days=365):
            out.append(_check(S, "Invoice date sensible", "fail",
                              f"Invoice is more than a year old ({d}).", effect="hold"))
        else:
            out.append(_check(S, "Invoice date sensible", "pass", f"Dated {d}."))
    return out


# ---------------------------------------------------------------- Stage 5
def vendor_checks(f, vendors):
    S = "Vendor check"
    out = []
    inv_tax = digits(f.get("vendor_tax_id"))
    inv_name = norm_company(f.get("vendor_name"))

    # Try tax ID first (most reliable), then fuzzy name.
    by_tax = vendors[vendors["tax_id"].map(digits) == inv_tax] if inv_tax else vendors.iloc[0:0]
    scores = vendors["vendor_name"].map(lambda n: fuzz.token_sort_ratio(norm_company(n), inv_name))
    best_i = scores.idxmax()
    best_score = scores[best_i]

    if len(by_tax):
        v = by_tax.iloc[0]
        name_score = fuzz.token_sort_ratio(norm_company(v["vendor_name"]), inv_name)
        how = f"tax ID {v['tax_id']}"
        if name_score < NAME_MATCH_MIN:
            out.append(_check(S, "Vendor name matches tax ID", "warn",
                              f"Tax ID belongs to '{v['vendor_name']}' but invoice says "
                              f"'{f.get('vendor_name')}'. Possible impersonation.",
                              effect="hold", high_risk=True))
    elif best_score >= NAME_MATCH_MIN:
        v = vendors.loc[best_i]
        how = f"name (similarity {best_score:.0f}%)"
        if inv_tax:
            out.append(_check(S, "Vendor tax ID matches record", "warn",
                              f"Name matches '{v['vendor_name']}' but tax ID on invoice ({f.get('vendor_tax_id')}) "
                              f"differs from record ({v['tax_id']}).", effect="hold", high_risk=True))
    else:
        out.append(_check(S, "Vendor is approved", "fail",
                          f"'{f.get('vendor_name')}' is not in the approved vendor list. "
                          "Vendor must complete onboarding before any payment.", effect="reject"))
        return out, None

    vendor = v.to_dict()
    if vendor["status"] != "approved":
        out.append(_check(S, "Vendor is approved", "fail",
                          f"{vendor['vendor_name']} ({vendor['vendor_id']}) is marked '{vendor['status']}' "
                          "in the vendor master.", effect="reject"))
    else:
        out.append(_check(S, "Vendor is approved", "pass",
                          f"Matched {vendor['vendor_name']} ({vendor['vendor_id']}) by {how}."))

    inv_acct = digits(f.get("bank_account"))
    if not inv_acct:
        out.append(_check(S, "Bank account matches vendor record", "pass",
                          "No bank details on invoice – payment will go to the account on file."))
    elif inv_acct == digits(vendor["bank_account"]):
        out.append(_check(S, "Bank account matches vendor record", "pass",
                          f"Account ending {inv_acct[-4:]} matches the vendor master."))
    else:
        out.append(_check(S, "Bank account matches vendor record", "fail",
                          f"Invoice asks for payment to {f.get('bank_name') or 'a bank'} account ending "
                          f"{inv_acct[-4:]}, but our record is {vendor['bank_name']} ending "
                          f"{digits(vendor['bank_account'])[-4:]}. Common fraud pattern – verify by phone "
                          "using a number from our records (not the invoice) before paying.",
                          effect="hold", high_risk=True))
    return out, vendor


# ---------------------------------------------------------------- Stage 6
def po_checks(f, vendor, pos):
    S = "PO match"
    out = []
    po_ref = norm_po(f.get("po_number"))

    if po_ref:
        match = pos[pos["po_number"] == po_ref]
        if match.empty:
            out.append(_check(S, "PO exists", "fail",
                              f"{po_ref} is not in the purchase order list.", effect="hold"))
            return out, None, False
        po = match.iloc[0].to_dict()
        out.append(_check(S, "PO exists", "pass", f"{po_ref} found: {po['description']}."))
        if vendor and po["vendor_id"] != vendor["vendor_id"]:
            out.append(_check(S, "PO belongs to this vendor", "fail",
                              f"{po_ref} was issued to vendor {po['vendor_id']}, not {vendor['vendor_id']}.",
                              effect="reject", high_risk=True))
        elif vendor:
            out.append(_check(S, "PO belongs to this vendor", "pass",
                              f"{po_ref} was issued to {vendor['vendor_name'].rstrip('.')}."))
        if po["status"] != "open":
            out.append(_check(S, "PO is open", "fail",
                              f"{po_ref} is {po['status']} – no more invoices should be paid against it.",
                              effect="hold"))
        else:
            out.append(_check(S, "PO is open", "pass", f"{po_ref} is open."))
        return out, po, False

    # No PO on the invoice → try to infer one from this vendor's open POs.
    if not vendor:
        out.append(_check(S, "PO reference", "fail", "No PO number and unknown vendor.", effect="hold"))
        return out, None, False

    sub = f.get("subtotal") or f.get("total") or 0
    desc = " ".join(i.get("description") or "" for i in f.get("line_items") or [])
    open_pos = pos[(pos["vendor_id"] == vendor["vendor_id"]) & (pos["status"] == "open")]
    candidates = []
    for _, p in open_pos.iterrows():
        remaining = float(p["total_amount"]) - float(p["amount_invoiced"]) - db.billed_on_po(p["po_number"])
        if remaining <= 0 or sub > remaining * (1 + TOLERANCE_PCT / 100):
            continue
        amount_fit = 1 - abs(remaining - sub) / remaining          # 1.0 = exact
        text_fit = fuzz.token_set_ratio(desc.lower(), str(p["description"]).lower()) / 100
        score = round(100 * (0.6 * amount_fit + 0.4 * text_fit))
        candidates.append({"po_number": p["po_number"], "description": p["description"],
                           "remaining": remaining, "score": score})
    candidates.sort(key=lambda c: -c["score"])

    if not candidates:
        out.append(_check(S, "PO reference", "fail",
                          f"No PO number on invoice and none of {vendor['vendor_name']}'s open POs can cover "
                          f"{money(sub)}. Ask the requester which PO this belongs to.", effect="hold"))
        return out, None, False

    best = candidates[0]
    others = "; ".join(f"{c['po_number']} ({c['score']}%)" for c in candidates[1:]) or "none"
    out.append(_check(S, "PO reference", "warn",
                      f"No PO number on invoice. Best match: {best['po_number']} – \"{best['description']}\" "
                      f"(match score {best['score']}%; other candidates: {others}). "
                      "Inferred matches are never auto-approved – please confirm.", effect="hold"))
    po = pos[pos["po_number"] == best["po_number"]].iloc[0].to_dict()
    po["candidates"] = candidates
    return out, po, True


# ---------------------------------------------------------------- Stage 7
def amount_checks(f, po):
    S = "Amount check"
    if not po:
        return [], None
    po_total = float(po["total_amount"])
    already = float(po["amount_invoiced"]) + db.billed_on_po(po["po_number"])
    this = f.get("subtotal")
    if this is None:
        this = (f.get("total") or 0) - (f.get("tax_amount") or 0)
    after = already + this
    allowed = po_total * (1 + TOLERANCE_PCT / 100)
    summary = (f"PO total {money(po_total)} · already billed {money(already)} · "
               f"this invoice {money(this)} (pre-tax) → {money(after)} billed in total.")
    ctx = {"po_total": po_total, "already_billed": already, "this_invoice": this,
           "after": after, "remaining_before": po_total - already}

    if after <= po_total + 0.01:
        return [_check(S, "Within PO amount", "pass", summary)], ctx
    if after <= allowed + 0.01:
        return [_check(S, "Within PO amount", "warn",
                       summary + f" Over by {money(after - po_total)}, which is within the "
                       f"{TOLERANCE_PCT:g}% tolerance.")], ctx
    over = after - po_total
    return [_check(S, "Within PO amount", "fail",
                   summary + f" Over the PO by {money(over)} ({over / po_total * 100:.1f}%), "
                   f"above the {TOLERANCE_PCT:g}% tolerance. Needs a PO amendment or credit note.",
                   effect="hold")], ctx


# ---------------------------------------------------------------- Stage 8
def duplicate_checks(f, vendor, sha256, history):
    S = "Duplicate check"
    out = []
    same_file = [r for r in history if r["sha256"] == sha256]
    if same_file:
        r = same_file[0]
        out.append(_check(S, "Not a duplicate", "fail",
                          f"This exact file was already processed (run #{r['id']}, {r['created_at'][:10]}, "
                          f"decision {r['decision']}).", effect="reject"))
        return out

    num = norm_invoice_number(f.get("invoice_number"))
    vid = vendor["vendor_id"] if vendor else None
    same_number = [r for r in history if num and r["invoice_number_norm"] == num and r["vendor_id"] == vid]
    if same_number:
        r = same_number[0]
        out.append(_check(S, "Not a duplicate", "fail",
                          f"Same vendor and invoice number as run #{r['id']} "
                          f"('{r['invoice_number']}' vs '{f.get('invoice_number')}' – both mean {num}), "
                          f"processed {r['created_at'][:10]} with decision {r['decision']}. "
                          "Do not pay twice.", effect="reject"))
        return out

    d = parse_date(f.get("invoice_date"))
    similar = [r for r in history
               if r["vendor_id"] == vid and vid and r["total"] is not None and f.get("total") is not None
               and abs(r["total"] - f["total"]) < 0.01 and d and parse_date(r["invoice_date"])
               and abs((parse_date(r["invoice_date"]) - d).days) <= DUPLICATE_WINDOW_DAYS]
    if similar:
        r = similar[0]
        out.append(_check(S, "Not a duplicate", "warn",
                          f"Different invoice number, but same vendor and same total ({money(f['total'])}) as "
                          f"run #{r['id']} dated within {DUPLICATE_WINDOW_DAYS} days. Possible duplicate.",
                          effect="hold"))
        return out

    marks = (f.get("document_marks") or "").upper()
    if any(w in marks for w in ("COPY", "RESENT", "DUPLICATE")):
        out.append(_check(S, "Not a duplicate", "warn",
                          f"Invoice is marked '{f['document_marks']}' but no original was found in our "
                          "records. It may have been paid outside this system – please confirm.",
                          effect="hold"))
        return out

    out.append(_check(S, "Not a duplicate", "pass",
                      f"No earlier invoice from this vendor with number '{f.get('invoice_number')}', "
                      "the same file, or the same amount."))
    return out


# ---------------------------------------------------------------- all together
def run_all_checks(fields, sha256, history, log=print):
    """Runs stages 4–8 in order. Returns (list_of_checks, context_dict)."""
    vendors, pos = load_reference()
    checks = []

    log("Stage 4 – sanity checks")
    checks += sanity_checks(fields)

    log("Stage 5 – vendor check")
    c, vendor = vendor_checks(fields, vendors)
    checks += c

    log("Stage 6 – PO match")
    c, po, inferred = po_checks(fields, vendor, pos)
    checks += c

    log("Stage 7 – amount check")
    c, amounts = amount_checks(fields, po)
    checks += c

    log("Stage 8 – duplicate check")
    checks += duplicate_checks(fields, vendor, sha256, history)

    context = {"vendor": vendor, "po": po, "po_inferred": inferred, "amounts": amounts,
               "invoice_number_norm": norm_invoice_number(fields.get("invoice_number"))}
    return checks, context
