-- Part 1: what the AusTender data can and can't tell us.
-- Each query starts with `-- name: <id>`; scripts/profile_releases.py runs them in order.
-- Thresholds: notices must be published for contracts of $10,000 or more (CPRs 7.18), and
-- non-corporate entities must approach the market openly from $80,000 (CPRs 9.7) unless an
-- exemption or a limited-tender condition applies.

-- name: coverage
SELECT
    count(*)                                              AS releases,
    count(DISTINCT cn_id)                                 AS notices,
    count(*) FILTER (release_type = 'amendment')          AS amendments,
    count(DISTINCT cn_id) FILTER (release_type = 'amendment') AS notices_amended,
    count(DISTINCT ocid)                                  AS ocids,
    min(published_au)                                     AS first_published,
    max(published_au)                                     AS last_published,
    max(release_au)                                       AS last_release,
    count(DISTINCT agency)                                AS agencies
FROM releases;

-- name: chain
-- Is every version of every notice here, and what does each amendment point at?
WITH r AS (SELECT * FROM releases),
per_cn AS (
    SELECT cn_id, count(*) AS versions, max(amendment_no) AS max_no,
           count(*) FILTER (amendment_no = 0) AS parents,
           count(DISTINCT amendment_no) AS distinct_nos,
           count(DISTINCT published_ts) AS publish_dates,
           count(DISTINCT ocid) AS ocids,
           count(DISTINCT start_au) AS starts, count(DISTINCT end_au) AS ends
    FROM r GROUP BY cn_id
),
links AS (
    SELECT a.amends_release_id = p.release_id AS to_parent,
           a.amends_release_id = q.release_id AS to_previous
    FROM r a
    LEFT JOIN r p ON p.cn_id = a.cn_id AND p.amendment_no = 0
    LEFT JOIN r q ON q.cn_id = a.cn_id AND q.amendment_no = a.amendment_no - 1
    WHERE a.amendment_no > 0
)
SELECT
    (SELECT count(*) FROM per_cn WHERE parents = 0)                      AS notices_missing_parent,
    (SELECT count(*) FROM per_cn WHERE max_no + 1 <> versions OR distinct_nos <> versions) AS notices_with_gaps,
    (SELECT count(*) FROM per_cn WHERE publish_dates > 1)                AS notices_publish_date_varies,
    (SELECT count(*) FROM per_cn WHERE ocids > 1)                        AS notices_several_ocids,
    (SELECT count(*) FROM links)                                         AS amendments,
    (SELECT count(*) FROM links WHERE to_parent)                         AS amendments_point_to_notice,
    (SELECT count(*) FROM links WHERE coalesce(to_previous, false) AND NOT to_parent) AS amendments_point_to_previous_only,
    (SELECT count(*) FROM links WHERE NOT coalesce(to_parent, false) AND NOT coalesce(to_previous, false)) AS amendments_point_elsewhere,
    (SELECT count(*) FROM per_cn WHERE versions > 1 AND (starts > 1 OR ends > 1)) AS amended_notices_dates_change,
    (SELECT max(max_no) FROM per_cn)                                     AS most_amendments;

-- name: amendment_steps
-- What does an amendment do to the value? (Its value is the new total; see AMENDMENT_CHECK.md.)
WITH steps AS (
    SELECT a.value_aud - p.value_aud AS step
    FROM releases a JOIN releases p ON p.cn_id = a.cn_id AND p.amendment_no = a.amendment_no - 1
)
SELECT count(*)                          AS amendments,
       count(*) FILTER (step > 0)        AS increase,
       count(*) FILTER (step = 0)        AS no_change,
       count(*) FILTER (step < 0)        AS decrease,
       (SELECT count(*) FROM releases WHERE value_aud < 0)  AS negative_values,
       (SELECT count(*) FROM releases WHERE value_aud = 0)  AS zero_values
FROM steps;

-- name: double_count
-- What you'd get by summing the wrong thing.
SELECT
    (SELECT sum(value_aud) FROM releases)            AS sum_every_version,
    (SELECT sum(value_aud) FROM notices)             AS sum_current_value,
    (SELECT sum(original_value_aud) FROM notices)    AS sum_value_at_award,
    (SELECT sum(value_aud) FROM releases) / (SELECT sum(value_aud) FROM notices) AS overstatement;

-- name: amendment_timing
-- When were amendments published? Grouped by Canberra month of the amendment release.
SELECT strftime(release_au, '%Y-%m') AS month, count(*) AS amendments,
       count(DISTINCT release_au) AS days,
       max(per_day) AS busiest_day_count
FROM (
    SELECT release_au, count(*) OVER (PARTITION BY release_au) AS per_day
    FROM releases WHERE release_type = 'amendment'
)
GROUP BY 1 ORDER BY 1;

