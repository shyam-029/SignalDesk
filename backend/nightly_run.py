"""Detached full nightly ingestion run (fills 736 unpriced top-1000 stocks and
re-applies Alpha v1.5 to the stored history via backfill_alpha_history)."""
from app.logging_utils import configure_logging

configure_logging()

from app.jobs import run_daily_ingestion

run_daily_ingestion()
