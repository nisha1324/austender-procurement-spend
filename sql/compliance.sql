-- Part 3: competition and compliance, on active notices (the `comp` view).
-- Each query starts with `-- name: <id>`; scripts/compliance.py runs them in order.
-- Thresholds are judged on the value at award; spend figures use the current (committed) value.

-- name: totals
SELECT count(*)                                                     AS notices,
       count(*) FILTER (award_80k_plus)                             AS notices_80k,
       sum(award_value) FILTER (award_80k_plus)                     AS award_value_80k,
       count(*) FILTER (award_80k_plus AND method = 'limited')      AS limited_80k,
       sum(award_value) FILTER (award_80k_plus AND method = 'limited') AS limited_award_value_80k,
       sum(current_value) FILTER (award_80k_plus AND method = 'limited') AS limited_current_value_80k,
       count(*) FILTER (NOT award_80k_plus)                         AS notices_under_80k,
       count(*) FILTER (NOT award_80k_plus AND method = 'limited')  AS limited_under_80k,
       count(*) FILTER (award_80k_plus AND NOT is_defence)          AS notices_80k_ex_defence,
       count(*) FILTER (award_80k_plus AND NOT is_defence AND method = 'limited') AS limited_80k_ex_defence,
       sum(award_value) FILTER (award_80k_plus AND NOT is_defence)  AS award_value_80k_ex_defence,
       sum(award_value) FILTER (award_80k_plus AND NOT is_defence AND method = 'limited')
                                                                    AS limited_award_value_80k_ex_defence,
       count(*) FILTER (award_80k_plus AND route LIKE '5.%')        AS no_code_80k,
       count(*) FILTER (award_80k_plus AND route LIKE '5.%' AND current_value < 80000 AND n_amendments > 0)
                                                                    AS no_code_80k_amended_below,
       count(*) FILTER (award_80k_plus AND limited_reason_code IN ('AD', 'TR')) AS ad_tr_80k,
       sum(award_value) FILTER (award_80k_plus AND limited_reason_code IN ('AD', 'TR')) AS ad_tr_award_value_80k
FROM comp;

-- name: routes
-- Notices of $80k and over at award, by route; with and without Defence.
SELECT route,
       count(*) AS notices,
       round(count(*) / sum(count(*)) OVER (), 9) AS notice_share,
       sum(award_value) AS award_value,
       round(sum(award_value) / sum(sum(award_value)) OVER (), 9) AS award_value_share,
       sum(current_value) AS current_value,
       count(*) FILTER (NOT is_defence) AS notices_ex_defence,
       coalesce(sum(award_value) FILTER (NOT is_defence), 0) AS award_value_ex_defence
FROM comp WHERE award_80k_plus
GROUP BY 1 ORDER BY 1;

-- name: limited_codes
-- Limited tenders of $80k and over at award, by the condition or exemption they give.
SELECT CASE WHEN limited_reason_code IS NOT NULL THEN '10.3 condition' ELSE 'exemption' END AS kind,
       coalesce(limited_reason_code, exemption_code) AS code,
       any_value(coalesce(limited_reason, exemption)) AS meaning,
       count(*) AS notices, sum(award_value) AS award_value, sum(current_value) AS current_value,
       count(DISTINCT agency_key) AS agencies,
       round(coalesce(sum(award_value) FILTER (is_defence), 0) / sum(award_value), 9) AS defence_share
FROM comp
WHERE award_80k_plus AND method = 'limited' AND coalesce(limited_reason_code, exemption_code) IS NOT NULL
GROUP BY 1, 2 ORDER BY award_value DESC, code;

-- name: limited_by_agency
-- Agencies with at least 100 notices of $80k and over: how much of it is a limited tender.
WITH a AS (
    SELECT agency_key, any_value(agency) AS agency, count(*) AS notices_80k,
           sum(award_value) AS award_value_80k,
           count(*) FILTER (method = 'limited') AS limited,
           coalesce(sum(award_value) FILTER (method = 'limited'), 0) AS limited_award_value,
           count(*) FILTER (route LIKE '3.%') AS by_condition,
           count(*) FILTER (route LIKE '4.%') AS by_exemption,
           count(*) FILTER (route LIKE '5.%') AS no_code
    FROM comp WHERE award_80k_plus GROUP BY 1
),
top_code AS (
    SELECT agency_key,
           arg_max(code, (v, code)) AS top_code,
           max(v) / sum(v) AS top_code_share
    FROM (SELECT agency_key, coalesce(limited_reason_code, exemption_code) AS code, sum(award_value) AS v
          FROM comp WHERE award_80k_plus AND method = 'limited'
            AND coalesce(limited_reason_code, exemption_code) IS NOT NULL GROUP BY 1, 2)
    GROUP BY 1
)
SELECT a.agency, a.notices_80k, a.award_value_80k, a.limited,
       round(a.limited / a.notices_80k, 9) AS limited_share,
       round(a.limited_award_value / a.award_value_80k, 9) AS limited_value_share,
       a.by_condition, a.by_exemption, a.no_code,
       t.top_code, round(t.top_code_share, 9) AS top_code_share