-- name: busiest_amendment_days
SELECT release_au AS day, count(*) AS amendments, count(DISTINCT agency) AS agencies,
       mode(agency) AS main_agency,
       round(100.0 * count(*) FILTER (agency = (SELECT mode(agency) FROM releases r2
                                                WHERE r2.release_au = r.release_au
                                                  AND r2.release_type = 'amendment'))
             / count(*), 1) AS main_agency_pct
FROM releases r WHERE release_type = 'amendment'
GROUP BY 1 ORDER BY amendments DESC, day LIMIT 5;

-- name: monthly
-- Active notices only: a cancelled notice re-published under a new number would count twice.
SELECT strftime(published_au, '%Y-%m') AS month,
       count(*)                AS notices,
       sum(original_value_aud) AS value_at_award,
       sum(value_aud)          AS current_value
FROM notices WHERE status = 'active' GROUP BY 1 ORDER BY 1;

-- name: value_bands
SELECT band, count(*) AS notices, sum(value_aud) AS current_value
FROM (
    SELECT value_aud,
           CASE WHEN value_aud < 10000    THEN '1. under $10k'
                WHEN value_aud < 80000    THEN '2. $10k to <$80k'
                WHEN value_aud < 1000000  THEN '3. $80k to <$1m'
                WHEN value_aud < 10000000 THEN '4. $1m to <$10m'
                WHEN value_aud < 100000000 THEN '5. $10m to <$100m'
                ELSE '6. $100m and over' END AS band
    FROM notices
)
GROUP BY band ORDER BY band;

-- name: concentration
-- How much of the money sits in the largest notices?
WITH ranked AS (
    SELECT value_aud, row_number() OVER (ORDER BY value_aud DESC) AS rk, count(*) OVER () AS n,
           sum(value_aud) OVER () AS total
    FROM notices
)
SELECT max(n) AS notices,
       sum(value_aud) FILTER (rk <= 10) / max(total)              AS top10_share,
       sum(value_aud) FILTER (rk <= ceil(n * 0.01)) / max(total)  AS top1pct_share,
       ceil(max(n) * 0.01)                                        AS top1pct_notices,
       median(value_aud)                                          AS median_value,
       avg(value_aud)                                             AS mean_value
FROM ranked;

-- name: largest
SELECT cn_id, agency, supplier_name, description, value_aud, original_value_aud,
       n_amendments, method_details, start_au, end_au
FROM notices ORDER BY value_aud DESC, cn_id LIMIT 10;

-- name: methods
SELECT method, method_details, count(*) AS notices,
       sum(value_aud) AS current_value,
       count(*) FILTER (value_aud >= 80000) AS notices_80k_plus
FROM notices GROUP BY ALL ORDER BY notices DESC;

-- name: limited_reasons
-- On the notice's latest version. A limited tender should carry a reason or an exemption.
SELECT method_details,
       count(*)                                                       AS notices,
       count(*) FILTER (limited_reason_code IS NOT NULL)              AS with_reason,
       count(*) FILTER (exemption_code IS NOT NULL)                   AS with_exemption_code,
       count(*) FILTER (exemption_flag = '1')                         AS exempt_flag_1,
       count(*) FILTER (limited_reason_code IS NULL AND exemption_code IS NULL
                        AND coalesce(exemption_flag, '0') <> '1')     AS no_reason_or_exemption,
       count(*) FILTER (limited_reason_code IS NULL AND exemption_code IS NULL
                        AND coalesce(exemption_flag, '0') <> '1' AND value_aud >= 80000)
                                                                      AS no_reason_80k_plus
FROM notices GROUP BY 1 ORDER BY notices DESC;

-- name: limited_patterns
-- How limited tenders are coded, split at $80k on the value at award (the value the
-- procurement threshold is judged on when the contract is let).
SELECT coalesce(exemption_flag, '(blank)')              AS exemption_flag,
       limited_reason_code IS NOT NULL                  AS has_reason_code,
       exemption_code IS NOT NULL                       AS has_exemption_code,
       original_value_aud >= 80000                      AS award_80k_plus,
       count(*)                                         AS notices,
       sum(value_aud)                                   AS current_value
FROM notices WHERE method = 'limited'
GROUP BY ALL ORDER BY notices DESC;

-- name: limited_codes
SELECT 'reason' AS kind, limited_reason_code AS code, any_value(limited_reason) AS meaning, count(*) AS notices,
       sum(value_aud) AS current_value
FROM notices WHERE limited_reason_code IS NOT NULL GROUP BY 1, 2
UNION ALL
SELECT 'exemption', exemption_code, any_value(exemption), count(*), sum(value_aud)
FROM notices WHERE exemption_code IS NOT NULL GROUP BY 1, 2
ORDER BY kind DESC, notices DESC, code;

