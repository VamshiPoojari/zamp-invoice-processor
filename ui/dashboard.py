"""
SCREEN 2 — Dashboard: history, status and outputs across all runs.
  KPI tiles · decision mix · top reasons invoices were stopped · reviewer queue ·
  filterable run history with drill-down into any run · CSV export.
"""
import html
from collections import Counter

import pandas as pd
import streamlit as st

from pipeline import db
from pipeline.checks import money
from pipeline.config import SAMPLES_DIR
from pipeline.decide import ISSUE_LABEL
from pipeline.run import process_invoice
from ui.components import DECISION_COLOR, DECISION_WORD, final_status, render_record, review_panel
from ui.icons import line_icon, status_icon


def load_demo_runs():
    """Process the 5 sample invoices in demo order (uses saved AI readings when available)."""
    files = sorted(SAMPLES_DIR.glob("*.pdf"))
    bar = st.progress(0.0, text="Processing sample invoices…")
    for i, f in enumerate(files, 1):
        process_invoice(f.read_bytes(), f.name)
        bar.progress(i / len(files), text=f"Processed {f.name}")


def kpi(label, value, sub, icon):
    return (f'<div class="kpi"><div class="k">{icon} {html.escape(label)}</div>'
            f'<div class="v">{value}</div><div class="s">{html.escape(sub)}</div></div>')


