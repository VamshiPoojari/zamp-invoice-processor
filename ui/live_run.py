"""
SCREEN 1 — Process an invoice (live run view).
Pick a sample or upload a PDF → press Run → watch each stage light up → see the decision.
"""
import time

import streamlit as st

from pipeline import db
from pipeline.config import SAMPLES_DIR
from pipeline.run import STAGES, process_invoice
from ui.components import pdf_preview, render_record, stage_html

SAMPLES = {
    "1_happy_path_northwind.pdf": ("Happy path – Northwind Office Supplies",
                                   "Clean invoice, PO given, amounts match. Expected: APPROVE."),
    "2_edge_split_po_overbilled_summit.pdf": ("Edge 1 – Split PO, overbilled (Summit Logistics)",
                                              "3rd invoice on a PO that's already ⅔ billed. Expected: HOLD."),
    "3_edge_duplicate_northwind.pdf": ("Edge 2 – Disguised duplicate (Northwind)",
                                       "Same invoice as the happy path, number written '42'. "
                                       "Run the happy path first. Expected: REJECT."),
    "4_edge_scanned_no_po_greenleaf.pdf": ("Edge 3 – Scanned, no PO number (Greenleaf)",
                                           "Image-only PDF, PO must be inferred. Expected: HOLD."),
    "5_edge_bank_changed_brightline.pdf": ("Edge 4 – Bank account changed (Brightline IT)",
                                           "Perfect invoice, new bank details. Expected: HOLD, high risk."),
}

PAUSE = 0.35  # short pause between stages so viewers can follow; real timings are shown on each row


def page():
    st.title("Process an invoice")
    st.caption("AI reads the invoice · rules check it against vendors, POs and history · "
               "you get a decision with reasons and next steps.")

    # ---------------------------------------------------------------- input
    pdf_bytes, filename = None, None
    with st.container(border=True):
        src = st.segmented_control("Invoice source", ["Sample invoice", "Upload a PDF"],
                                   default="Sample invoice", label_visibility="collapsed")
        if src == "Upload a PDF":
            up = st.file_uploader("Invoice PDF", type=["pdf"])
            if up:
                pdf_bytes, filename = up.getvalue(), up.name
        else:
            choice = st.selectbox("Sample invoice", list(SAMPLES), format_func=lambda f: SAMPLES[f][0])
            st.caption(SAMPLES[choice][1])
            pdf_bytes, filename = (SAMPLES_DIR / choice).read_bytes(), choice

        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        use_cache = c2.toggle("Reuse saved AI reading", value=True,
                              help="If this exact file was read before, reuse that result instead of "
                                   "calling the AI again. Saves the free daily quota. Turn off to "
                                   "watch a fresh AI extraction.")
        run = c1.button("Run process", type="primary", disabled=pdf_bytes is None, width="stretch")

    if pdf_bytes is None:
        st.info("Upload a PDF invoice to begin.")
        return

    # ---------------------------------------------------------------- live view
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown("**Invoice**")
        img = pdf_preview(pdf_bytes)
        if img:
            st.image(img, width="stretch")
        else:
            st.warning("Can't preview this file – it may not be a valid PDF.")

    with right:
        st.markdown("**Live run**")
        progress = st.progress(0.0)
        rows = {key: st.empty() for key, _, _ in STAGES}
        log_box = st.empty()

    names = {key: (name, desc) for key, name, desc in STAGES}
    last = st.session_state.get("last_run")

    def draw(key, status, summary="", secs=None):
        name, desc = names[key]
        rows[key].markdown(stage_html(name, desc, status, summary, secs), unsafe_allow_html=True)

    if run:
        for key in rows:
            draw(key, "pending")
        logs, done = [], []

        def on_log(msg):
            logs.append(msg)
            log_box.caption("  \n".join(logs[-4:]))

        def on_event(key, status, summary, secs):
            if key not in rows:
                return
            draw(key, status, summary, secs)
            if status != "running":
                done.append(key)
                progress.progress(len(done) / len(STAGES))
                time.sleep(PAUSE)

        try:
            result = process_invoice(pdf_bytes, filename, use_cache=use_cache,
                                     on_event=on_event, on_log=on_log)
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            return
        for key in rows:  # stages that never ran (e.g. after an error)
            if key not in done:
                draw(key, "skipped", "Skipped")
        progress.progress(1.0)
        st.session_state["last_run"] = {"run_id": result["run_id"], "filename": filename}
        last = st.session_state["last_run"]
        st.cache_data.clear()  # refresh quota counter in the sidebar

    elif last and last["filename"] == filename and db.get_run(last["run_id"]):
        # Page was refreshed (e.g. you clicked a tab) – redraw the finished run.
        timeline = {t["stage"]: t for t in db.get_run(last["run_id"])["record"]["timeline"]}
        for key in rows:
            t = timeline.get(key)
            draw(key, t["status"], t["summary"], t["seconds"]) if t else draw(key, "skipped", "Skipped")
        progress.progress(1.0)
    else:
        for key in rows:
            draw(key, "pending")
        last = None

    # ---------------------------------------------------------------- result
    if last and last["filename"] == filename:
        run_row = db.get_run(last["run_id"])
        if run_row:
            st.divider()
            render_record(run_row, key=f"live{run_row['id']}")