FROM a LEFT JOIN top_code t USING (agency_key)
WHERE a.notices_80k >= 100
ORDER BY limited_value_share DESC, agency;

-- name: bunching_points
-- Bunching test. For each round amount P, count notices whose value at award falls in the last
-- $1,000 before P and compare with the mean of the 8 neighbouring $1,000 bins (4 below that bin,
-- 4 above the bin that starts at P). The bin starting at P is left out because round amounts
-- ($80,000.00 itself) pile up there. `ratio_not_round` repeats it without whole-thousand values.
WITH pts AS (SELECT unnest(range(30000, 160001, 10000)) AS p),
b AS (
    SELECT p, floor((award_value - p) / 1000)::INTEGER AS k, award_value % 1000 = 0 AS whole_k, method
    FROM pts, comp
    WHERE award_value >= p - 5000 AND award_value < p + 5000
)
SELECT p AS amount, p = 80000 AS is_threshold,
       count(*) FILTER (k = -1) AS last_1k,
       round(count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4)) / 8, 1) AS neighbour_mean,
       round(count(*) FILTER (k = -1) / (count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4)) / 8), 2) AS ratio,
       round(count(*) FILTER (k = -1 AND NOT whole_k)
             / (count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4) AND NOT whole_k) / 8), 2) AS ratio_not_round,
       round(count(*) FILTER (k = -1 AND method = 'limited') / count(*) FILTER (k = -1), 9) AS last_1k_limited_share,
       round(count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4) AND method = 'limited')
             / count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4)), 9) AS neighbour_limited_share
FROM b GROUP BY p ORDER BY p;

-- name: bunching_scan
-- The same test on every $1,000 bin from $25k to $195k, not only round amounts: bin j against
-- bins j-4..j-1 and j+2..j+5 (j+1 left out, as above). `same_value_max`: the most notices in the
-- bin that share one exact value (one agency's standard fee shows up here). Ranked on
-- `ratio_not_round`, because every bin that starts at a round amount fills up with whole-thousand
-- values ($50,000.00 alone is 1,681 notices).
WITH c AS (
    SELECT floor(award_value / 1000)::INTEGER AS k, count(*) AS notices,
           count(*) FILTER (award_value % 1000 <> 0) AS not_round
    FROM comp WHERE award_value >= 20000 AND award_value < 201000 GROUP BY 1
),
same AS (
    SELECT k, max(m) AS same_value_max
    FROM (SELECT floor(award_value / 1000)::INTEGER AS k, award_value, count(*) AS m FROM comp
          WHERE award_value >= 25000 AND award_value < 195000 GROUP BY 1, 2) GROUP BY 1
)
SELECT (a.k * 1000)::INTEGER AS bin, a.notices,
       round(avg(x.notices), 1) AS neighbour_mean,
       round(a.notices / avg(x.notices), 2) AS ratio,
       round(a.not_round / avg(x.not_round), 2) AS ratio_not_round,
       s.same_value_max
FROM c a
JOIN c x ON x.k BETWEEN a.k - 4 AND a.k + 5 AND x.k NOT IN (a.k, a.k + 1)
JOIN same s ON s.k = a.k
WHERE a.k BETWEEN 25 AND 194
GROUP BY a.k, a.notices, a.not_round, s.same_value_max
ORDER BY ratio_not_round DESC, bin;

-- name: bunching_relative
-- The same test at the other thresholds and policy amounts, with bins of 1.25% of the amount.
-- $88,000 is $80,000 plus GST, in case some agencies apply the threshold before GST.
WITH pts(p, what) AS (VALUES
    (80000, 'non-corporate entities'), (88000, '$80k plus GST'), (200000, 'round amount'),
    (400000, 'prescribed corporate entities'), (500000, 'SME exemption ceiling (App A 17)'),
    (1000000, 'round amount'), (7500000, 'construction services')),
b AS (
    SELECT p, what, floor((award_value - p) / (p * 0.0125))::INTEGER AS k
    FROM pts, comp WHERE award_value >= p * 0.9375 AND award_value < p * 1.0625
)
SELECT p AS amount, what,
       count(*) FILTER (k = -1) AS last_bin,
       round(count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4)) / 8, 1) AS neighbour_mean,
       round(count(*) FILTER (k = -1) / (count(*) FILTER (k IN (-5, -4, -3, -2, 1, 2, 3, 4)) / 8), 2) AS ratio
