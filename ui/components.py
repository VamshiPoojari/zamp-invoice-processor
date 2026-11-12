"""
Reusable pieces of the UI: stage tracker rows, decision card, human review panel,
and the full result view (used by both the live run page and the dashboard).
"""
import html
from datetime import datetime

import pandas as pd
import pymupdf
import streamlit as st

from pipeline import db
from pipeline.checks import money
from ui.icons import CRITICAL, GOOD, WARNING, line_icon, status_icon

DECISION_WORD = {"APPROVE": "Approve", "HOLD": "Hold for review", "REJECT": "Reject", "PENDING": "Pending"}
DECISION_COLOR = {"APPROVE": GOOD, "HOLD": WARNING, "REJECT": CRITICAL}

CSS = """
<style>
@keyframes spin{to{transform:rotate(360deg)}}
.spin{animation:spin .9s linear infinite;transform-origin:50% 50%}
.stage{display:flex;gap:12px;align-items:flex-start;padding:9px 14px;margin-bottom:6px;
  border:1px solid #e6e8ef;border-left:4px solid #cbd2e1;border-radius:8px;background:#fff;transition:all .2s}
.stage .icon{width:22px;padding-top:1px}
.stage .body{flex:1;min-width:0}
.stage .name{font-weight:600;font-size:14.5px}
.stage .desc{color:#6b7280;font-size:12.5px;margin-left:6px}
.stage .sum{font-size:13px;color:#374151;margin-top:2px;overflow-wrap:anywhere}
.stage .secs{color:#9ca3af;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.stage-pending,.stage-skipped{opacity:.5}
.stage-running{border-left-color:#2f5bea;background:#f3f6ff}
.stage-pass{border-left-color:#0ca30c}
.stage-warn{border-left-color:#fab219;background:#fffbeb}
.stage-fail{border-left-color:#d03b3b;background:#fef2f2}
.decision{padding:18px 22px;border-radius:12px;margin:6px 0 14px;display:flex;gap:16px;align-items:flex-start}
.decision-APPROVE{background:#ecfdf3;border:1px solid #86efac}
.decision-HOLD{background:#fffbeb;border:1px solid #fcd34d}
.decision-REJECT{background:#fef2f2;border:1px solid #fca5a5}
.dlabel{font-size:12.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:#374151}
.dhead{font-size:20px;font-weight:600;margin-top:2px;color:#111827}
.dmeta{font-size:13px;color:#6b7280;margin-top:6px}
.risk{display:inline-flex;gap:4px;align-items:center;background:#d03b3b;color:#fff;font-size:11px;
  font-weight:700;padding:2px 9px;border-radius:999px;margin-left:8px;vertical-align:middle;letter-spacing:.04em}
.chk{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid #f0f1f5;font-size:14px}
.chk .msg{color:#4b5563;font-size:13px}
.stagehdr{font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin:14px 0 2px}
.action{display:flex;gap:10px;padding:9px 12px;border-radius:8px;background:#f5f7fb;margin-bottom:6px;font-size:14px}
.owner{font-weight:700;color:#2f5bea;white-space:nowrap}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;padding:3px 10px;
  border-radius:999px;background:#f3f4f6;color:#374151}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:6px 0 18px}
.kpi{border:1px solid #e6e8ef;border-radius:12px;padding:14px 16px;background:#fff}
.kpi .k{font-size:12.5px;color:#6b7280;display:flex;gap:6px;align-items:center}
.kpi .v{font-size:26px;font-weight:700;color:#111827;margin-top:4px;font-variant-numeric:tabular-nums}
.kpi .s{font-size:12px;color:#6b7280;margin-top:2px}
.mix{display:flex;gap:2px;height:28px;border-radius:6px;overflow:hidden;margin:8px 0}
.mix div{height:100%}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:#374151}
.legend span{display:inline-flex;gap:6px;align-items:center}
.hbar{display:grid;grid-template-columns:200px 1fr 36px;gap:10px;align-items:center;font-size:13px;margin:6px 0}
.hbar .track{height:14px;background:#f1f3f8;border-radius:0 4px 4px 0}
.hbar .fill{height:100%;background:#2a78d6;border-radius:0 4px 4px 0}
.hbar .n{text-align:right;font-variant-numeric:tabular-nums;color:#111827;font-weight:600}
.brand{display:flex;gap:10px;align-items:center;font-weight:700;font-size:17px;color:#111827}
.brand .mark{width:32px;height:32px;border-radius:8px;background:#2f5bea;color:#fff;display:flex;
  align-items:center;justify-content:center}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def stage_html(name, desc, status, summary="", secs=None):
    t = "" if secs is None or status in ("pending", "running") else f"{secs:.2f}s"
    if status == "running":
        summary = summary or "Working…"
    return (f'<div class="stage stage-{status}"><div class="icon">{status_icon(status)}</div>'
            f'<div class="body"><span class="name">{html.escape(name)}</span>'
            f'<span class="desc">{html.escape(desc)}</span>'
            f'<div class="sum">{html.escape(summary)}</div></div>'
            f'<div class="secs">{t}</div></div>')


@st.cache_data(show_spinner=False)
def pdf_preview(pdf_bytes, dpi=80):
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        return doc[0].get_pixmap(dpi=dpi).tobytes("png")
    except Exception:
        return None


def final_status(run):
    """Where the invoice ends up after any human review."""
    if run["decision"] == "HOLD":
        return {"APPROVED": "Approved after review", "REJECTED": "Rejected after review"}.get(
            run.get("review_status"), "Needs review")
    return {"APPROVE": "Auto-approved", "REJECT": "Auto-rejected"}.get(run["decision"], run["decision"])


def decision_card(run):
    d = run["record"]["decision"]
    risk = (f'<span class="risk">{line_icon("shield", 12, "#fff")} HIGH RISK</span>'
            if d.get("high_risk") else "")
    c = d["counts"]
    meta = (f"Run #{run['id']} · {c['passed']} passed · {c['warnings']} warning(s) · "
            f"{c['failed']} failed · {run['record'].get('total_seconds', '?')}s end-to-end")
    head = d["headline"].replace(" (HIGH RISK)", "")
    if d["decision"] != "APPROVE" and ":" in head:
        head = head.split(":", 1)[1].strip()
        head = head[0].upper() + head[1:]
    st.markdown(f'<div class="decision decision-{d["decision"]}"><div>{status_icon(d["decision"], 34)}</div>'
                f'<div><div class="dlabel">{DECISION_WORD[d["decision"]]}{risk}</div>'
                f'<div class="dhead">{html.escape(head)}</div>'
                f'<div class="dmeta">{meta}</div></div></div>', unsafe_allow_html=True)


def review_panel(run, key):
    """Human-in-the-loop: a reviewer approves or rejects an invoice on HOLD."""
    if run["decision"] != "HOLD":
        return
    if run.get("review_status"):
        st.markdown(f'<span class="pill">{status_icon("APPROVE" if run["review_status"] == "APPROVED" else "REJECT", 16)}'
                    f' {final_status(run)} · {html.escape(run.get("review_note") or "no note")} · '
                    f'{(run.get("reviewed_at") or "")[:16].replace("T", " ")}</span>', unsafe_allow_html=True)
        return
    with st.container(border=True):
        st.markdown(f"**{line_icon('user')} Reviewer decision** – the process never pays a HOLD on its own.",
                    unsafe_allow_html=True)
        note = st.text_input("Note (what you checked)", key=f"note_{key}",
                             placeholder="e.g. Called vendor on number in vendor master – change confirmed")
        a, b = st.columns(2)
        if a.button("Approve for payment", key=f"ok_{key}", type="primary", width="stretch"):
            db.update_run(run["id"], review_status="APPROVED", review_note=note or None,
                          reviewed_at=datetime.now().isoformat(timespec="seconds"))
            st.rerun()
        if b.button("Reject invoice", key=f"no_{key}", width="stretch"):
            db.update_run(run["id"], review_status="REJECTED", review_note=note or None,
                          reviewed_at=datetime.now().isoformat(timespec="seconds"))
            st.rerun()


def render_record(run, key="live"):
    """Full result view for one run."""
    rec = run["record"]
    d = rec["decision"]
    decision_card(run)

    a, b = st.columns(2, gap="large")
    with a:
        st.markdown("**Why**")
        for r in d["reasons"]:
            st.markdown(f"- {r}")
        for n in d.get("notes", []):
            st.caption(n)
    with b:
        st.markdown("**What happens next**")
        for act in d["actions"]:
            st.markdown(f'<div class="action"><span class="owner">{line_icon("user", 14, "#2f5bea")} '
                        f'{html.escape(act["owner"])}</span><span>{html.escape(act["action"])}</span></div>',
                        unsafe_allow_html=True)
        review_panel(run, key)

    checks = rec.get("checks", [])
    tabs = st.tabs([f"Checks ({len(checks)})", "Extracted data", "PO & amounts", "Raw data"])

    with tabs[0]:
        current = None
        for c in checks:
            if c["stage"] != current:
                current = c["stage"]
                st.markdown(f'<div class="stagehdr">{html.escape(current)}</div>', unsafe_allow_html=True)
            flag = (f'<span class="risk">{line_icon("shield", 12, "#fff")} HIGH RISK</span>'
                    if c["high_risk"] and c["status"] != "pass" else "")
            effect = f" → <b>{c['effect'].upper()}</b>" if c["effect"] else ""
            st.markdown(f'<div class="chk"><div>{status_icon(c["status"], 18)}</div><div>'
                        f'<b>{html.escape(c["check"])}</b>{effect}{flag}'
                        f'<div class="msg">{html.escape(c["message"])}</div></div></div>',
                        unsafe_allow_html=True)

    with tabs[1]:
        f = rec.get("fields", {})
        info = rec.get("info", {})
        if info:
            how = "saved result (no AI request)" if info.get("cached") else info.get("model")
            st.caption(f"Read as **{info.get('method')}** · extracted by {how}")
        rows = [(k.replace("_", " ").capitalize(), "—" if v is None else str(v))
                for k, v in f.items() if k != "line_items"]
        st.dataframe(pd.DataFrame(rows, columns=["Field", "Value"]), hide_index=True, width="stretch")
        if f.get("line_items"):
            st.markdown("**Line items**")
            st.dataframe(pd.DataFrame(f["line_items"]), hide_index=True, width="stretch")

    with tabs[2]:
        amt = rec.get("amounts")
        if not amt:
            st.info("No purchase order was matched, so no amount comparison was possible.")
        else:
            st.markdown(f"**{run['po_number']}**" + (" · *inferred – not printed on invoice*"
                                                    if run.get("po_inferred") else ""))
            m = st.columns(4)
            m[0].metric("PO total (pre-tax)", money(amt["po_total"]))
            m[1].metric("Already billed", money(amt["already_billed"]))
            m[2].metric("This invoice (pre-tax)", money(amt["this_invoice"]))
            over = amt["after"] - amt["po_total"]
            m[3].metric("Billed after this", money(amt["after"]),
                        delta=f"{money(over)} over PO" if over > 0.01 else None, delta_color="inverse")
            st.progress(min(amt["after"] / amt["po_total"], 1.0) if amt["po_total"] else 0.0,
                        text=f"{amt['after'] / amt['po_total'] * 100:.0f}% of PO used after this invoice")
        cands = rec.get("po_candidates")
        if cands:
            st.markdown("**PO candidates considered** (60% amount fit + 40% description fit)")
            st.dataframe(pd.DataFrame(cands).rename(columns={
                "po_number": "PO", "description": "Description", "remaining": "Remaining", "score": "Match %"}),
                hide_index=True, width="stretch")

    with tabs[3]:
        st.json(rec, expanded=False)
