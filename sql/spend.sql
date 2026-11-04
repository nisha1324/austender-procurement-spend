-- Part 2: the spend cube. Active notices, latest (committed) value, from the `spend` view.
-- Each query starts with `-- name: <id>`; scripts/spend_cube.py runs them in order.
-- "Large" families: $100m or more and at least 20 notices, so one-off buys don't dominate.

-- name: totals
SELECT count(*) AS notices, sum(value_aud) AS value, sum(original_value_aud) AS value_at_award,
       count(DISTINCT supplier_key) AS suppliers, count(DISTINCT agency_key) AS agencies,
       count(*) FILTER (supplier_key LIKE 'ID %') AS notices_no_abn,
       count(*) FILTER (supplier_key LIKE 'ID %' AND supplier_country <> 'AUSTRALIA') AS notices_no_abn_overseas,
       count(*) FILTER (unspsc IS NOT NULL AND category_title IS NULL) AS codes_not_in_codeset,
       count(*) FILTER (family IS NULL) AS segment_only_notices,
       sum(value_aud) FILTER (family IS NULL) AS segment_only_value,
       count(*) FILTER (is_defence) AS defence_notices,
       sum(value_aud) FILTER (is_defence) AS defence_value,
       (SELECT count(*) FROM categories) AS codeset_codes,
       (SELECT count(DISTINCT family) FROM categories WHERE family <> '') AS codeset_families,
       (SELECT count(DISTINCT family) FROM categories
         WHERE family_title_source = 'derived from child codes') AS families_titled_by_hand,
       count(DISTINCT unspsc) AS codes_used, count(DISTINCT family) AS families_used,
       count(DISTINCT segment) AS segments_used
FROM spend;

-- name: goods_services
SELECT goods_services, count(*) AS notices, sum(value_aud) AS value,
       sum(value_aud) / (SELECT sum(value_aud) FROM spend) AS value_share,
       median(value_aud) AS median_notice
FROM spend GROUP BY 1 ORDER BY value DESC;

-- name: segments
SELECT segment, any_value(segment_title) AS segment_title, count(*) AS notices,
       sum(value_aud) AS value,
       sum(value_aud) / (SELECT sum(value_aud) FROM spend) AS value_share,
       coalesce(sum(value_aud) FILTER (is_defence), 0) AS defence_value,
       coalesce(sum(value_aud) FILTER (is_defence), 0) / sum(value_aud) AS defence_share,
       median(value_aud) AS median_notice
FROM spend GROUP BY 1 ORDER BY value DESC, segment;

-- name: families
SELECT family, any_value(family_title) AS family_title, any_value(segment_title) AS segment_title,
       count(*) AS notices, sum(value_aud) AS value,
       sum(value_aud) / (SELECT sum(value_aud) FROM spend) AS value_share,
       coalesce(sum(value_aud) FILTER (is_defence), 0) / sum(value_aud) AS defence_share,
       count(DISTINCT agency_key) AS agencies, count(DISTINCT supplier_key) AS suppliers
FROM spend WHERE family IS NOT NULL
GROUP BY 1 ORDER BY value DESC, family;

-- name: agencies
WITH a AS (
    SELECT agency_key, count(*) AS notices, sum(value_aud) AS value,
           median(value_aud) AS median_notice, count(DISTINCT supplier_key) AS suppliers
    FROM spend GROUP BY 1
),
top_family AS (
    SELECT agency_key, arg_max(family_title, (v, family)) AS top_family,
           max(v) / sum(v) AS top_family_share
    FROM (SELECT agency_key, family, any_value(family_title) AS family_title, sum(value_aud) AS v
          FROM spend WHERE family IS NOT NULL GROUP BY 1, 2)
    GROUP BY 1
),
sup AS (
    SELECT agency_key, sum(v) FILTER (rk <= 5) / sum(v) AS top5_supplier_share
    FROM (SELECT agency_key, supplier_key, sum(value_aud) AS v,
                 row_number() OVER (PARTITION BY agency_key ORDER BY sum(value_aud) DESC, supplier_key) AS rk
          FROM spend GROUP BY 1, 2)
    GROUP BY 1
)
SELECT l.agency_label AS agency, a.notices, a.value,
       a.value / (SELECT sum(value_aud) FROM spend) AS value_share,
       a.median_notice, a.suppliers, s.top5_supplier_share, t.top_family, t.top_family_share
