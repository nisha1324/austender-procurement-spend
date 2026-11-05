-- Part 3 base: one row per active notice with the fields the competition and compliance
-- questions need. Needs the views from 00_load.sql and 01_spend.sql.
--
-- Rules for FY2024-25 (Commonwealth Procurement Rules in force 1 July 2024 to 16 November 2025):
-- * Division 2 (an open approach, unless a 10.3 condition or an Appendix A exemption applies)
--   starts at $80,000 for non-corporate entities, $400,000 for prescribed corporate entities and
--   $7.5 million for construction services, GST inclusive, judged on the expected value. The
--   API has no expected value, so the value at award (the first version) stands in for it.
-- * A contract must be reported within 42 days of entering into it. The API has no signing date
--   (its `dateSigned` is the publish date), so the lag is measured from the contract start date,
--   a proxy: a contract signed after its start date looks late here even if it was reported on
--   time. Placeholder start dates (before 2000) are left out of every lag figure.

CREATE OR REPLACE VIEW comp AS
SELECT
    s.cn_id, s.published_au, s.agency_key, l.agency_label AS agency, s.is_defence,
    s.supplier_key, s.description, s.unspsc, s.segment, s.family, s.family_title,
    s.original_value_aud AS award_value, s.value_aud AS current_value,
    n.method, n.limited_reason_code, n.limited_reason, n.exemption_flag, n.exemption_code,
    n.exemption, n.n_amendments, n.original_start_au AS start_au,
    CASE WHEN n.original_start_au >= DATE '2000-01-01'
         THEN s.published_au - n.original_start_au END                       AS lag_days,
    s.original_value_aud >= 80000                                            AS award_80k_plus,
    -- How the notice was bought, as the CPRs would describe it.
    CASE WHEN n.method = 'open' THEN '1. Open tender'
         WHEN n.method = 'selective' THEN '2. Prequalified tender'
         WHEN n.limited_reason_code IS NOT NULL THEN '3. Limited: a 10.3 condition'
         WHEN n.exemption_code IS NOT NULL THEN '4. Limited: an exemption'
         ELSE '5. Limited: no reason or exemption code' END                  AS route
FROM spend s
JOIN notices n USING (cn_id)
JOIN agency_labels l USING (agency_key);
