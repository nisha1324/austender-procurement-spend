"""Facts the rules rest on, checked on the committed snapshot."""
from pathlib import Path

import pandas as pd
import pytest

from scripts import profile_releases as pr

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def r():
    return pr.run_all(pr.connect(), ROOT / "sql" / "profile.sql")


def test_amendment_chain_is_complete_and_points_at_the_notice(r):
    c = r["chain"].iloc[0]
    assert c.notices_missing_parent == 0 and c.notices_with_gaps == 0
    assert c.amendments_point_to_notice == c.amendments
    assert c.notices_publish_date_varies == 0 and c.notices_several_ocids == 0


def test_summing_versions_overstates(r):
    dc = r["double_count"].iloc[0]
    assert float(dc.overstatement) > 2
    assert float(dc.sum_current_value) > float(dc.sum_value_at_award)


def test_no_negative_or_zero_values(r):
    s = r["amendment_steps"].iloc[0]
    assert s.negative_values == 0 and s.zero_values == 0


def test_supplier_id_never_splits_an_abn(r):
    assert r["supplier_id_meaning"].iloc[0].abns_several_ids == 0


def test_notices_view_is_one_row_per_notice():
    con = pr.connect()
    a, b = con.sql("SELECT count(*), count(DISTINCT cn_id) FROM notices").fetchone()
    assert a == b == con.sql("SELECT count(*) FROM releases WHERE amendment_no = 0").fetchone()[0]


def test_monthly_chart_data_leaves_out_cancelled(r):
    con = pr.connect()
    active = con.sql("SELECT count(*) FROM notices WHERE status = 'active'").fetchone()[0]
    assert r["monthly"].notices.sum() == active


def test_profile_regenerates_identically(tmp_path, monkeypatch):
    """The committed report is what the code produces now."""
    import json
    snap = json.loads(pr.SNAPSHOT.read_text())
    text = pr.write_report(pr.run_all(pr.connect(), ROOT / "sql" / "profile.sql"), snap)
    assert text == (ROOT / "results" / "SOURCE_PROFILE.md").read_text()
    bands = pd.read_csv(ROOT / "results" / "value_bands.csv")
    assert bands.notices.sum() == snap["contract_notices"]
