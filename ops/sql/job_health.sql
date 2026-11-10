-- Ingestion health, last 30 days (Phase 1 of the 2026-11 remediation). READ-ONLY.
--
-- Answers: has the nightly actually been green? Which passes fail or go
-- partial, and how often? (The T7 reliability week was never recorded.)
-- Output is job names, statuses, counts and timings only. No row contents.

BEGIN READ ONLY;
SET LOCAL statement_timeout = '60s';

-- 1. Nightly outcome per day.
SELECT 'nightly_by_day' AS section,
       started_at::date AS day,
       status,
       round(extract(epoch FROM (finished_at - started_at)) / 60.0) AS minutes
FROM job_runs
WHERE job_name = 'nightly_ingestion'
  AND started_at >= current_date - 30
ORDER BY started_at;

-- 2. Status mix per pass over the window.
SELECT 'pass_status_mix' AS section,
       job_name,
       count(*) AS runs,
       count(*) FILTER (WHERE status = 'success') AS success,
       count(*) FILTER (WHERE status = 'partial') AS partial,
       count(*) FILTER (WHERE status = 'failed') AS failed,
       count(*) FILTER (WHERE status = 'running') AS still_running,
       max(started_at) AS last_started
FROM job_runs
WHERE started_at >= current_date - 30
GROUP BY job_name
ORDER BY failed DESC, partial DESC, job_name;

-- 3. Latest successful run per pass (staleness check).
SELECT 'last_success' AS section,
       job_name,
       max(finished_at) AS last_success_at,
       round(extract(epoch FROM (now() - max(finished_at))) / 3600.0) AS hours_ago
FROM job_runs
WHERE status = 'success'
GROUP BY job_name
ORDER BY max(finished_at);

COMMIT;
