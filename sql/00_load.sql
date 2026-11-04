-- Load the snapshot and build the two views every later query uses.
-- {releases_csv} is filled in by the Python runner.

CREATE OR REPLACE TABLE releases_raw AS
SELECT * FROM read_csv('{releases_csv}', header = true, all_varchar = true);

-- One row per version of a notice, typed.
-- Dates come as UTC; `_au` columns are Canberra calendar dates (AusTender works in Canberra time).
CREATE OR REPLACE VIEW releases AS
SELECT
    release_id, ocid, cn_id, release_type, amendment_id, amends_release_id,
    -- CN123-A16 -> 16, the notice itself -> 0. Never sort amendments as text (A10 < A2).
    CASE WHEN amendment_id IS NULL THEN 0
         ELSE CAST(split_part(amendment_id, '-A', 2) AS INTEGER) END        AS amendment_no,
    CAST(release_date AS TIMESTAMPTZ)                                         AS release_ts,
    CAST(cn_published AS TIMESTAMPTZ)                                         AS published_ts,
    CAST(timezone('Australia/Sydney', CAST(cn_published AS TIMESTAMPTZ)) AS DATE) AS published_au,
    CAST(timezone('Australia/Sydney', CAST(release_date AS TIMESTAMPTZ)) AS DATE) AS release_au,
    CAST(timezone('Australia/Sydney', CAST(start_date AS TIMESTAMPTZ)) AS DATE)   AS start_au,
    CAST(timezone('Australia/Sydney', CAST(end_date AS TIMESTAMPTZ)) AS DATE)     AS end_au,
    agency, agency_abn, agency_branch, agency_division,
    supplier_id, supplier_name, supplier_abn, supplier_locality, supplier_region,
    supplier_postcode, supplier_country,
    unspsc, description, agency_reference,
    CAST(value_aud AS DECIMAL(18, 2))                                         AS value_aud,
    currency, status, method, method_details,
    limited_reason_code, limited_reason, exemption_flag, exemption_code, exemption
FROM releases_raw;

-- One row per contract notice: the latest version (current value), with the value at award.
CREATE OR REPLACE VIEW notices AS
WITH ranked AS (
    SELECT *, row_number() OVER (PARTITION BY cn_id ORDER BY amendment_no DESC) AS rn_latest
    FROM releases
),
firsts AS (
    SELECT cn_id, value_aud AS original_value_aud, start_au AS original_start_au,
           end_au AS original_end_au
    FROM releases WHERE amendment_no = 0
),
counts AS (
    SELECT cn_id, count(*) - 1 AS n_amendments, max(amendment_no) AS last_amendment_no
    FROM releases GROUP BY cn_id
)
SELECT r.* EXCLUDE (rn_latest, amendment_id, amends_release_id, release_id, release_type),
       r.amendment_no AS latest_amendment_no,
       f.original_value_aud, f.original_start_au, f.original_end_au,
       c.n_amendments
FROM ranked r
LEFT JOIN firsts f USING (cn_id)
JOIN counts c USING (cn_id)
WHERE r.rn_latest = 1;