FROM b GROUP BY p, what ORDER BY p;

-- name: bunching_bins
-- $1,000 bins of value at award from $60k to $100k, for the chart.
SELECT (floor(award_value / 1000) * 1000)::INTEGER AS bin, count(*) AS notices,
       count(*) FILTER (method = 'limited') AS limited,
       count(*) FILTER (award_value % 1000 = 0) AS whole_thousands
FROM comp WHERE award_value >= 60000 AND award_value < 100000
GROUP BY 1 ORDER BY 1;

-- name: bunching_detail
-- What is in the last $1,000 before $80k.
SELECT count(*) AS notices, count(DISTINCT agency_key) AS agencies,
       count(*) FILTER (method = 'limited') AS limited,
       count(*) FILTER (method = 'open') AS open,
       count(*) FILTER (route LIKE '5.%') AS limited_no_code,
       count(*) FILTER (award_value = 79200) AS at_79200,
       sum(award_value) AS award_value,
       (SELECT count(*) FROM comp WHERE award_value = 80000) AS at_80000,
       (SELECT count(*) FROM comp WHERE award_value = 80000 AND method = 'limited') AS at_80000_limited,
       (SELECT count(*) FROM comp WHERE award_value = 80000 AND method = 'limited'
          AND route IN ('3. Limited: a 10.3 condition', '4. Limited: an exemption')) AS at_80000_limited_coded
FROM comp WHERE award_value >= 79000 AND award_value < 80000;

-- name: bunching_agencies
-- Agencies with at least 8 notices in the last $1,000 before $80k, against their own neighbouring
-- bins (same 8 bins as above). `same_value_max`: the most notices sharing one exact value.
WITH b AS (
    SELECT agency_key, any_value(agency) AS agency,
           count(*) FILTER (award_value >= 79000 AND award_value < 80000) AS last_1k,
           count(*) FILTER ((award_value >= 75000 AND award_value < 79000)
                            OR (award_value >= 81000 AND award_value < 85000)) / 8 AS neighbour_mean_raw
    FROM comp WHERE award_value >= 75000 AND award_value < 85000 GROUP BY 1
),
same AS (
    SELECT agency_key, max(c) AS same_value_max FROM (
        SELECT agency_key, award_value, count(*) AS c FROM comp
        WHERE award_value >= 79000 AND award_value < 80000 GROUP BY 1, 2) GROUP BY 1
)
SELECT b.agency, b.last_1k, round(b.neighbour_mean_raw, 1) AS neighbour_mean, s.same_value_max
FROM b JOIN same s USING (agency_key)
WHERE b.last_1k >= 8 ORDER BY b.last_1k DESC, b.agency;

-- name: split_summary
-- Possible split purchases: limited tenders each under $80k at award, from one agency to one
-- supplier, with the same description and start date, published within 30 days of each other,
-- adding up to $80k or more. The CPRs bar dividing a procurement to get under a threshold, but
-- most such groups have ordinary explanations (separate engagements, one notice per period or
-- per site). This is a list to review, not a finding. Suppliers are not named: some are individuals.
WITH g AS (
    SELECT agency_key, any_value(agency) AS agency, supplier_key, lower(trim(description)) AS d, start_au,
           count(*) AS notices, sum(award_value) AS award_value, max(award_value) AS largest
    FROM comp
    WHERE method = 'limited' AND award_value < 80000
    GROUP BY agency_key, supplier_key, lower(trim(description)), start_au
    HAVING count(*) >= 2 AND sum(award_value) >= 80000 AND max(published_au) - min(published_au) <= 30
)
SELECT count(*) AS groups, sum(notices) AS notices, sum(award_value) AS award_value,
       count(DISTINCT agency_key) AS agencies,
       count(*) FILTER (agency = 'Department of Defence') AS defence_groups,
       median(notices) AS median_notices,
       (SELECT count(*) FROM comp WHERE method = 'limited' AND award_value < 80000) AS limited_under_80k
FROM g;