def page():
    st.title("Dashboard")
    st.caption("Every invoice the process has handled – decisions, money at stake, and what still needs a human.")
    runs = db.all_runs()

    if not runs:
        with st.container(border=True):
            st.markdown(f"{line_icon('inbox', 18)} **No runs yet.** Process an invoice on the "
                        "*Process invoice* page, or load the five demo scenarios in one click.",
                        unsafe_allow_html=True)
            if st.button("Load the 5 demo scenarios", type="primary"):
                load_demo_runs()
                st.rerun()
        return

    # ---------------------------------------------------------------- KPIs
    n = len(runs)
    status = [final_status(r) for r in runs]
    auto_ok = sum(r["decision"] == "APPROVE" for r in runs)
    queue = [r for r in runs if r["decision"] == "HOLD" and not r.get("review_status")]
    approved_value = sum((r["total"] or 0) for r, s in zip(runs, status) if s.startswith("Approved")
                         or s == "Auto-approved")
    stopped_value = sum((r["total"] or 0) for r, s in zip(runs, status)
                        if s in ("Needs review", "Auto-rejected", "Rejected after review"))
    high_risk = sum(bool(r["record"].get("decision", {}).get("high_risk")) for r in runs)
    times = [r["record"].get("total_seconds") for r in runs if r["record"].get("total_seconds") is not None]
    avg_t = sum(times) / len(times) if times else 0

    st.markdown('<div class="kpis">' + "".join([
        kpi("Invoices processed", n, f"avg {avg_t:.1f}s each, end-to-end", line_icon("zap")),
        kpi("Straight-through", f"{auto_ok / n:.0%}", f"{auto_ok} approved with no human touch",
            status_icon("APPROVE", 15)),
        kpi("Needs review", len(queue), "HOLDs waiting for a reviewer", status_icon("HOLD", 15)),
        kpi("Value approved", money(approved_value), "auto + after review", line_icon("dollar")),
        kpi("Value stopped", money(stopped_value), "held or rejected – not paid", status_icon("REJECT", 15)),
        kpi("High-risk flags", high_risk, "fraud-type signals caught", line_icon("shield", 16, "#d03b3b")),
    ]) + "</div>", unsafe_allow_html=True)

    # ---------------------------------------------------------------- charts
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Decision mix**")
        counts = Counter(r["decision"] for r in runs if r["decision"] in DECISION_COLOR)
        segs = "".join(
            f'<div title="{DECISION_WORD[k]}: {counts[k]} of {n}" '
            f'style="width:{counts[k] / n * 100:.2f}%;background:{DECISION_COLOR[k]}"></div>'
            for k in ("APPROVE", "HOLD", "REJECT") if counts[k])
        legend = "".join(
            f'<span>{status_icon(k, 15)} {DECISION_WORD[k]} <b>{counts[k]}</b> '
            f'<span style="color:#6b7280">({counts[k] / n:.0%})</span></span>'
            for k in ("APPROVE", "HOLD", "REJECT"))
        st.markdown(f'<div class="mix">{segs}</div><div class="legend">{legend}</div>', unsafe_allow_html=True)
    with right:
        st.markdown("**Why invoices were stopped**")
        issues = Counter()
        for r in runs:
            d = r["record"].get("decision", {})
            if d.get("decision") in ("HOLD", "REJECT"):
                fired = {c["check"] for c in r["record"].get("checks", []) if c.get("effect")}
                if "Not a duplicate" in fired:          # duplicate explains the PO overrun
                    fired.discard("Within PO amount")
                issues.update(ISSUE_LABEL.get(c, c) for c in fired)
        if issues:
            top = max(issues.values())
            st.markdown("".join(
                f'<div class="hbar" title="{html.escape(k)}: {v}"><div>{html.escape(k[0].upper() + k[1:])}</div>'
                f'<div class="track"><div class="fill" style="width:{v / top * 100:.1f}%"></div></div>'
                f'<div class="n">{v}</div></div>' for k, v in issues.most_common(6)), unsafe_allow_html=True)
        else:
            st.caption("Nothing stopped yet.")

    # ---------------------------------------------------------------- reviewer queue
    st.divider()
    st.subheader(f"Reviewer queue ({len(queue)})")
    if not queue:
        st.caption("Nothing waiting – every HOLD has been reviewed.")
    for r in queue:
        d = r["record"]["decision"]
        risk = " · HIGH RISK" if d.get("high_risk") else ""
        with st.expander(f"Run #{r['id']} · {r['vendor_name']} · {money(r['total'])} · "
                         f"{d['headline'].replace(' (HIGH RISK)', '').split(':', 1)[-1].strip()}{risk}"):
            for reason in d["reasons"]:
                st.markdown(f"- {reason}")
            for a in d["actions"]:
                st.caption(f"Next: {a['owner']} – {a['action']}")
            review_panel(r, key=f"q{r['id']}")

    # ---------------------------------------------------------------- history
    st.divider()
    st.subheader("Run history")
    table = pd.DataFrame([{
        "Run": r["id"],
        "Time": r["created_at"][5:16].replace("T", " "),
        "Status": s,
        "Vendor": r["vendor_name"] or "—",
        "Invoice #": r["invoice_number"] or "—",
        "PO": (r["po_number"] or "—") + (" (inferred)" if r["po_inferred"] else ""),
        "Total": r["total"],
        "Reason": r["record"].get("decision", {}).get("headline", ""),
        "File": r["filename"],
    } for r, s in zip(runs, status)])

    f1, f2, f3 = st.columns([2, 2, 3])
    pick_status = f1.multiselect("Status", sorted(table["Status"].unique()))
    pick_vendor = f2.multiselect("Vendor", sorted(table["Vendor"].unique()))
    search = f3.text_input("Search", placeholder="invoice number, PO, file…")
    view = table
    if pick_status:
        view = view[view["Status"].isin(pick_status)]
    if pick_vendor:
        view = view[view["Vendor"].isin(pick_vendor)]
    if search:
        mask = view.astype(str).apply(lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
        view = view[mask]

    event = st.dataframe(
        view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        column_config={"Total": st.column_config.NumberColumn(format="dollar"),
                       "Run": st.column_config.NumberColumn(width="small")},
    )
    st.download_button("Download history (CSV)", view.to_csv(index=False), "invoice_runs.csv", "text/csv")

    rows = event.selection.rows if event and event.selection else []
    if rows:
        run_id = int(view.iloc[rows[0]]["Run"])
        st.divider()
        st.subheader(f"Run #{run_id} – details")
        render_record(db.get_run(run_id), key=f"d{run_id}")
    else:
        st.caption("Select a row to see the full run: every check, extracted data, PO maths and raw output.")
