# The funds database (a second Neon project, owner decision 2026-11-14).
#
# Its own declarative base, its own engine and its own Alembic history
# (backend/alembic_funds), so the two databases never see each other's
# tables. No foreign keys cross databases: links are text (ISIN first, then
# symbol), and anything that needs both databases does two reads and joins
# in Python in the service or job layer.
#
# Schema: session 4's plan (2026-11-14). Holdings tables
# (fund_holdings_monthly, fund_ratings_monthly, holding_files) come later in
# their own migration on this history.
