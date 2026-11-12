"""
The web app. Run it with:   .venv/bin/streamlit run app.py
"""
import streamlit as st

from pipeline import db
from pipeline.config import get_api_keys
from pipeline.llm import MODELS, free_requests_left
from ui import dashboard, how_it_works, live_run
from ui.components import inject_css
from ui.icons import line_icon

st.set_page_config(page_title="Invoice Processor", page_icon=":material/receipt_long:", layout="wide")
inject_css()


@st.cache_data(ttl=60, show_spinner=False)
def quota():
    return free_requests_left()


nav = st.navigation([
    st.Page(live_run.page, title="Process invoice", icon=":material/play_circle:", default=True),
    st.Page(dashboard.page, title="Dashboard", icon=":material/monitoring:", url_path="dashboard"),
    st.Page(how_it_works.page, title="How it works", icon=":material/account_tree:", url_path="how-it-works"),
])

with st.sidebar:
    st.markdown(f'<div class="brand"><div class="mark">{line_icon("logo", 18, "#fff")}</div>'
                'Invoice Processor</div>', unsafe_allow_html=True)
    st.caption("PDF invoice → AI extraction → rule checks → reasoned decision")
    st.divider()
    if not get_api_keys():
        st.error("No OpenRouter API key configured.")
    else:
        left = quota()
        st.caption(f"AI model: `{MODELS[0].split('/')[1]}` (+{len(MODELS) - 1} fallbacks)  \n"
                   f"Free AI requests left today: **{left if left is not None else '?'}**")
    st.caption("Demo order: 1 happy path → 2 split PO → 3 duplicate → 4 scanned → 5 bank change")
    with st.popover("Reset demo", width="stretch"):
        st.write("Deletes all run history so the demo can start from scratch.")
        if st.button("Yes, delete history", type="primary"):
            db.reset()
            st.session_state.pop("last_run", None)
            st.toast("History cleared")
            st.rerun()

nav.run()
