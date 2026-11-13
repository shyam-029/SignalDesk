-- Storage forensics (Phase 1 of the 2026-11 remediation). READ-ONLY.
--
-- Run by .github/workflows/backup.yml (storage job) on manual dispatch, and executed
-- against the CI test database by backend/tests/test_storage_forensics_sql.py
-- so a syntax error can never reach production.
--
-- Safety:
--   * The whole script runs inside BEGIN READ ONLY: Postgres itself rejects
--     any INSERT/UPDATE/DELETE/DDL, whatever the statements say.
--   * statement_timeout bounds every query; large-table column-size probes
--     use TABLESAMPLE so they read ~5% of pages, not the whole table.
--   * No CREATE EXTENSION: optional extensions are only reported, and used
--     only if already installed (dynamic SQL inside a guarded DO block).
--   * Output is sizes, counts and dates only. No row contents, no secrets.
--
-- Every result set starts with a `section` column so the log reads in order.

BEGIN READ ONLY;
SET LOCAL statement_timeout = '120s';

-- 1. Database size (what the canary and the prune gate measure).
SELECT 'db_size' AS section,
       pg_database_size(current_database()) AS bytes,
       pg_size_pretty(pg_database_size(current_database())) AS pretty,
       current_setting('server_version') AS server_version;

-- 2. Per-table storage split + MVCC churn counters + vacuum history.
--    n_dead_tup / dead_pct is the bloat hypothesis; n_tup_upd vs
--    n_tup_hot_upd shows whether the nightly rewrites are HOT (no index
--    churn) or not. Counters are cumulative since the last stats reset.
SELECT 'tables' AS section,
       s.relname AS table_name,
       round(pg_total_relation_size(c.oid) / 1e6, 1) AS total_mb,
       round(pg_relation_size(c.oid) / 1e6, 1) AS heap_mb,
       round(pg_indexes_size(c.oid) / 1e6, 1) AS index_mb,
       round(COALESCE(pg_total_relation_size(NULLIF(c.reltoastrelid, 0)), 0) / 1e6, 1) AS toast_mb,
       s.n_live_tup,
       s.n_dead_tup,
       round(100.0 * s.n_dead_tup / NULLIF(s.n_live_tup + s.n_dead_tup, 0), 1) AS dead_pct,
       s.n_tup_ins,
       s.n_tup_upd,
       s.n_tup_hot_upd,
       s.n_tup_del,
       s.last_autovacuum,
       s.last_vacuum,
       s.autovacuum_count,
       s.last_autoanalyze,
       c.reloptions
FROM pg_stat_user_tables s
JOIN pg_class c ON c.oid = s.relid
ORDER BY pg_total_relation_size(c.oid) DESC;

-- 3. Stats epoch: when the cumulative counters above started counting.
SELECT 'stats_reset' AS section, stats_reset
FROM pg_stat_database
WHERE datname = current_database();

-- 4. Every index: size, scans since stats reset, definition. Redundant
--    indexes show up as a non-unique index whose columns are a prefix of a
--    unique one on the same table.
SELECT 'indexes' AS section,
       i.relname AS table_name,
       i.indexrelname AS index_name,
       round(pg_relation_size(i.indexrelid) / 1e6, 1) AS size_mb,
       i.idx_scan,
       x.indisunique AS is_unique,
       pg_get_indexdef(i.indexrelid) AS definition
FROM pg_stat_user_indexes i
JOIN pg_index x ON x.indexrelid = i.indexrelid
ORDER BY pg_relation_size(i.indexrelid) DESC;

-- 5. Vacuum-relevant settings. neon.max_cluster_size (Neon only) is the
--    storage limit the platform actually enforces; absent elsewhere.
SELECT 'settings' AS section, name, setting, unit
FROM pg_settings
WHERE name IN (
    'autovacuum', 'track_counts', 'autovacuum_naptime',
    'autovacuum_vacuum_scale_factor', 'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_insert_scale_factor', 'autovacuum_work_mem',
    'maintenance_work_mem', 'neon.max_cluster_size'
)
ORDER BY name;

-- 6. Extensions relevant to later phases (reported, never created).
SELECT 'extensions' AS section, name, default_version, installed_version
FROM pg_available_extensions
WHERE name IN ('pgstattuple', 'pg_repack', 'neon', 'pg_stat_statements')
ORDER BY name;

-- 7. Optional exact measurements, only if the tooling already exists.
--    pg_cluster_size() is Neon's own size metric; pgstattuple_approx gives
--    real dead/free space for the two big tables.
DO $$
DECLARE
    v_bytes bigint;
    r record;
BEGIN
    -- Each probe has its own exception handler: a missing privilege on an
    -- optional tool must not abort the rest of the read-only script.
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'pg_cluster_size') THEN
            EXECUTE 'SELECT pg_cluster_size()' INTO v_bytes;
            RAISE NOTICE 'neon_cluster_size bytes=%', v_bytes;
        ELSE
            RAISE NOTICE 'neon_cluster_size unavailable (pg_cluster_size() not present)';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'neon_cluster_size failed: %', SQLERRM;
    END;

    BEGIN
        IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'pgstattuple_approx') THEN
            FOR r IN EXECUTE
                'SELECT t AS tbl, (pgstattuple_approx(t::regclass)).* '
                'FROM unnest(ARRAY[''daily_prices'', ''alpha_scores'']) AS t'
            LOOP
                RAISE NOTICE 'pgstattuple_approx % table_len=% live_pct=% dead_pct=% free_pct=%',
                    r.tbl, r.table_len, r.approx_tuple_percent,
                    r.dead_tuple_percent, r.approx_free_percent;
            END LOOP;
        ELSE
            RAISE NOTICE 'pgstattuple_approx unavailable (extension not installed)';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pgstattuple_approx failed: %', SQLERRM;
    END;