-- name: split_by_agency
WITH g AS (
    SELECT agency_key, any_value(agency) AS agency, supplier_key, lower(trim(description)) AS d, start_au,
           count(*) AS notices, sum(award_value) AS award_value
    FROM comp
    WHERE method = 'limited' AND award_value < 80000
    GROUP BY agency_key, supplier_key, lower(trim(description)), start_au
    HAVING count(*) >= 2 AND sum(award_value) >= 80000 AND max(published_au) - min(published_au) <= 30
)
SELECT agency, count(*) AS groups, sum(notices) AS notices, sum(award_value) AS award_value,
       arg_max(d, (award_value, d)) AS largest_group_description,
       arg_max(notices, (award_value, d)) AS largest_group_notices,
       max(award_value) AS largest_group_value
FROM g GROUP BY agency_key, agency ORDER BY groups DESC, award_value DESC, agency;

-- name: late_totals
SELECT count(*) AS notices,
       count(lag_days) AS with_start,
       count(*) FILTER (lag_days > 42) AS late,
       round(count(*) FILTER (lag_days > 42) / count(lag_days), 9) AS late_share,
       sum(current_value) FILTER (lag_days > 42) AS late_value,
       count(*) FILTER (lag_days > 42 AND lag_days <= 90) AS late_43_90,
       count(*) FILTER (lag_days > 90 AND lag_days <= 365) AS late_91_365,
       count(*) FILTER (lag_days > 365) AS late_over_1y,
       count(*) FILTER (lag_days < 0) AS starts_after_publish,
       median(lag_days) AS median_lag,
       round(count(*) FILTER (lag_days > 42 AND method = 'limited') / count(lag_days) FILTER (method = 'limited'), 9)
           AS late_share_limited,
       round(count(*) FILTER (lag_days > 42 AND method = 'open') / count(lag_days) FILTER (method = 'open'), 9)
           AS late_share_open
FROM comp;

-- name: late_batches
-- Catch-up reporting: an agency publishing 10 or more late notices on one day.
WITH d AS (
    SELECT agency_key, published_au, count(*) FILTER (lag_days > 42) AS late, count(*) AS published
    FROM comp GROUP BY 1, 2
)
SELECT count(*) FILTER (late >= 10) AS batch_days,
       count(DISTINCT agency_key) FILTER (late >= 10) AS batch_agencies,
       sum(late) FILTER (late >= 10) AS late_in_batches,
       sum(late) AS late,
       round(sum(late) FILTER (late >= 10) / sum(late), 9) AS batch_share
FROM d;

-- name: late_top_batches
-- The largest catch-up days, with their most common description and the range of start dates.
WITH l AS (SELECT * FROM comp WHERE lag_days > 42),
d AS (
    SELECT agency_key, any_value(agency) AS agency, published_au, count(*) AS late,
           median(lag_days) AS median_lag, min(start_au) AS earliest_start, max(start_au) AS latest_start
    FROM l GROUP BY 1, 3 HAVING count(*) >= 10
),
desc_ AS (
    SELECT agency_key, published_au, arg_max(d, (c, d)) AS main_description, max(c) AS main_description_notices
    FROM (SELECT agency_key, published_au, lower(trim(description)) AS d, count(*) AS c
          FROM l GROUP BY 1, 2, 3)
    GROUP BY 1, 2
),
start_ AS (
    SELECT agency_key, published_au, arg_max(s, (c, s)) AS main_start, max(c) AS main_start_notices
    FROM (SELECT agency_key, published_au, start_au AS s, count(*) AS c FROM l GROUP BY 1, 2, 3)
    GROUP BY 1, 2
)
SELECT d.agency, strftime(d.published_au, '%Y-%m-%d') AS published, d.late, d.median_lag,
       x.main_description, x.main_description_notices,
       strftime(st.main_start, '%Y-%m-%d') AS main_start, st.main_start_notices,
       strftime(d.earliest_start, '%Y-%m-%d') AS earliest_start, strftime(d.latest_start, '%Y-%m-%d') AS latest_start
FROM d JOIN desc_ x USING (agency_key, published_au) JOIN start_ st USING (agency_key, published_au)
ORDER BY d.late DESC, d.agency, d.published_au LIMIT 10;

-- name: late_by_agency
-- Agencies with at least 300 notices (with a usable start date).
WITH d AS (
    SELECT agency_key, published_au, count(*) FILTER (lag_days > 42) AS late_that_day
    FROM comp GROUP BY 1, 2
)
SELECT any_value(c.agency) AS agency, count(c.lag_days) AS notices,
       count(*) FILTER (c.lag_days > 42) AS late,
       round(count(*) FILTER (c.lag_days > 42) / count(c.lag_days), 9) AS late_share,
       count(*) FILTER (c.lag_days > 42 AND d.late_that_day >= 10) AS late_in_batches,
       round(count(*) FILTER (c.lag_days > 42 AND d.late_that_day < 10) / count(c.lag_days), 9) AS late_share_outside_batches,
       median(c.lag_days) AS median_lag,
       count(*) FILTER (c.lag_days > 365) AS over_1y
