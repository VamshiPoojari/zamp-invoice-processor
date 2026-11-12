"""SCREEN 3 — How it works: visual pipeline + the full process map."""
import html

import streamlit as st

from pipeline.config import ROOT
from pipeline.run import STAGES

KIND = {"extract": ("AI", "#6250d6", "#f1efff"), "read": ("Code", "#2a78d6", "#eef5ff")}


def page():
    st.title("How it works")
    st.markdown("**AI reads the invoice. Rules make the decision.** The model only extracts fields – "
                "every check and the final decision are deterministic code, so each outcome is repeatable "
                "and explainable.")
    chips = []
    for i, (key, name, desc) in enumerate(STAGES, 1):
        kind, fg, bg = KIND.get(key, ("Rules", "#0b7a3e", "#ecfdf3"))
        if key in ("intake", "record"):
            kind, fg, bg = "System", "#52514e", "#f3f4f6"
        chips.append(
            f'<div style="border:1px solid #e6e8ef;border-radius:10px;padding:10px 12px;background:#fff">'
            f'<div style="font-size:11px;color:#6b7280">STAGE {i}</div>'
            f'<div style="font-weight:600;font-size:14px">{html.escape(name)}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin:2px 0 6px">{html.escape(desc)}</div>'
            f'<span style="font-size:11px;font-weight:700;color:{fg};background:{bg};padding:2px 8px;'
            f'border-radius:999px">{kind}</span></div>')
    st.markdown('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));'
                f'gap:10px;margin:12px 0 24px">{"".join(chips)}</div>', unsafe_allow_html=True)
    st.divider()
    st.markdown((ROOT / "PROCESS_MAP.md").read_text())
