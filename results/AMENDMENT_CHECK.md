# Amendment values: running total, not the change

Contract `CN3350299` (Department of Defence) in the live AusTender OCDS API, against the
`Amendments Value` column of the government's [historical CN export](https://data.gov.au/data/dataset/5c7fa69b-b0e9-4553-b8df-2a022dd2e982/resource/bc2097b7-8116-4e9d-9953-98813635892a/download).

| Amendment | API value before | API value after | Step in the API | Change in the export | Match |
|---|---:|---:|---:|---:|---|
| CN3350299-A16 | 3,454,993,626.88 | 9,739,061,243.88 | 6,284,067,617.00 | 6,284,067,617.00 | yes |
| CN3350299-A18 | 9,858,341,982.18 | 11,976,801,152.18 | 2,118,459,170.00 | 2,118,459,170.00 | yes |

The contract has 72 versions in the API (the notice and 71 amendments).

**Verdict: each amendment's value is the contract's new total.** Summing every version of a notice would count the same money again and again; use the latest version only.