FROM a
JOIN agency_labels l USING (agency_key)
JOIN sup s USING (agency_key)
LEFT JOIN top_family t USING (agency_key)
ORDER BY a.value DESC, agency;

-- name: suppliers
SELECT l.supplier, count(*) AS notices, sum(value_aud) AS value,
       sum(value_aud) / (SELECT sum(value_aud) FROM spend) AS value_share,
       count(DISTINCT agency_key) AS agencies, count(DISTINCT family) AS families,
       count(DISTINCT supplier_name) AS names,
       coalesce(sum(value_aud) FILTER (is_defence), 0) / sum(value_aud) AS defence_share,
       max(value_aud) / sum(value_aud) AS largest_notice_share,
       s.supplier_key LIKE 'ID %' AS no_abn
FROM spend s JOIN supplier_labels l USING (supplier_key)
GROUP BY l.supplier, s.supplier_key ORDER BY value DESC, l.supplier;

-- name: supplier_base
WITH sk AS (SELECT supplier_key, sum(value_aud) AS v, count(*) AS notices FROM spend GROUP BY 1),
r AS (
    SELECT *, sum(v) OVER (ORDER BY v DESC, supplier_key ROWS UNBOUNDED PRECEDING) / sum(v) OVER () AS cum,
           row_number() OVER (ORDER BY v DESC, supplier_key) AS rk
    FROM sk
)
SELECT count(*) AS suppliers,
       min(rk) FILTER (cum >= 0.5 - 1e-9) AS suppliers_for_50pct,
       min(rk) FILTER (cum >= 0.8 - 1e-9) AS suppliers_for_80pct,
       max(cum) FILTER (rk <= 10) AS top10_share,
       max(cum) FILTER (rk <= 100) AS top100_share,
       count(*) FILTER (notices = 1) AS one_notice_suppliers,
       sum(v) FILTER (notices = 1) / sum(v) AS one_notice_value_share
FROM r;

-- name: concentration_all
SELECT * FROM family_concentration(false)
WHERE value >= 100e6 AND notices >= 20 ORDER BY value DESC, family;

-- name: concentration_ex_defence
SELECT * FROM family_concentration(true)
WHERE value >= 100e6 AND notices >= 20 ORDER BY value DESC, family;

-- name: concentration_bands
-- How much of the large families' value sits in each HHI band, and why the high ones are high.
SELECT 'all agencies' AS scope, hhi_band, driver, count(*) AS families, sum(value) AS value
FROM family_concentration(false) WHERE value >= 100e6 AND notices >= 20 GROUP BY ALL
UNION ALL
SELECT 'without Defence', hhi_band, driver, count(*), sum(value)
FROM family_concentration(true) WHERE value >= 100e6 AND notices >= 20 GROUP BY ALL
ORDER BY scope, hhi_band, driver;

-- name: fragmented
-- Large families bought by many agencies from a long tail of suppliers: where a whole-of-
-- government arrangement could pool demand. The API has no panel flag, so some of this
-- spend may already go through panels; this is a list to check, not a finding.
SELECT family, family_title, value, notices, agencies, suppliers, suppliers_for_80pct,
       median_notice, top1_share
FROM family_concentration(false)
WHERE value >= 100e6 AND notices >= 20 AND agencies >= 20 AND suppliers_for_80pct >= 30
ORDER BY suppliers_for_80pct DESC, family;

-- name: cube
-- The spend cube for BI tools: agency x category family x goods/services.
SELECT l.agency_label AS agency, coalesce(s.segment, '') AS segment,
       coalesce(s.segment_title, '') AS segment_title,
       coalesce(s.family, '') AS family,
       coalesce(s.family_title, '(segment only)') AS family_title, s.goods_services,
       count(*) AS notices, count(DISTINCT s.supplier_key) AS suppliers,
       sum(s.value_aud) AS value, sum(s.original_value_aud) AS value_at_award
FROM spend s JOIN agency_labels l USING (agency_key)
GROUP BY ALL ORDER BY agency, segment, family;