-- name: status
SELECT status, count(*) AS notices, sum(value_aud) AS current_value
FROM notices GROUP BY 1 ORDER BY notices DESC;

-- name: suppliers
SELECT
    count(*)                                                        AS notices,
    count(*) FILTER (supplier_abn IS NULL)                          AS no_abn,
    count(*) FILTER (supplier_abn IS NULL AND upper(supplier_country) NOT IN ('AUSTRALIA'))
                                                                    AS no_abn_overseas,
    count(*) FILTER (upper(supplier_country) <> 'AUSTRALIA')        AS overseas,
    count(DISTINCT supplier_country)                                AS country_spellings,
    count(DISTINCT upper(supplier_country))                         AS countries,
    count(*) FILTER (supplier_country = 'Australia')                AS country_mixed_case_australia,
    count(DISTINCT supplier_abn)                                    AS distinct_abns,
    count(DISTINCT supplier_name)                                   AS distinct_names,
    count(DISTINCT supplier_id)                                     AS distinct_supplier_ids,
    count(DISTINCT upper(trim(supplier_name)))                      AS distinct_names_upper
FROM notices;

-- name: abn_name_variants
-- One business (ABN), many spellings. Grouping by name would split it.
SELECT supplier_abn, count(DISTINCT supplier_name) AS names, count(*) AS notices,
       sum(value_aud) AS current_value,
       string_agg(DISTINCT supplier_name, ' | ' ORDER BY supplier_name) AS spellings
FROM notices WHERE supplier_abn IS NOT NULL
GROUP BY 1 ORDER BY names DESC, notices DESC, supplier_abn LIMIT 8;

-- name: abn_variant_summary
WITH v AS (
    SELECT supplier_abn, count(DISTINCT supplier_name) AS names, count(*) AS notices,
           sum(value_aud) AS value
    FROM notices WHERE supplier_abn IS NOT NULL GROUP BY 1
)
SELECT count(*) AS abns, count(*) FILTER (names > 1) AS abns_several_names,
       sum(notices) FILTER (names > 1) AS notices_in_those,
       sum(value) FILTER (names > 1) / sum(value) AS value_share_in_those
FROM v;

-- name: supplier_id_meaning
-- Is `supplier_id` a stable supplier key? Count ids per ABN and per exact name.
SELECT
    (SELECT count(*) FROM (SELECT supplier_abn FROM notices WHERE supplier_abn IS NOT NULL
                           GROUP BY 1 HAVING count(DISTINCT supplier_id) > 1))  AS abns_several_ids,
    (SELECT count(*) FROM (SELECT supplier_name FROM notices
                           GROUP BY 1 HAVING count(DISTINCT supplier_id) > 1))  AS names_several_ids,
    (SELECT count(DISTINCT supplier_id) FROM notices)                           AS ids,
    (SELECT count(*) FROM notices)                                              AS notices;

-- name: agencies
SELECT count(DISTINCT agency) AS agency_names, count(DISTINCT agency_abn) AS agency_abns,
       count(DISTINCT agency) FILTER (agency_abn IS NOT NULL) AS names_with_abn,
       count(DISTINCT agency) FILTER (agency_abn IS NULL) AS names_without_abn,
       count(*) FILTER (agency_branch IS NOT NULL) AS with_branch,
       count(*) FILTER (agency_division IS NOT NULL) AS with_division,
       count(*) AS notices
FROM notices;

-- name: agency_abn_variants
SELECT agency_abn, count(DISTINCT agency) AS names,
       string_agg(DISTINCT agency, ' | ' ORDER BY agency) AS names_used
FROM notices GROUP BY 1 HAVING count(DISTINCT agency) > 1 ORDER BY names DESC, agency_abn;

-- name: top_agencies
SELECT agency, count(*) AS notices, sum(value_aud) AS current_value,
       sum(value_aud) / (SELECT sum(value_aud) FROM notices) AS value_share
FROM notices GROUP BY 1 ORDER BY current_value DESC LIMIT 8;

-- name: unspsc_depth
-- UNSPSC codes are 8 digits: segment (2) / family (4) / class (6) / commodity (8).
-- Trailing zeros mean the notice was only coded to a broader level.
SELECT CASE WHEN unspsc LIKE '______00' AND unspsc LIKE '____0000' AND unspsc LIKE '__000000' THEN '1. segment only'
            WHEN unspsc LIKE '____0000' THEN '2. family'
            WHEN unspsc LIKE '______00' THEN '3. class'
            ELSE '4. commodity' END AS depth,
       count(*) AS notices, sum(value_aud) AS current_value
FROM notices GROUP BY 1 ORDER BY 1;

