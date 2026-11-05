-- Part 4 base: active notices coded only to UNSPSC segment 86, Education and Training Services.
-- The AusTender codeset has no families under segment 86, so this code is as fine as agencies
-- can go. Needs the `spend` view from 01_spend.sql.
CREATE OR REPLACE VIEW training AS
SELECT cn_id, agency, agency_key, is_defence, supplier_name, supplier_key,
       -- One line per notice: some descriptions carry line breaks.
       trim(regexp_replace(description, '\s+', ' ', 'g')) AS description,
       value_aud, original_value_aud, method_details
FROM spend
WHERE unspsc = '86000000';
