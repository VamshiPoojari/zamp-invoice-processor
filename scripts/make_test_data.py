"""
Creates all test data for the demo:
  data/vendors.csv            - the approved vendor list ("vendor master")
  data/purchase_orders.csv    - the purchase orders
  sample_invoices/*.pdf       - 5 invoice PDFs (1 happy path + 4 edge cases)

Run it with:   .venv/bin/python scripts/make_test_data.py
Safe to run again — it just overwrites the files.
"""
import csv
import io
import random
import sys
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (reads and builds PDFs)
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "sample_invoices"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

BUYER = ["Clearwater Retail Group", "Accounts Payable", "500 Market Street",
         "San Francisco, CA 94105"]

# ---------------------------------------------------------------------------
# 1. VENDOR MASTER — what the company's procurement system knows about vendors
# ---------------------------------------------------------------------------
VENDORS = [
    # id,   name,                              tax_id,       bank,          account,      status
    ["V001", "Northwind Office Supplies Inc.", "94-3318420", "Chase Bank",  "4839201748", "approved"],
    ["V002", "Brightline IT Services LLC",     "82-5502917", "Wells Fargo", "7720153390", "approved"],
    ["V003", "Summit Logistics Co.",           "47-1190385", "Bank of America", "3301847726", "approved"],
    ["V004", "Greenleaf Facilities Management","61-7724031", "Citibank",    "5527810943", "approved"],
    ["V005", "Apex Industrial Parts",          "33-9081146", "US Bank",     "1189034472", "inactive"],
]

# ---------------------------------------------------------------------------
# 2. PURCHASE ORDERS — amounts are BEFORE tax.
#    amount_invoiced = how much has already been billed against the PO.
# ---------------------------------------------------------------------------
POS = [
    # po,       vendor, description,                                   total,    invoiced, status, created
    ["PO-1001", "V001", "Office furniture: ergonomic chairs and standing desks", 4250.00, 0.00,    "open",   "2026-10-02"],
    ["PO-1002", "V003", "Freight & warehousing services, Q4 2026 (billed monthly)", 12000.00, 8000.00, "open", "2026-09-15"],
    ["PO-1003", "V002", "Cloud productivity licenses (annual) + onboarding", 6750.00, 0.00,    "open",   "2026-10-10"],
    ["PO-1004", "V004", "Janitorial & window cleaning, October 2026",      2400.00,  0.00,    "open",   "2026-09-28"],
    ["PO-1005", "V004", "HVAC repair, Building B",                         9500.00,  0.00,    "open",   "2026-10-20"],
    ["PO-1006", "V001", "Printer paper and toner, Q3 2026",                1180.00,  1180.00, "closed", "2026-07-01"],
]


def write_csvs():
    with open(DATA / "vendors.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vendor_id", "vendor_name", "tax_id", "bank_name", "bank_account", "status"])
        w.writerows(VENDORS)
    with open(DATA / "purchase_orders.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["po_number", "vendor_id", "description", "total_amount",
                    "amount_invoiced", "status", "created_date"])
        w.writerows(POS)


# ---------------------------------------------------------------------------
# 3. INVOICE PDFs — each vendor has its own look, like in real life
# ---------------------------------------------------------------------------
def money(x):
    return f"${x:,.2f}"


