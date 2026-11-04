"""The load views and profile queries on a hand-written set of notices with known answers."""
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_snapshot as bs
from scripts import check_amendment_values as cav
from scripts import profile_releases as pr

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def con(release, tmp_path):
    specs = [
        # CN1: notice + 10 amendments; the latest is A10, which a text sort would miss (A9 > A10).
        *[({"cn": "CN1", "n": k, "value": f"{100000 + 1000 * k}.00"}) for k in range(0, 11)],
        # CN2: an amendment that lowers the value.
        {"cn": "CN2", "value": "50000.00"},
        {"cn": "CN2", "n": 1, "value": "40000.00"},
        # Limited tenders, one of each coding pattern seen in the real data.
        {"cn": "CN3", "value": "20000.00", "method": "limited", "limitedTenderExempt": "1"},
        {"cn": "CN4", "value": "900000.00", "method": "limited", "limitedTenderExempt": "0",
         "limitedTenderReasonCode": "TR", "limitedTenderReason": "10.3.d.iii"},
        {"cn": "CN5", "value": "300000.00", "method": "limited", "limitedTenderExempt": "1",
         "exemptionCode": "LH", "exemption": "App A: 14. Contracts for labour hire."},
        # CN6: same supplier ABN, different spelling.
        {"cn": "CN6", "value": "15000.00", "supplier": "ACME P/L"},
    ]
    rows = [bs.flatten_release(release(**kw), "2024-07-01") for kw in specs]
    df = bs.build(pd.DataFrame(rows, columns=bs.COLUMNS))
    path = tmp_path / "releases.csv.gz"
    df.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    return pr.connect(path)


@pytest.fixture
def results(con):
    return pr.run_all(con, ROOT / "sql" / "profile.sql")


def test_notices_view_takes_the_highest_amendment_number(con):
    row = con.sql("SELECT * FROM notices WHERE cn_id = 'CN1'").df().iloc[0]
    assert row.latest_amendment_no == 10
    assert row.value_aud == Decimal("110000.00")
    assert row.original_value_aud == Decimal("100000.00")
    assert row.n_amendments == 10


def test_coverage_and_chain(results):
    cov = results["coverage"].iloc[0]
    assert (cov.releases, cov.notices, cov.amendments, cov.notices_amended) == (17, 6, 11, 2)
    chain = results["chain"].iloc[0]
    assert chain.notices_missing_parent == 0 and chain.notices_with_gaps == 0
    assert chain.amendments == 11 and chain.amendments_point_to_notice == 11
    assert chain.amendments_point_elsewhere == 0
    assert chain.most_amendments == 10


def test_amendment_steps_and_double_count(results):
    steps = results["amendment_steps"].iloc[0]
    assert (steps.increase, steps.no_change, steps.decrease) == (10, 0, 1)
    dc = results["double_count"].iloc[0]
    every = sum(100000 + 1000 * k for k in range(11)) + 50000 + 40000 + 20000 + 900000 + 300000 + 15000
    assert float(dc.sum_every_version) == every
    assert float(dc.sum_current_value) == 110000 + 40000 + 20000 + 900000 + 300000 + 15000
    assert float(dc.sum_value_at_award) == 100000 + 50000 + 20000 + 900000 + 300000 + 15000


def test_limited_patterns(results):
    lp = results["limited_patterns"]
    got = {(r.exemption_flag, r.has_reason_code, r.has_exemption_code, r.award_80k_plus): r.notices
           for r in lp.itertuples()}
    assert got == {("1", False, False, False): 1, ("0", True, False, True): 1, ("1", False, True, True): 1}


def test_abn_variants(results):
    v = results["abn_variant_summary"].iloc[0]
    assert v.abns == 1 and v.abns_several_names == 1


def test_amendment_check_on_saved_api_values():
    values = json.loads((ROOT / "tests" / "fixtures" / "cn3350299_values.json").read_text())
    rows = cav.compare(values)
    assert [r["match"] for r in rows] == [True, True]
    # The same values read as changes instead of totals would not match.
    assert Decimal(values["CN3350299-A16"]) != cav.EXPORT_CHANGES["CN3350299-A16"]


def test_amendment_numbers_sort_as_numbers():
    ids = ["CN1-A2", "CN1-A10", None, "CN1-A9"]
    assert sorted(ids, key=cav.amendment_no) == [None, "CN1-A2", "CN1-A9", "CN1-A10"]
