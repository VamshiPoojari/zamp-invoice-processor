"""
Settings for the whole app, in one place.
If you want to change a rule (like the 2% tolerance), change it here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Folder paths
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SAMPLES_DIR = ROOT / "sample_invoices"
DB_PATH = ROOT / "runs.db"

# Load secret keys from the .env file (on your computer)
load_dotenv(ROOT / ".env")


def get_api_keys():
    """Return all OpenRouter keys found (OPENROUTER_API_KEY1, 2, 3...).
    Works locally (.env) and online (Streamlit Cloud secrets)."""
    keys = [
        value
        for name, value in sorted(os.environ.items())
        if name.startswith("OPENROUTER_API_KEY") and value.strip()
    ]
    if not keys:
        try:  # when the app runs on Streamlit Cloud
            import streamlit as st

            keys = [v for k, v in sorted(st.secrets.items())
                    if k.startswith("OPENROUTER_API_KEY") and v]
        except Exception:
            pass
    return keys


# Business rules (from PROCESS_MAP.md)
CURRENCY = "USD"
TOLERANCE_PCT = 2.0            # invoice may exceed PO remaining by up to 2%
DUPLICATE_WINDOW_DAYS = 7      # same vendor + same total within 7 days = possible duplicate