def draw_invoice(path, inv, style):
    """Draws one invoice PDF. `style` changes the layout so vendors look different."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    W, H = LETTER
    font, bold = ("Courier", "Courier-Bold") if style == "plain" else ("Helvetica", "Helvetica-Bold")
    accent = {"classic": colors.HexColor("#1f3a5f"), "band": colors.HexColor("#0f766e"),
              "band2": colors.HexColor("#6d28d9"), "plain": colors.black}[style]

    # --- Header ---
    if style in ("band", "band2"):
        c.setFillColor(accent)
        c.rect(0, H - 95, W, 95, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(bold, 20); c.drawString(40, H - 45, inv["vendor"])
        c.setFont(font, 9)
        c.drawString(40, H - 62, inv["vendor_addr"])
        c.drawString(40, H - 75, f"Tax ID (EIN): {inv['tax_id']}  |  {inv['vendor_email']}")
        c.setFont(bold, 26); c.drawRightString(W - 40, H - 50, "INVOICE")
        c.setFillColor(colors.black)
        y = H - 130
    else:
        c.setFillColor(accent)
        c.setFont(bold, 18); c.drawString(40, H - 55, inv["vendor"])
        c.setFillColor(colors.black)
        c.setFont(font, 9)
        c.drawString(40, H - 70, inv["vendor_addr"])
        c.drawString(40, H - 82, f"EIN {inv['tax_id']}   {inv['vendor_email']}")
        c.setFont(bold, 22); c.drawRightString(W - 40, H - 55, inv.get("title", "INVOICE"))
        c.setStrokeColor(accent); c.setLineWidth(1.5); c.line(40, H - 95, W - 40, H - 95)
        y = H - 125

    # --- Bill to (left) and invoice details (right) ---
    c.setFont(bold, 10); c.drawString(40, y, "BILL TO")
    c.setFont(font, 10)
    for i, line in enumerate(BUYER):
        c.drawString(40, y - 14 * (i + 1), line)

    details = [(inv["label_no"], inv["invoice_no"]), ("Invoice Date", inv["date"]),
               ("Due Date", inv["due"])]
    if inv.get("po"):
        details.append(("PO Number", inv["po"]))
    for i, (k, v) in enumerate(details):
        c.setFont(bold, 10); c.drawString(W - 260, y - 14 * i, k + ":")
        c.setFont(font, 10); c.drawRightString(W - 40, y - 14 * i, v)

    # --- Line items table ---
    y -= 95
    c.setFillColor(colors.HexColor("#eeeeee") if style != "plain" else colors.white)
    c.rect(40, y - 4, W - 80, 18, fill=1, stroke=0)
    c.setFillColor(colors.black); c.setFont(bold, 10)
    c.drawString(46, y, "Description"); c.drawRightString(370, y, "Qty")
    c.drawRightString(470, y, "Unit Price"); c.drawRightString(W - 46, y, "Amount")
    c.setFont(font, 10)
    subtotal = 0
    for desc, qty, unit in inv["items"]:
        y -= 20
        amt = round(qty * unit, 2); subtotal += amt
        c.drawString(46, y, desc); c.drawRightString(370, y, f"{qty:g}")
        c.drawRightString(470, y, money(unit)); c.drawRightString(W - 46, y, money(amt))
    subtotal = round(subtotal, 2)
    tax = round(subtotal * inv["tax_rate"], 2)
    total = round(subtotal + tax, 2)

    # --- Totals ---
    y -= 15; c.setLineWidth(0.5); c.setStrokeColor(colors.grey); c.line(330, y, W - 40, y)
    rows = [("Subtotal", money(subtotal))]
    if inv["tax_rate"]:
        rows.append((f"Sales Tax ({inv['tax_rate'] * 100:.3f}%)", money(tax)))
    else:
        rows.append(("Sales Tax", "Exempt (services)"))
    rows.append(("TOTAL DUE", money(total)))
    for k, v in rows:
        y -= 18
        c.setFont(bold if k == "TOTAL DUE" else font, 11 if k == "TOTAL DUE" else 10)
        c.drawString(340, y, k); c.drawRightString(W - 46, y, v)

    # --- Payment details + notes ---
    y -= 50
    c.setFont(bold, 10); c.drawString(40, y, "PAYMENT DETAILS")
    c.setFont(font, 10)
    c.drawString(40, y - 15, f"Bank: {inv['bank']}")
    c.drawString(40, y - 29, f"Account No: {inv['account']}    Routing: {inv['routing']}")
    c.drawString(40, y - 43, f"Terms: {inv['terms']}")
    for i, note in enumerate(inv.get("notes", [])):
        c.drawString(40, y - 70 - 14 * i, note)

    # --- Optional red stamp (e.g. "RESENT") ---
    if inv.get("stamp"):
        c.saveState()
        c.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.55))
        c.setFont("Helvetica-Bold", 30)
        c.translate(W - 190, H - 300); c.rotate(18)
        c.drawCentredString(0, 0, inv["stamp"])
        c.restoreState()

    c.setFont(font, 8); c.setFillColor(colors.grey)
    c.drawCentredString(W / 2, 30, "Thank you for your business.")
    c.save()
    return subtotal, tax, total


def make_scanned(src_pdf, dst_pdf):
    """Turns a normal PDF into a 'scanned' one: image only, no selectable text,
    slightly tilted, greyish, a bit blurry — like a phone/office scanner."""
    random.seed(7)
    page = fitz.open(src_pdf)[0]
    pix = page.get_pixmap(dpi=150)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")       # greyscale
    img = img.rotate(-1.2, expand=True, fillcolor=235)                  # slight tilt
    img = img.filter(ImageFilter.GaussianBlur(0.6))                     # slight blur
    px = img.load()                                                     # speckle noise
    for _ in range(25000):
        x, y = random.randrange(img.width), random.randrange(img.height)
        px[x, y] = max(0, px[x, y] - random.randint(40, 120))
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70)
    doc = fitz.open()
    p = doc.new_page(width=img.width * 72 / 150, height=img.height * 72 / 150)
    p.insert_image(p.rect, stream=buf.getvalue())
    doc.save(dst_pdf)
    Path(src_pdf).unlink()  # delete the clean version — only the scan should exist


NORTHWIND = dict(vendor="Northwind Office Supplies Inc.", vendor_addr="1450 Harbor Blvd, Oakland, CA 94607",
                 tax_id="94-3318420", vendor_email="billing@northwind-office.example",
                 bank="Chase Bank", account="4839201748", routing="021000021", terms="Net 30")

INVOICES = [
    # 1. HAPPY PATH — clean, approved vendor, PO given, amounts match exactly
    ("1_happy_path_northwind.pdf", "classic", dict(
        **NORTHWIND, label_no="Invoice No", invoice_no="INV-0042",
        date="2026-10-28", due="2026-11-27", po="PO-1001",
        items=[("Ergonomic office chair (model EC-200)", 10, 285.00),
               ("Standing desk, 60in electric", 4, 350.00)],
        tax_rate=0.08625)),

    # 2. EDGE: SPLIT PO, OVERBILLED — PO-1002 is $12,000, $8,000 already billed.
    #    This invoice is $4,800 → total billed would be $12,800 (over the PO).
    ("2_edge_split_po_overbilled_summit.pdf", "band", dict(
        vendor="Summit Logistics Co.", vendor_addr="88 Terminal Way, Long Beach, CA 90802",
        tax_id="47-1190385", vendor_email="ar@summitlogistics.example",
        bank="Bank of America", account="3301847726", routing="026009593", terms="Net 15",
        label_no="Invoice #", invoice_no="SL-2264", date="2026-11-03", due="2026-11-18",
        po="PO-1002",
        items=[("Freight services - November 2026", 1, 4000.00),
               ("Fuel surcharge", 1, 450.00),
               ("Expedited delivery fee", 1, 350.00)],
        tax_rate=0.0, notes=["Invoice 3 of 3 against PO-1002."])),

    # 3. EDGE: DISGUISED DUPLICATE — same invoice as #1, resent with a different
    #    number format ("42" vs "INV-0042"), different date format, a stamp.
    #    Different file → different fingerprint, so a simple file check misses it.
    ("3_edge_duplicate_northwind.pdf", "classic", dict(
        **NORTHWIND, title="INVOICE - COPY", label_no="Invoice #", invoice_no="42",
        date="Oct 28, 2026", due="Nov 27, 2026", po="PO-1001",
        items=[("Ergonomic office chair (model EC-200)", 10, 285.00),
               ("Standing desk, 60in electric", 4, 350.00)],
        tax_rate=0.08625, stamp="RESENT",
        notes=["Second notice - our records show this invoice as unpaid."])),

    # 4. EDGE: SCANNED, NO PO NUMBER — image-only PDF; the PO must be inferred.
    #    Greenleaf has two open POs (PO-1004 $2,400 and PO-1005 $9,500).
    ("4_edge_scanned_no_po_greenleaf.pdf", "plain", dict(
        vendor="Greenleaf Facilities Management", vendor_addr="310 Elm Street, San Jose, CA 95112",
        tax_id="61-7724031", vendor_email="invoices@greenleaf-fm.example",
        bank="Citibank", account="5527810943", routing="321171184", terms="Net 30",
        label_no="Invoice No", invoice_no="GF-3310", date="10/31/2026", due="11/30/2026",
        po=None,
        items=[("Janitorial services - October 2026", 1, 2200.00),
               ("Window cleaning (quarterly)", 1, 200.00)],
        tax_rate=0.0)),

    # 5. EDGE: BANK ACCOUNT CHANGED — everything matches PO-1003 perfectly,
    #    but the bank details differ from the vendor master. Classic fraud pattern.
    ("5_edge_bank_changed_brightline.pdf", "band2", dict(
        vendor="Brightline IT Services LLC", vendor_addr="2201 Mission College Blvd, Santa Clara, CA 95054",
        tax_id="82-5502917", vendor_email="accounts@brightline-it.example",
        bank="First Horizon Bank", account="9184402267", routing="084000026", terms="Net 30",
        label_no="Invoice Number", invoice_no="BIT-5521", date="2026-11-05", due="2026-12-05",
        po="PO-1003",
        items=[("Cloud productivity suite licenses (annual)", 25, 198.00),
               ("Onboarding & setup", 1, 1800.00)],
        tax_rate=0.08625,
        notes=["IMPORTANT: We have changed banks. Please update your records",
               "and send all future payments to the account above."])),
]


def main():
    write_csvs()
    print("Created data/vendors.csv and data/purchase_orders.csv")
    for filename, style, inv in INVOICES:
        path = OUT / filename
        if "scanned" in filename:
            tmp = OUT / ("_clean_" + filename)
            sub, tax, tot = draw_invoice(tmp, inv, style)
            make_scanned(tmp, path)
        else:
            sub, tax, tot = draw_invoice(path, inv, style)
        print(f"Created {filename:42s} subtotal {money(sub):>11s}  tax {money(tax):>9s}  total {money(tot):>11s}")


if __name__ == "__main__":
    sys.exit(main())
