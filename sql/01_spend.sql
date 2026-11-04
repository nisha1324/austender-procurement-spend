-- Part 2 base: category names plus one row per active notice, with the keys every spend query uses.
-- {categories_csv} is filled in by the Python runner. Needs the views from 00_load.sql.

CREATE OR REPLACE TABLE categories AS
SELECT * FROM read_csv('{categories_csv}', header = true, all_varchar = true);

-- Rules from Part 1: latest version only (the `notices` view), cancelled notices out,
-- suppliers by ABN (else the API's supplier id), agencies by ABN (else name), never by name.
CREATE OR REPLACE VIEW spend AS
SELECT
    n.cn_id, n.published_au, n.agency, n.supplier_name, upper(n.supplier_country) AS supplier_country, n.description, n.unspsc,
    n.value_aud, n.original_value_aud, n.method_details,
    coalesce('ABN ' || n.supplier_abn, 'ID ' || n.supplier_id)       AS supplier_key,
    coalesce('ABN ' || n.agency_abn, 'NAME ' || n.agency)            AS agency_key,
    n.agency = 'Department of Defence'                               AS is_defence,
    c.title                                                          AS category_title,
    c.level                                                          AS category_level,
    c.goods_services,
    c.segment, c.segment_title,
    nullif(c.family, '')                                             AS family,
    nullif(c.family_title, '')                                       AS family_title
FROM notices n
LEFT JOIN categories c ON c.code = n.unspsc
WHERE n.status = 'active';

-- One label per supplier key: its most used name (latest notice breaks ties).
CREATE OR REPLACE VIEW supplier_labels AS
WITH counted AS (
    SELECT supplier_key, supplier_name, count(*) AS uses, max(published_au) AS last_used
    FROM spend GROUP BY 1, 2
)
SELECT supplier_key, arg_max(supplier_name, (uses, last_used, supplier_name)) AS supplier
FROM counted GROUP BY 1;

-- One label per agency key: the name on its most recently published version (Part 1 rule).
CREATE OR REPLACE VIEW agency_labels AS
SELECT coalesce('ABN ' || agency_abn, 'NAME ' || agency) AS agency_key,
       arg_max(agency, (release_ts, agency)) AS agency_label
FROM releases GROUP BY 1;

-- Supplier concentration in each UNSPSC family, on committed value (latest version).
-- HHI: sum of squared supplier shares x 10,000 (one supplier = 10,000).
-- `hhi_without_largest`: the same after dropping the family's single largest notice. If a family
-- is only highly concentrated because of one contract, this falls below 2,500 ('one contract');
-- if it stays above, the concentration goes beyond that one contract, either because the top
-- supplier keeps winning or because the rest of the family is also held by a few suppliers.
CREATE OR REPLACE MACRO family_concentration(leave_out_defence) AS TABLE
WITH base AS (
    SELECT family, supplier_key, agency_key, value_aud AS v,
           row_number() OVER (PARTITION BY family ORDER BY value_aud DESC, cn_id) = 1 AS is_largest
    FROM spend
    WHERE family IS NOT NULL AND NOT (leave_out_defence AND is_defence)
),
fs AS (
    SELECT family, supplier_key, sum(v) AS v, count(*) AS notices, max(v) AS largest,
           sum(v) FILTER (NOT is_largest) AS v_rest
    FROM base GROUP BY 1, 2
),
shares AS (
    SELECT *, v / sum(v) OVER (PARTITION BY family) AS share,
           coalesce(v_rest, 0) / sum(v_rest) OVER (PARTITION BY family) AS share_rest,
           row_number() OVER (PARTITION BY family ORDER BY v DESC, supplier_key) AS rk
    FROM fs
),
cum AS (
    SELECT *, sum(share) OVER (PARTITION BY family ORDER BY rk) AS cum_share FROM shares
),
fam AS (
    SELECT family, sum(v) AS value, sum(notices) AS notices, count(*) AS suppliers,
           max(share) AS top1_share,
           sum(share) FILTER (rk <= 3) AS top3_share,
           10000 * sum(share * share) AS hhi,
           10000 * sum(share_rest * share_rest) AS hhi_without_largest,
           -- Sums are exact (DECIMAL); shares are rounded so results don't depend on the order
           -- DuckDB's parallel aggregation happens to add doubles in.
           max(largest) / sum(v) AS largest_notice_share,
           min(rk) FILTER (cum_share >= 0.8 - 1e-9) AS suppliers_for_80pct,
           any_value(supplier_key) FILTER (rk = 1) AS top_supplier_key,
           any_value(notices) FILTER (rk = 1) AS top_supplier_notices,
           any_value(largest) FILTER (rk = 1) / sum(v) AS top_supplier_largest_notice_share
    FROM cum GROUP BY 1
),
agencies AS (
    SELECT s.family, count(DISTINCT agency_key) AS agencies, median(v) AS median_notice
    FROM base s GROUP BY 1
)
SELECT f.family, (SELECT any_value(family_title) FROM categories c WHERE c.family = f.family) AS family_title,
       f.value, f.notices, a.agencies, f.suppliers, a.median_notice,
       round(f.top1_share, 9) AS top1_share, round(f.top3_share, 9) AS top3_share,
       round(f.hhi)::INTEGER AS hhi, round(f.hhi_without_largest)::INTEGER AS hhi_without_largest,
       round(f.largest_notice_share, 9) AS largest_notice_share, f.suppliers_for_80pct,
       l.supplier AS top_supplier, f.top_supplier_notices,
       round(f.top_supplier_largest_notice_share, 9) AS top_supplier_largest_notice_share,
       CASE WHEN f.hhi > 2500 THEN 'high' WHEN f.hhi >= 1500 THEN 'moderate' ELSE 'low' END AS hhi_band,
       CASE WHEN f.hhi <= 2500 THEN ''
            WHEN f.hhi_without_largest > 2500 THEN 'beyond one contract'
            ELSE 'one contract' END AS driver
FROM fam f
JOIN agencies a USING (family)
JOIN supplier_labels l ON l.supplier_key = f.top_supplier_key;