END
$$;

-- 8. daily_prices by calendar year.
SELECT 'prices_by_year' AS section,
       extract(year FROM date)::int AS year,
       count(*) AS bars,
       count(DISTINCT stock_id) AS stocks
FROM daily_prices
GROUP BY 2
ORDER BY 2;

-- 9. daily_prices by month, last 27 months (growth slope + gaps).
SELECT 'prices_by_month' AS section,
       to_char(date_trunc('month', date), 'YYYY-MM') AS month,
       count(*) AS bars,
       count(DISTINCT stock_id) AS stocks
FROM daily_prices
WHERE date >= date_trunc('month', current_date) - interval '26 months'
GROUP BY 2
ORDER BY 2;

-- 10. Who owns the bars: ranked top-1000, ETFs, or catalog stocks outside
--     the nightly universe; and how many bars sit outside the 2y fetch
--     window (never re-fetched, so never re-adjusted).
WITH top1000 AS (
    SELECT su.stock_id
    FROM stock_universe su
    JOIN universes u ON u.id = su.universe_id
    WHERE u.name = 'top1000'
)
SELECT 'prices_by_owner' AS section,
       CASE WHEN s.is_etf THEN 'etf'
            WHEN t.stock_id IS NOT NULL THEN 'top1000'
            ELSE 'other_catalog' END AS owner,
       count(DISTINCT dp.stock_id) AS stocks,
       count(*) AS bars,
       count(*) FILTER (WHERE dp.date < current_date - 730) AS bars_older_than_2y,
       min(dp.date) AS first_bar,
       max(dp.date) AS last_bar
FROM daily_prices dp
JOIN stocks s ON s.id = dp.stock_id
LEFT JOIN top1000 t ON t.stock_id = dp.stock_id
GROUP BY 2
ORDER BY 4 DESC;

-- 11. Bars-per-stock distribution (spots truncated or over-long series).
WITH per_stock AS (
    SELECT stock_id, count(*) AS n FROM daily_prices GROUP BY stock_id
)
SELECT 'bars_per_stock' AS section,
       count(*) AS stocks,
       min(n) AS min_bars,
       percentile_disc(0.10) WITHIN GROUP (ORDER BY n) AS p10,
       percentile_disc(0.50) WITHIN GROUP (ORDER BY n) AS p50,
       percentile_disc(0.90) WITHIN GROUP (ORDER BY n) AS p90,
       max(n) AS max_bars
FROM per_stock;

-- 12. alpha_scores by year, split into backfilled (technical-only) rows and
--     live snapshot rows (fundamental present; preserved by the backfill).
SELECT 'alpha_by_year' AS section,
       extract(year FROM date)::int AS year,
       count(*) AS rows_total,
       count(*) FILTER (WHERE fundamental IS NULL) AS backfill_rows,
       count(*) FILTER (WHERE fundamental IS NOT NULL) AS live_rows,
       count(DISTINCT symbol) AS symbols
FROM alpha_scores
GROUP BY 2
ORDER BY 2;

-- 13. alpha_scores integrity checks from the audit:
--     weekend-dated live rows (live snapshot keyed on the runner's UTC date)
--     and rows whose symbol no longer exists in the catalog (no FK).
SELECT 'alpha_integrity' AS section,
       count(*) FILTER (WHERE fundamental IS NOT NULL
                        AND extract(isodow FROM date) IN (6, 7)) AS weekend_live_rows,
       count(*) FILTER (WHERE NOT EXISTS (
           SELECT 1 FROM stocks s WHERE s.symbol = a.symbol)) AS orphan_symbol_rows
FROM alpha_scores a;

-- 14. Average stored widths (sampled ~5% of pages; estimates, not totals).
SELECT 'alpha_widths_sampled' AS section,
       count(*) AS sampled_rows,
       round(avg(pg_column_size(a.*))) AS avg_row_bytes,
       round(avg(pg_column_size(a.components_json))) AS avg_components_json_bytes
FROM alpha_scores a TABLESAMPLE SYSTEM (5);

SELECT 'prices_widths_sampled' AS section,
       count(*) AS sampled_rows,
       round(avg(pg_column_size(p.*))) AS avg_row_bytes
FROM daily_prices p TABLESAMPLE SYSTEM (5);

-- 15. News: size drivers and monthly growth (the suspected real grower).
SELECT 'news_totals' AS section,
       count(*) AS articles,
       count(*) FILTER (WHERE published_at IS NULL) AS no_published_at,
       round(avg(pg_column_size(content))) AS avg_content_bytes,
       round(avg(pg_column_size(title))) AS avg_title_bytes,
       min(published_at) AS oldest,
       max(published_at) AS newest
FROM news_articles;

SELECT 'news_by_month' AS section,
       to_char(date_trunc('month', published_at), 'YYYY-MM') AS month,
       count(*) AS articles
FROM news_articles
WHERE published_at >= date_trunc('month', current_date) - interval '11 months'
GROUP BY 2
ORDER BY 2;

-- 16. Churn multiplier: how many times each write-heavy pass ran per day
--     over the last 21 days (re-runs multiply the rewrite volume).
SELECT 'pass_runs_per_day' AS section,
       started_at::date AS day,
       count(*) FILTER (WHERE job_name = 'ingest_prices') AS price_runs,
       count(*) FILTER (WHERE job_name = 'backfill_alpha_history') AS alpha_backfill_runs,
       count(*) FILTER (WHERE job_name = 'nightly_ingestion' AND status = 'failed') AS failed_nights
FROM job_runs
WHERE started_at >= current_date - 21
GROUP BY 2
ORDER BY 2;

COMMIT;
