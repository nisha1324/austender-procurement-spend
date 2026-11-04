import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_snapshot as bs

ROOT = Path(__file__).resolve().parent.parent


def test_flatten_reads_agency_branch_from_the_supplier_party_and_drops_contacts(release):
    row = bs.flatten_release(release(), "2024-07-01")
    assert row["agency"] == "Department of Examples"
    assert row["agency_abn"] == "99999999999"
    assert row["agency_branch"] == "Procurement Branch"
    assert row["agency_division"] == "Corporate Division"
    assert row["supplier_abn"] == "11111111111"
    text = json.dumps(row)
    for secret in ("An Officer", "officer@agency.gov.au", "02 0000 0000", "1 Secret St"):
        assert secret not in text
    assert list(row) == bs.COLUMNS


def test_flatten_picks_the_amendment_this_release_records(release):
    row = bs.flatten_release(release(n=3, value="250000.00"), "2024-07-01")
    assert row["release_type"] == "amendment"
    assert row["amendment_id"] == "CN1-A3"
    assert row["amends_release_id"] == "prod-CN1-r0"
    assert row["value_aud"] == "250000.00"


def test_flatten_keeps_limited_tender_codes(release):
    rel = release(method="limited", limitedTenderExempt="0", limitedTenderReasonCode="TR",
                  limitedTenderReason="10.3.d.iii ...")
    row = bs.flatten_release(rel, "2024-07-01")
    assert (row["method"], row["exemption_flag"], row["limited_reason_code"]) == ("limited", "0", "TR")


@pytest.mark.parametrize("breaker, message", [
    (lambda r: r["awards"][0]["suppliers"].append({"id": "s2", "name": "B"}), "supplier"),
    (lambda r: r["contracts"].append(r["contracts"][0]), "contract"),
    (lambda r: r["contracts"][0]["items"].append(r["contracts"][0]["items"][0]), "item"),
    (lambda r: r.__setitem__("tag", ["tender"]), "unexpected tag"),
    (lambda r: r["contracts"][0]["items"][0]["classification"].__setitem__("scheme", "CPV"), "UNSPSC"),
])
def test_flatten_refuses_shapes_it_would_lose_data_on(release, breaker, message):
    rel = release()
    breaker(rel)
    with pytest.raises(ValueError, match=message):
        bs.flatten_release(rel, "2024-07-01")


def _frame(release, specs):
    return pd.DataFrame([bs.flatten_release(release(**kw), day) for kw, day in specs], columns=bs.COLUMNS)


def test_build_keeps_a_midnight_notice_once_under_the_new_day(release):
    midnight = "2024-08-04T14:00:00Z"  # 00:00 on 5 Aug in Canberra
    df = _frame(release, [
        ({"cn": "CN1", "published": midnight}, "2024-08-04"),
        ({"cn": "CN1", "published": midnight}, "2024-08-05"),
        ({"cn": "CN2", "published": "2024-08-05T01:00:00Z"}, "2024-08-05"),
    ])
    out = bs.build(df)
    assert len(out) == 2
    assert out.set_index("cn_id").loc["CN1", "fetched_day"] == "2024-08-05"


def test_build_drops_a_notice_after_the_last_day(release):
    df = _frame(release, [
        ({"cn": "CN1", "published": "2025-06-30T01:00:00Z"}, "2025-06-30"),
        ({"cn": "CN9", "published": "2025-06-30T14:00:00Z"}, "2025-06-30"),  # 1 Jul in Canberra
    ])
    assert bs.build(df)["cn_id"].tolist() == ["CN1"]


def test_build_fails_if_a_release_would_vanish(release):
    df = _frame(release, [({"cn": "CN1", "published": "2024-08-10T01:00:00Z"}, "2024-08-04"),
                          ({"cn": "CN2", "published": "2024-08-20T01:00:00Z"}, "2024-08-20")])
    with pytest.raises(ValueError, match="weren't published on"):
        bs.build(df)


def test_build_fails_on_a_conflicting_repeat(release):
    df = _frame(release, [({"cn": "CN1", "value": "1.00"}, "2024-07-01"),
                          ({"cn": "CN1", "value": "2.00"}, "2024-07-01")])
    with pytest.raises(ValueError, match="different contents"):
        bs.build(df)


def test_committed_snapshot_matches_its_manifest():
    meta = json.loads((ROOT / "data" / "SNAPSHOT.json").read_text())
    path = ROOT / "data" / meta["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"]
    df = pd.read_csv(path, dtype=str)
    assert len(df) == meta["releases"]
    assert (df.release_type == "contract").sum() == meta["contract_notices"]
    assert (df.release_type == "amendment").sum() == meta["amendments"]
    assert df.release_id.is_unique
    assert meta["licences"] == ["https://creativecommons.org/licenses/by/3.0/au/"]
    assert (meta["first_day"], meta["last_day"]) == ("2024-07-01", "2025-06-30")
