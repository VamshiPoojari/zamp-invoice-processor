"""
STAGE 9: Decide.

The rule is simple and strict:
    any check says REJECT  → REJECT
    else any check says HOLD → HOLD FOR REVIEW
    else                     → APPROVE
(Reject beats Hold beats Approve.)

Besides the decision, we produce:
  - reasons:   every check that caused it, in plain English
  - actions:   who needs to do what next (so a HOLD never just sits there)
  - headline:  one sentence an AP manager can read in 3 seconds
The decision is made by code, not AI, so it is consistent and auditable.
"""
from pipeline.checks import money

# Which team handles each kind of problem, and what they should do.
NEXT_STEP = {
    "Bank account matches vendor record":
        ("Treasury", "Call the vendor on the phone number in our vendor master (not the one on the "
                     "invoice) to confirm the bank change. Do not pay until confirmed."),
    "Vendor name matches tax ID": ("Vendor management", "Confirm the vendor's identity before paying."),
    "Vendor tax ID matches record": ("Vendor management", "Confirm the vendor's tax ID before paying."),
    "Vendor is approved": ("Procurement", "Send the vendor through onboarding. Return invoice to vendor."),
    "Within PO amount":
        ("Procurement", "Ask the PO owner to amend the PO, or ask the vendor for a credit note for the excess."),
    "PO reference": ("AP reviewer", "Confirm the suggested PO with the requester, then approve."),
    "PO exists": ("AP reviewer", "Ask the vendor or requester for the correct PO number."),
    "PO is open": ("Procurement", "Check why an invoice arrived for a closed PO."),
    "PO belongs to this vendor": ("AP reviewer", "PO and vendor don't match – return invoice to vendor."),
    "Not a duplicate": ("AP reviewer", "Tell the vendor this invoice was already received. No payment."),
    "Critical fields present": ("AP reviewer", "Ask the vendor for a corrected invoice."),
    "Line items add up to subtotal": ("AP reviewer", "Ask the vendor for a corrected invoice."),
    "Subtotal + tax = total": ("AP reviewer", "Ask the vendor for a corrected invoice."),
    "Invoice date sensible": ("AP reviewer", "Check the invoice date with the vendor."),
    "Document readable": ("AP reviewer", "Check the extracted figures against the PDF by eye."),
    "Automatic processing": ("AP reviewer", "Process this invoice manually."),
}


# Short labels for headlines ("Hold for review: bank account changed").
ISSUE_LABEL = {
    "Bank account matches vendor record": "bank account changed",
    "Vendor name matches tax ID": "vendor identity mismatch",
    "Vendor tax ID matches record": "tax ID mismatch",
    "Vendor is approved": "vendor not approved",
    "Within PO amount": "over PO amount",
    "PO reference": "PO inferred – needs confirmation",
    "PO exists": "PO not found",
    "PO is open": "PO is closed",
    "PO belongs to this vendor": "PO belongs to another vendor",
    "Not a duplicate": "duplicate invoice",
    "Critical fields present": "missing information",
    "Line items add up to subtotal": "line items don't add up",
    "Subtotal + tax = total": "totals don't add up",
    "Invoice date sensible": "suspicious date",
    "Document readable": "hard to read",
    "Automatic processing": "could not be processed automatically",
}


def decide(checks, fields, context):
    rejects = [c for c in checks if c["effect"] == "reject"]
    holds = [c for c in checks if c["effect"] == "hold"]

    # A confirmed duplicate is rejected no matter what. Any other issue (e.g. the PO now
    # looks over-billed) belongs to the ORIGINAL invoice, so it becomes a side note –
    # nobody gets sent on a wild goose chase.
    side_effects = []
    if any(c["check"] == "Not a duplicate" and c["effect"] == "reject" for c in rejects):
        side_effects = holds
        holds = []
    passed = sum(c["status"] == "pass" for c in checks)
    high_risk = any(c["high_risk"] and c["status"] != "pass" for c in checks)

    if rejects:
        decision = "REJECT"
    elif holds:
        decision = "HOLD"
    else:
        decision = "APPROVE"

    vendor = (context.get("vendor") or {}).get("vendor_name") or fields.get("vendor_name") or "unknown vendor"
    po = (context.get("po") or {}).get("po_number")
    total = money(fields.get("total"))

    if decision == "APPROVE":
        headline = f"Approve {total} to {vendor}" + (f" against {po}" if po else "") + \
                   f". All {passed} checks passed."
        reasons = [f"All {passed} checks passed."]
        notes = [c["message"] for c in checks if c["status"] == "warn"]  # e.g. within tolerance
        actions = [{"owner": "AP", "action": f"Schedule payment of {total} by the due date "
                                            f"({fields.get('due_date') or 'not stated'})."}]
    else:
        problems = rejects + holds
        labels = [ISSUE_LABEL.get(c["check"], c["check"].lower()) for c in problems]
        word = "Reject" if decision == "REJECT" else "Hold for review"
        headline = f"{word}: {', '.join(dict.fromkeys(labels))}" + (" (HIGH RISK)" if high_risk else "")
        reasons = [c["message"] for c in problems]
        notes = [f"Also noticed (belongs to the original invoice – no separate action): {c['message']}"
                 for c in side_effects]
        actions, seen = [], set()
        for c in problems:
            owner, action = NEXT_STEP.get(c["check"], ("AP reviewer", "Review manually."))
            if action not in seen:
                seen.add(action)
                actions.append({"owner": owner, "action": action})

    return {"decision": decision, "headline": headline, "reasons": reasons, "notes": notes,
            "actions": actions, "high_risk": high_risk,
            "counts": {"passed": passed, "warnings": sum(c["status"] == "warn" for c in checks),
                       "failed": sum(c["status"] == "fail" for c in checks)}}