FROM comp c JOIN d USING (agency_key, published_au)
GROUP BY c.agency_key HAVING count(c.lag_days) >= 300
ORDER BY late_share DESC, agency;

-- name: late_by_month
SELECT strftime(published_au, '%Y-%m') AS month, count(lag_days) AS notices,
       count(*) FILTER (lag_days > 42) AS late,
       round(count(*) FILTER (lag_days > 42) / count(lag_days), 9) AS late_share
FROM comp GROUP BY 1 ORDER BY 1;

-- name: growth_totals
SELECT count(*) AS notices,
       count(*) FILTER (n_amendments > 0) AS amended,
       count(*) FILTER (current_value > award_value) AS grew,
       sum(award_value) AS award_value, sum(current_value) AS current_value,
       sum(current_value) - sum(award_value) AS net_added,
       round(sum(current_value) / sum(award_value) - 1, 9) AS growth,
       count(*) FILTER (current_value >= 2 * award_value) AS doubled,
       count(*) FILTER (current_value >= 10 * award_value) AS tenfold,
       sum(current_value - award_value) FILTER (current_value >= 10 * award_value) AS tenfold_added
FROM comp;

-- name: growth_by_route
-- Notices of $80k and over at award: how much they grew after award, by route.
SELECT route, count(*) AS notices, sum(award_value) AS award_value,
       sum(current_value) - sum(award_value) AS added,
       round(sum(current_value) / sum(award_value) - 1, 9) AS growth,
       round(count(*) FILTER (current_value > award_value) / count(*), 9) AS share_grew,
       round(count(*) FILTER (current_value >= 2 * award_value) / count(*), 9) AS share_doubled
FROM comp WHERE award_80k_plus GROUP BY 1 ORDER BY 1;

-- name: growth_by_code
-- Limited tenders of $80k and over with a code, by code (codes with 20+ notices).
SELECT coalesce(limited_reason_code, exemption_code) AS code,
       any_value(coalesce(limited_reason, exemption)) AS meaning,
       count(*) AS notices, sum(award_value) AS award_value,
       sum(current_value) - sum(award_value) AS added,
       round(sum(current_value) / sum(award_value) - 1, 9) AS growth
FROM comp WHERE award_80k_plus AND method = 'limited' AND coalesce(limited_reason_code, exemption_code) IS NOT NULL
GROUP BY 1 HAVING count(*) >= 20 ORDER BY growth DESC, code;

-- name: growth_top
-- The 12 notices that grew most after award (dollars added).
SELECT cn_id, agency, description, route, award_value, current_value,
       current_value - award_value AS added, round(current_value / award_value, 1) AS times, n_amendments
FROM comp ORDER BY added DESC, cn_id LIMIT 12;

-- name: placeholders
-- Notices first published at exactly $10,000 (the reporting threshold) and later amended upward.
SELECT agency, count(*) AS notices, count(*) FILTER (current_value >= 10 * award_value) AS tenfold,
       sum(award_value) AS award_value, sum(current_value) AS current_value,
       arg_max(lower(trim(description)), (current_value, cn_id)) AS largest_description
FROM comp WHERE award_value = 10000 AND current_value > award_value
GROUP BY agency_key, agency ORDER BY current_value DESC, agency;

-- name: placeholder_mix
-- What the largest placeholder agency's notices are.
WITH top AS (
    SELECT agency_key FROM comp WHERE award_value = 10000 AND current_value > award_value
    GROUP BY 1 ORDER BY sum(current_value) DESC LIMIT 1
)
SELECT lower(trim(description)) AS description, count(*) AS notices, sum(current_value) AS current_value
FROM comp WHERE award_value = 10000 AND current_value > award_value AND agency_key IN (SELECT agency_key FROM top)
GROUP BY 1 ORDER BY current_value DESC, description;

-- name: crossed_threshold
-- Awarded under $80k, now $80k or more: the threshold was judged on a value the contract outgrew.
SELECT method, count(*) AS notices, sum(award_value) AS award_value, sum(current_value) AS current_value,
       count(*) FILTER (award_value = 10000) AS from_10000,
       count(*) FILTER (current_value >= 1000000) AS now_1m_plus
FROM comp WHERE award_value < 80000 AND current_value >= 80000
GROUP BY 1 ORDER BY notices DESC;