-- name: unspsc_codes
SELECT count(DISTINCT unspsc) AS codes, count(DISTINCT left(unspsc, 2)) AS segments,
       count(DISTINCT left(unspsc, 4)) AS families,
       count(*) FILTER (length(unspsc) <> 8 OR NOT regexp_full_match(unspsc, '[0-9]{8}')) AS malformed
FROM notices;

-- name: dates
-- Reporting lag: CPRs 7.18 asks for a notice within 42 days of the contract starting.
SELECT
    count(*)                                                        AS notices,
    count(*) FILTER (end_au < start_au)                             AS end_before_start,
    count(*) FILTER (start_au > published_au)                       AS starts_after_publish,
    -- Lag figures leave out placeholder start dates (before 2000).
    count(*) FILTER (published_au - original_start_au > 42 AND original_start_au >= DATE '2000-01-01')
                                                                    AS published_over_42d_after_start,
    count(*) FILTER (published_au - original_start_au > 365 AND original_start_au >= DATE '2000-01-01')
                                                                    AS published_over_1y_after_start,
    median(published_au - original_start_au) FILTER (original_start_au >= DATE '2000-01-01')
                                                                    AS median_lag_days,
    median(original_end_au - original_start_au)                     AS median_term_days,
    count(*) FILTER (original_end_au - original_start_au > 3653)    AS terms_over_10y,
    count(*) FILTER (original_start_au < DATE '2000-01-01')         AS start_before_2000,
    count(*) FILTER (original_start_au = DATE '1900-01-01')         AS start_1900_01_01,
    min(original_start_au) AS earliest_start, max(original_end_au) AS latest_end
FROM notices;

-- name: lag_by_value
SELECT CASE WHEN value_aud < 80000 THEN '1. under $80k' WHEN value_aud < 1000000 THEN '2. $80k to <$1m'
            ELSE '3. $1m and over' END AS band,
       count(*) AS notices,
       count(*) FILTER (published_au - original_start_au > 42) AS over_42d,
       round(100.0 * count(*) FILTER (published_au - original_start_au > 42) / count(*), 1) AS over_42d_pct
FROM notices WHERE original_start_au >= DATE '2000-01-01' GROUP BY 1 ORDER BY 1;

-- name: lookalikes
-- Different notice numbers, same agency, supplier, value at award, start date and description.
-- `extra_*` counts everything beyond the first notice in each group. The second set of columns
-- repeats the check on active notices only, because a cancelled notice is often re-published.
WITH base AS (
    SELECT *, coalesce(supplier_abn, supplier_id) AS supplier_key, lower(trim(description)) AS d
    FROM notices
),
k AS (
    SELECT agency, supplier_key, original_value_aud, original_start_au, d,
           count(*) AS n, count(*) FILTER (status = 'cancelled') AS n_cancelled,
           count(*) FILTER (status = 'active') AS n_active
    FROM base GROUP BY agency, supplier_key, original_value_aud, original_start_au, d
    HAVING count(*) > 1
)
SELECT count(*)                                                     AS groups,
       sum(n) - count(*)                                            AS extra_notices,
       sum((n - 1) * original_value_aud)                            AS extra_value,
       count(*) FILTER (n_cancelled > 0)                            AS groups_with_cancelled,
       count(*) FILTER (n_active > 1)                               AS active_groups,
       sum(n_active - 1) FILTER (n_active > 1)                      AS active_extra_notices,
       sum((n_active - 1) * original_value_aud) FILTER (n_active > 1) AS active_extra_value,
       (SELECT sum(original_value_aud) FROM notices WHERE status = 'active') AS active_value_at_award
FROM k;

-- name: largest_lookalikes
WITH base AS (
    SELECT *, coalesce(supplier_abn, supplier_id) AS supplier_key, lower(trim(description)) AS d
    FROM notices
)
SELECT any_value(agency) AS agency, any_value(supplier_name) AS supplier, any_value(description) AS description,
       original_value_aud, count(*) AS notices,
       string_agg(cn_id || ' (' || status || ')', ', ' ORDER BY cn_id) AS notice_ids
FROM base
GROUP BY agency, supplier_key, original_value_aud, original_start_au, d
HAVING count(*) > 1
ORDER BY original_value_aud * (count(*) - 1) DESC, notice_ids
LIMIT 5;

-- name: code_changes
-- Do method or limited-tender codes change between a notice's first and latest version?
SELECT count(*) AS amended_notices,
       count(*) FILTER (n.method <> o.method
                        OR coalesce(n.limited_reason_code, '') <> coalesce(o.limited_reason_code, '')
                        OR coalesce(n.exemption_code, '') <> coalesce(o.exemption_code, '')
                        OR coalesce(n.exemption_flag, '') <> coalesce(o.exemption_flag, '')) AS changed
FROM notices n JOIN releases o ON o.cn_id = n.cn_id AND o.amendment_no = 0
WHERE n.n_amendments > 0;
